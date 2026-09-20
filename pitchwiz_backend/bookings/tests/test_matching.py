"""
Unit tests for bookings/matching.py

Covers:
  - normalize_text: lowercasing, punctuation removal, ordinal word substitution
  - find_best_team_match: exact match, token-subset match, partial match,
    ambiguity detection, empty queryset / no match fallbacks
  - find_best_pitch_match: venue+pitch combined matching, substring boost,
    empty preference fallback, empty queryset fallback, entity_type filtering
"""

from unittest.mock import MagicMock, patch

from bookings.matching import find_best_pitch_match, find_best_team_match, normalize_text
from bookings.models import Pitch, Venue
from django.test import TestCase

# ... (Keep NormalizeTextTest, _make_team, _make_teams_qs, _make_empty_qs, FindBestTeamMatchTest as they are) ...


# ---------------------------------------------------------------------------
# Helpers – build mock Pitch and Venue querysets
# ---------------------------------------------------------------------------


def _make_teams_qs(*team_mocks):
    """
    Build a mock queryset from a list of team mocks.
    Supports iteration, .first(), and .filter().
    """
    qs = MagicMock()
    # Use side_effect to generate a fresh iterator on every call
    qs.__iter__ = MagicMock(side_effect=lambda: iter(team_mocks))
    qs.first = MagicMock(return_value=team_mocks[0] if team_mocks else None)
    return qs


def _make_empty_qs():
    qs = MagicMock()
    qs.__iter__ = MagicMock(side_effect=lambda: iter([]))
    qs.first = MagicMock(return_value=None)
    return qs


def _make_pitch(pitch_id, pitch_name, venue_id, entity_type="MAIN"):
    p = MagicMock()
    p.id = pitch_id
    p.name = pitch_name
    p.venue_id = venue_id
    p.entity_type = entity_type
    return p


def _make_venue_mock(venue_id, venue_name):
    v = MagicMock()
    v.id = venue_id
    v.name = venue_name
    return v


def _make_pitches_qs(*pitch_mocks):
    qs = MagicMock()
    # Use side_effect to generate a fresh iterator on every call
    qs.__iter__ = MagicMock(side_effect=lambda: iter(pitch_mocks))
    qs.first = MagicMock(return_value=pitch_mocks[0] if pitch_mocks else None)
    return qs


def _make_venues_qs(*venue_mocks):
    qs = MagicMock()
    # Use side_effect to generate a fresh iterator on every call
    qs.__iter__ = MagicMock(side_effect=lambda: iter(venue_mocks))

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
        self.pitch1 = _make_pitch(101, "Pitch 1", venue_id=1, entity_type="MAIN")
        self.pitch2 = _make_pitch(102, "Astro Pitch", venue_id=1, entity_type="YOUTH")
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
        pitch3 = _make_pitch(103, "Old Ground", venue_id=1, entity_type="MAIN")
        pitches_qs = _make_pitches_qs(self.pitch1, self.pitch2, pitch3)
        result = find_best_pitch_match("Astro Pitch", pitches_qs, self.venues_qs)
        self.assertEqual(result, 102)

    def test_case_insensitive_matching(self):
        # Preference with different casing
        result = find_best_pitch_match("ASTRO", self.pitches_qs, self.venues_qs)
        self.assertEqual(result, 102)

    # NEW: Test to enforce the NET and OUTFIELD exclusion logic
    def test_ignores_net_and_outfield_entity_types(self):
        net_pitch = _make_pitch(998, "Practice Nets", venue_id=1, entity_type="NET")
        outfield_pitch = _make_pitch(999, "Outfield Space", venue_id=1, entity_type="OUTFIELD")

        # Queryset contains NET, OUTFIELD, MAIN, and YOUTH
        pitches_qs = _make_pitches_qs(net_pitch, outfield_pitch, self.pitch1, self.pitch2)

        # "Practice Nets" is an exact text match for net_pitch,
        # but because it's a NET, it should be excluded from scoring entirely.
        result = find_best_pitch_match("Practice Nets", pitches_qs, self.venues_qs)

        # It should fall back to the first VALID pitch in the list (self.pitch1)
        self.assertEqual(result, 101)

        # "Outfield Space" is an exact match for the outfield pitch,
        # but again, it should be excluded.
        result_outfield = find_best_pitch_match("Outfield Space", pitches_qs, self.venues_qs)

        # Falls back to first valid pitch
        self.assertEqual(result_outfield, 101)
