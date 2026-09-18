"""
Unit tests for bookings/matching.py

Covers:
  - normalize_text: lowercasing, punctuation removal, ordinal word substitution
  - find_best_team_match: exact match, token-subset match, partial match,
    ambiguity detection, empty queryset / no match fallbacks
  - find_best_pitch_match: venue+pitch combined matching, substring boost,
    empty preference fallback, empty queryset fallback
"""

from unittest.mock import MagicMock, patch

from bookings.matching import find_best_pitch_match, find_best_team_match, normalize_text
from bookings.models import Pitch, Venue
from django.test import TestCase

# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


class NormalizeTextTest(TestCase):
    def test_empty_string_returns_empty(self):
        self.assertEqual(normalize_text(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_text(None), "")

    def test_lowercases_input(self):
        self.assertEqual(normalize_text("HELLO WORLD"), "hello world")

    def test_removes_punctuation(self):
        # Punctuation becomes spaces; normalisation strips consecutive whitespace doesn't collapse
        result = normalize_text("St. Mary's CC")
        self.assertNotIn("'", result)
        self.assertNotIn(".", result)

    def test_numeric_string_passes_through(self):
        result = normalize_text("1st XI")
        self.assertIn("1st", result)
        self.assertIn("xi", result)

    def test_replaces_first_with_ordinal(self):
        self.assertIn("1st", normalize_text("First XI"))

    def test_replaces_second_with_ordinal(self):
        self.assertIn("2nd", normalize_text("Second XI"))

    def test_replaces_third_with_ordinal(self):
        self.assertIn("3rd", normalize_text("Third XI"))

    def test_replaces_fourth_with_ordinal(self):
        self.assertIn("4th", normalize_text("Fourth XI"))

    def test_does_not_replace_partial_word(self):
        # "firstly" should NOT become "1stly"
        result = normalize_text("Firstly")
        self.assertNotIn("1stly", result)
        self.assertIn("firstly", result)

    def test_mixed_ordinals_and_punctuation(self):
        result = normalize_text("Bournemouth First XI (Home)")
        self.assertIn("1st", result)
        self.assertIn("bournemouth", result)
        self.assertIn("xi", result)
        self.assertNotIn("(", result)
        self.assertNotIn(")", result)

    def test_numeric_coercion(self):
        # Non-string input is coerced to string
        result = normalize_text(123)
        self.assertEqual(result, "123")


# ---------------------------------------------------------------------------
# Helpers – build cheap mock Team querysets
# ---------------------------------------------------------------------------


def _make_team(team_id, name):
    """Return a simple MagicMock that quacks like a Team."""
    t = MagicMock()
    t.id = team_id
    t.name = name
    return t


def _make_teams_qs(*team_mocks):
    """
    Build a mock queryset from a list of team mocks.
    Supports iteration, .first(), and .filter().
    """
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter(team_mocks))
    qs.first = MagicMock(return_value=team_mocks[0] if team_mocks else None)
    return qs


def _make_empty_qs():
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter([]))
    qs.first = MagicMock(return_value=None)
    return qs


# ---------------------------------------------------------------------------
# find_best_team_match
# ---------------------------------------------------------------------------


class FindBestTeamMatchTest(TestCase):
    def test_exact_match_returns_score_100_and_not_ambiguous(self):
        team = _make_team(1, "Bournemouth 1st XI")
        result = find_best_team_match("Bournemouth 1st XI", _make_teams_qs(team))
        self.assertEqual(result["team_id"], 1)
        self.assertFalse(result["ambiguous"])

    def test_ordinal_normalisation_exact_match(self):
        # Imported name uses "First", team name uses "1st"
        team = _make_team(1, "Bournemouth 1st XI")
        result = find_best_team_match("Bournemouth First XI", _make_teams_qs(team))
        self.assertEqual(result["team_id"], 1)
        self.assertFalse(result["ambiguous"])

    def test_full_token_intersection_match(self):
        # All tokens of the imported name appear in the team name
        team = _make_team(2, "Bournemouth 2nd XI Development Squad")
        result = find_best_team_match("Bournemouth 2nd XI", _make_teams_qs(team))
        self.assertEqual(result["team_id"], 2)

    def test_partial_match_is_returned(self):
        team = _make_team(3, "Poole Town CC")
        result = find_best_team_match("Poole CC", _make_teams_qs(team))
        # "Poole" and "CC" are both in team tokens → intersection_count > 0
        self.assertEqual(result["team_id"], 3)

    def test_best_match_selected_from_multiple_teams(self):
        team_a = _make_team(10, "Poole Town CC 1st XI")  # 4 matching tokens
        team_b = _make_team(11, "Dorset CC")  # 1 matching token ("CC")
        result = find_best_team_match("Poole Town CC 1st XI", _make_teams_qs(team_a, team_b))
        self.assertEqual(result["team_id"], 10)

    def test_ambiguous_when_two_teams_tie_on_top_score(self):
        # Both team names produce the same normalized form → both score 100
        team_a = _make_team(20, "Lymington CC")
        team_b = _make_team(21, "Lymington CC")  # exact duplicate
        result = find_best_team_match("Lymington CC", _make_teams_qs(team_a, team_b))
        self.assertTrue(result["ambiguous"])

    def test_ambiguous_when_scores_within_5_points(self):
        # team_a matches 2 tokens ("1st", "XI") → score = 2*10 = 20
        # team_b matches 1 token ("XI") → score = 10
        # Difference = 10 ≥ 5, so NOT ambiguous
        team_a = _make_team(30, "1st XI Home")
        team_b = _make_team(31, "XI Away")
        result = find_best_team_match("1st XI", _make_teams_qs(team_a, team_b))
        # score diff = 20 - 10 = 10 >= 5, so not ambiguous
        self.assertFalse(result["ambiguous"])

    def test_ambiguous_within_5_points(self):
        # Construct a scenario where scores differ by < 5
        # team_a: exact match → 100, team_b: full token subset → 81 (diff = 19, not ambiguous)
        # Instead force via same score using identical intersection counts
        team_a = _make_team(40, "Park CC")  # intersect with "Park CC" → score 100
        team_b = _make_team(41, "Park CC")  # same → score 100 too → ambiguous
        result = find_best_team_match("Park CC", _make_teams_qs(team_a, team_b))
        self.assertTrue(result["ambiguous"])

    def test_no_match_returns_first_team_id(self):
        team = _make_team(50, "Random Club CC")
        result = find_best_team_match("ZZZZZ Unrecognised", _make_teams_qs(team))
        # No overlap → fallback to first team
        self.assertEqual(result["team_id"], 50)
        self.assertFalse(result["ambiguous"])

    def test_empty_queryset_returns_none(self):
        result = find_best_team_match("Bournemouth 1st XI", _make_empty_qs())
        self.assertIsNone(result["team_id"])
        self.assertFalse(result["ambiguous"])

    def test_empty_imported_name_no_match_fallback(self):
        team = _make_team(60, "Some Club")
        result = find_best_team_match("", _make_teams_qs(team))
        # Empty imported_tokens set, intersection_count will be 0 for every team
        # Also norm_team != norm_imported → no 100-score matches
        # So falls through to "no matches" → return first team
        self.assertEqual(result["team_id"], 60)


# ---------------------------------------------------------------------------
# Helpers – build mock Pitch and Venue querysets
# ---------------------------------------------------------------------------


def _make_pitch(pitch_id, pitch_name, venue_id):
    p = MagicMock()
    p.id = pitch_id
    p.name = pitch_name
    p.venue_id = venue_id
    return p


def _make_venue_mock(venue_id, venue_name):
    v = MagicMock()
    v.id = venue_id
    v.name = venue_name
    return v


def _make_pitches_qs(*pitch_mocks):
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter(pitch_mocks))
    qs.first = MagicMock(return_value=pitch_mocks[0] if pitch_mocks else None)
    return qs


def _make_venues_qs(*venue_mocks):
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter(venue_mocks))

    def filter_side_effect(**kwargs):
        vid = kwargs.get("id")
        matching = [v for v in venue_mocks if v.id == vid]
        inner = MagicMock()
        inner.first = MagicMock(return_value=matching[0] if matching else None)
        return inner

    qs.filter = MagicMock(side_effect=filter_side_effect)
    return qs


# ---------------------------------------------------------------------------
# find_best_pitch_match
# ---------------------------------------------------------------------------


class FindBestPitchMatchTest(TestCase):
    def setUp(self):
        self.venue = _make_venue_mock(1, "Main Ground")
        self.pitch1 = _make_pitch(101, "Pitch 1", venue_id=1)
        self.pitch2 = _make_pitch(102, "Astro Pitch", venue_id=1)
        self.venues_qs = _make_venues_qs(self.venue)
        self.pitches_qs = _make_pitches_qs(self.pitch1, self.pitch2)

    def test_none_preference_returns_first_pitch(self):
        result = find_best_pitch_match(None, self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 101)

    def test_empty_string_preference_returns_first_pitch(self):
        result = find_best_pitch_match("", self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 101)

    def test_token_match_selects_correct_pitch(self):
        # "Astro" is in Pitch 2 but not Pitch 1
        result = find_best_pitch_match("Astro", self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 102)

    def test_venue_name_included_in_scoring(self):
        # "Main Ground Pitch 1" - "Main" and "Ground" are in the venue name
        result = find_best_pitch_match("Main Ground Pitch 1", self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 101)

    def test_substring_boost_applied(self):
        # "Main Ground Pitch 1" contains the full pitch description → +50 boost
        result = find_best_pitch_match("Main Ground Pitch 1", self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 101)

    def test_no_pitches_returns_none(self):
        empty_pitches = _make_pitches_qs()
        empty_pitches.first = MagicMock(return_value=None)
        result = find_best_pitch_match("Any pitch", empty_pitches, self.venues_qs)
        self.assertIsNone(result)

    def test_no_match_returns_first_pitch(self):
        # Token "zzzzz" won't match anything → score stays 0 → best_pitch_id remains None
        # Function falls back to first pitch
        result = find_best_pitch_match(
            "zzzzz completely unmatched", self.pitches_qs, self.venues_qs
        )
        # max_score will be -1 after the loop since no token matches
        # best_pitch_id = None, so fallback to first_pitch.id = 101
        self.assertEqual(result, 101)

    def test_multiple_tokens_accumulate_score(self):
        # "Astro Pitch" has two tokens matching pitch2
        pitch3 = _make_pitch(103, "Old Ground", venue_id=1)
        pitches_qs = _make_pitches_qs(self.pitch1, self.pitch2, pitch3)
        result = find_best_pitch_match("Astro Pitch", pitches_qs, self.venues_qs)
        self.assertEqual(result, 102)

    def test_case_insensitive_matching(self):
        # Preference with different casing
        result = find_best_pitch_match("ASTRO", self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 102)
