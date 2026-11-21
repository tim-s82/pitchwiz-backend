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

from bookings.matching import (
    allocate_pitches_for_matches,
    find_best_pitch_match,
    find_best_team_match,
    find_best_venue_match,
    infer_season_year,
    match_fixtures_for_refresh,
    normalize_opponent,
    normalize_text,
)
from bookings.models import Fixture, Pitch, PitchBooking, PitchLength, Team, Venue
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


# ---------------------------------------------------------------------------
# normalize_opponent & infer_season_year Tests
# ---------------------------------------------------------------------------


class NormalizeOpponentTest(TestCase):
    def test_strips_common_club_words(self):
        self.assertEqual(normalize_opponent("Poole CC"), "poole")
        self.assertEqual(normalize_opponent("Poole Cricket Club"), "poole")
        self.assertEqual(normalize_opponent("Dorchester Town CC"), "dorchester")

    def test_ordinal_and_roman_conversions(self):
        self.assertEqual(normalize_opponent("Dorchester II"), "dorchester 2nd")
        self.assertEqual(normalize_opponent("Wimborne 1st XI"), "wimborne 1st")
        self.assertEqual(normalize_opponent("Swanage Second XI"), "swanage 2nd")


class InferSeasonYearTest(TestCase):
    def test_infers_year_from_iso_dates(self):
        dates = ["2026-05-16", "2026-05-23", "2026-06-06"]
        self.assertEqual(infer_season_year(dates), 2026)

    def test_infers_year_from_uk_dates(self):
        dates = ["16/05/2026", "23/05/2026", "06/06/2026"]
        self.assertEqual(infer_season_year(dates), 2026)

    def test_empty_dates_falls_back_to_current_year(self):
        from datetime import datetime

        self.assertEqual(infer_season_year([]), datetime.now().year)


class FindBestVenueMatchTest(TestCase):
    def setUp(self):
        self.v1 = Venue.objects.create(name="The Leaze", is_default=True)
        self.v2 = Venue.objects.create(name="Dumpton School", is_default=False)

    def test_matches_by_name(self):
        venue = find_best_venue_match("Dumpton", Venue.objects.all())
        self.assertEqual(venue.id, self.v2.id)

    def test_falls_back_to_default_venue_on_no_match(self):
        venue = find_best_venue_match("Unknown Ground", Venue.objects.all())
        self.assertEqual(venue.id, self.v1.id)


# ---------------------------------------------------------------------------
# Play-Cricket Matching Tests
# ---------------------------------------------------------------------------


class PlayCricketMatchingTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")
        self.venue = Venue.objects.create(name="The Leaze", is_default=True)
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")

        self.f1 = Fixture.objects.create(
            team=self.team,
            opponent="Dorchester CC",
            start_date="2026-05-16",
            end_date="2026-05-16",
            play_cricket_id="5001",
        )
        self.b1 = PitchBooking.objects.create(
            fixture=self.f1,
            pitch=self.pitch,
            start_date="2026-05-16",
            end_date="2026-05-16",
            time_slot="AFTERNOON",
            status="APPROVED",
        )

        self.f2 = Fixture.objects.create(
            team=self.team,
            opponent="Poole Town CC",
            start_date="2026-05-23",
            end_date="2026-05-23",
            play_cricket_id="5002",
        )
        self.b2 = PitchBooking.objects.create(
            fixture=self.f2,
            pitch=self.pitch,
            start_date="2026-05-23",
            end_date="2026-05-23",
            time_slot="AFTERNOON",
            status="APPROVED",
        )

        # Friendly fixture without play_cricket_id
        self.friendly = Fixture.objects.create(
            team=self.team,
            opponent="Local Friendly XI",
            start_date="2026-06-01",
            end_date="2026-06-01",
            play_cricket_id=None,
        )

    def test_exact_pc_id_match_unchanged(self):
        incoming = [
            {
                "playCricketId": "5001",
                "opponent": "Dorchester CC",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
            }
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=True
        )
        matched = next(r for r in results if r["playCricketId"] == "5001")
        self.assertEqual(matched["action"], "UNCHANGED")
        self.assertEqual(matched["existing_fixture_id"], self.f1.id)

    def test_exact_pc_id_match_rescheduled_date(self):
        incoming = [
            {
                "playCricketId": "5002",
                "opponent": "Poole Town CC",
                "date": "2026-05-30",  # Moved from 2026-05-23
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
            }
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=True
        )
        matched = next(r for r in results if r["playCricketId"] == "5002")
        self.assertEqual(matched["action"], "RESCHEDULED")
        self.assertEqual(matched["oldDate"], "2026-05-23")
        self.assertEqual(matched["date"], "2026-05-30")
        self.assertTrue(matched["selected"])

    def test_new_fixture_in_play_cricket(self):
        incoming = [
            {
                "playCricketId": "5003",
                "opponent": "Broadstone CC",
                "date": "2026-06-06",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
            }
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=True
        )
        matched = next(r for r in results if r["playCricketId"] == "5003")
        self.assertEqual(matched["action"], "NEW")
        self.assertTrue(matched["selected"])

    def test_removed_fixture_in_play_cricket_flagged_for_removal_unchecked(self):
        # Incoming only has 5001; 5002 is absent from incoming data
        incoming = [
            {
                "playCricketId": "5001",
                "opponent": "Dorchester CC",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
            }
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=True
        )
        removed = next((r for r in results if r.get("existing_fixture_id") == self.f2.id), None)
        self.assertIsNotNone(removed)
        self.assertEqual(removed["action"], "REMOVED")
        self.assertFalse(removed["selected"])  # Must be unchecked by default for safety

    def test_friendly_without_pc_id_preserved_never_flagged_as_removed(self):
        incoming = [
            {
                "playCricketId": "5001",
                "opponent": "Dorchester CC",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
            }
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=True
        )
        # self.friendly has no play_cricket_id, so it should NOT be in results as REMOVED
        friendly_result = next(
            (r for r in results if r.get("existing_fixture_id") == self.friendly.id), None
        )
        self.assertIsNone(friendly_result)


# ---------------------------------------------------------------------------
# Spreadsheet Heuristic Matching Tests
# ---------------------------------------------------------------------------


class SpreadsheetHeuristicMatchingTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")

    def test_single_db_single_data_exact_date_unchanged(self):
        f = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        incoming = [
            {"opponent": "Poole CC", "date": "2026-05-16", "time": "13:30", "timeSlot": "AFTERNOON"}
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "UNCHANGED")
        self.assertEqual(results[0]["existing_fixture_id"], f.id)

    def test_single_db_single_data_different_date_rescheduled(self):
        f = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        incoming = [
            {"opponent": "Poole CC", "date": "2026-05-23", "time": "13:30", "timeSlot": "AFTERNOON"}
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "RESCHEDULED")
        self.assertEqual(results[0]["existing_fixture_id"], f.id)
        self.assertEqual(results[0]["oldDate"], "2026-05-16")
        self.assertEqual(results[0]["date"], "2026-05-23")

    def test_two_db_two_data_one_exact_one_moved(self):
        f1 = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        f2 = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-07-11", end_date="2026-07-11"
        )
        incoming = [
            {
                "opponent": "Poole CC",
                "date": "2026-05-16",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            },
            {
                "opponent": "Poole CC",
                "date": "2026-07-18",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            },
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        r_exact = next(r for r in results if r["date"] == "2026-05-16")
        r_moved = next(r for r in results if r["date"] == "2026-07-18")

        self.assertEqual(r_exact["action"], "UNCHANGED")
        self.assertEqual(r_exact["existing_fixture_id"], f1.id)

        self.assertEqual(r_moved["action"], "RESCHEDULED")
        self.assertEqual(r_moved["existing_fixture_id"], f2.id)
        self.assertEqual(r_moved["oldDate"], "2026-07-11")

    def test_two_db_two_data_both_moved_matched_by_closest_distance(self):
        f1 = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        f2 = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-07-11", end_date="2026-07-11"
        )
        incoming = [
            {
                "opponent": "Poole CC",
                "date": "2026-05-23",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            },
            {
                "opponent": "Poole CC",
                "date": "2026-07-18",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            },
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        r1 = next(r for r in results if r["date"] == "2026-05-23")
        r2 = next(r for r in results if r["date"] == "2026-07-18")

        self.assertEqual(r1["existing_fixture_id"], f1.id)
        self.assertEqual(r1["oldDate"], "2026-05-16")
        self.assertEqual(r2["existing_fixture_id"], f2.id)
        self.assertEqual(r2["oldDate"], "2026-07-11")

    def test_surplus_incoming_is_marked_new(self):
        Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        incoming = [
            {
                "opponent": "Poole CC",
                "date": "2026-05-16",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            },
            {
                "opponent": "Poole CC",
                "date": "2026-07-18",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            },
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        r_new = next(r for r in results if r["date"] == "2026-07-18")
        self.assertEqual(r_new["action"], "NEW")
        self.assertTrue(r_new["selected"])

    def test_surplus_db_is_marked_removed_unchecked_by_default(self):
        f1 = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        f2 = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-07-11", end_date="2026-07-11"
        )
        incoming = [
            {"opponent": "Poole CC", "date": "2026-05-16", "time": "13:30", "timeSlot": "AFTERNOON"}
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        r_rem = next(r for r in results if r["action"] == "REMOVED")
        self.assertEqual(r_rem["existing_fixture_id"], f2.id)
        self.assertFalse(r_rem["selected"])

    def test_fuzzy_opponent_names_match(self):
        f = Fixture.objects.create(
            team=self.team,
            opponent="Dorchester CC 1st XI",
            start_date="2026-05-16",
            end_date="2026-05-16",
        )
        incoming = [
            {
                "opponent": "Dorchester Cricket Club",
                "date": "2026-05-16",
                "time": "13:30",
                "timeSlot": "AFTERNOON",
            }
        ]
        results = match_fixtures_for_refresh(
            self.team.id, incoming, Fixture.objects.filter(team=self.team), is_play_cricket=False
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["existing_fixture_id"], f.id)


# ---------------------------------------------------------------------------
# Pitch Allocation & Venue Clash Tests
# ---------------------------------------------------------------------------


class PitchAllocationTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")
        self.v_home = Venue.objects.create(name="The Leaze", is_default=True)
        self.pitch1 = Pitch.objects.create(
            venue=self.v_home, name="Pitch 1", pitch_type="GRASS", entity_type="MAIN"
        )
        self.pitch2 = Pitch.objects.create(
            venue=self.v_home, name="Pitch 2", pitch_type="GRASS", entity_type="MAIN"
        )

        self.v_alt = Venue.objects.create(name="Dumpton School", is_default=False)
        self.pitch_alt = Pitch.objects.create(
            venue=self.v_alt, name="Main Pitch", pitch_type="GRASS", entity_type="MAIN"
        )

    def test_preserves_pitch_on_exact_match(self):
        f = Fixture.objects.create(
            team=self.team, opponent="Poole CC", start_date="2026-05-16", end_date="2026-05-16"
        )
        PitchBooking.objects.create(
            fixture=f,
            pitch=self.pitch2,
            start_date="2026-05-16",
            end_date="2026-05-16",
            time_slot="AFTERNOON",
            status="APPROVED",
        )
        records = [
            {
                "action": "UNCHANGED",
                "existing_fixture_id": f.id,
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            }
        ]
        allocated = allocate_pitches_for_matches(
            records,
            Venue.objects.all(),
            Pitch.objects.all(),
            PitchBooking.objects.all(),
            self.team,
        )
        self.assertEqual(allocated[0]["pitchId"], self.pitch2.id)
        self.assertTrue(allocated[0]["pitchPreserved"])

    def test_multi_pitch_venue_allocates_vacant_pitch(self):
        # Pitch 1 is booked on 2026-05-16
        PitchBooking.objects.create(
            pitch=self.pitch1,
            start_date="2026-05-16",
            end_date="2026-05-16",
            time_slot="AFTERNOON",
            status="APPROVED",
        )
        records = [
            {
                "action": "NEW",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            }
        ]
        allocated = allocate_pitches_for_matches(
            records,
            Venue.objects.all(),
            Pitch.objects.all(),
            PitchBooking.objects.all(),
            self.team,
        )
        self.assertEqual(allocated[0]["pitchId"], self.pitch2.id)
        self.assertFalse(allocated[0]["venueClash"])

    def test_outfield_blocking_prevents_assignment(self):
        # Pitch 1 blocks Pitch 2
        self.pitch1.blocks_pitches.add(self.pitch2)

        # Pitch 1 is booked
        PitchBooking.objects.create(
            pitch=self.pitch1,
            start_date="2026-05-16",
            end_date="2026-05-16",
            time_slot="AFTERNOON",
            status="APPROVED",
        )
        records = [
            {
                "action": "NEW",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            }
        ]
        allocated = allocate_pitches_for_matches(
            records,
            Venue.objects.all(),
            Pitch.objects.all(),
            PitchBooking.objects.all(),
            self.team,
        )
        # All pitches at The Leaze are booked or blocked -> venue clash and suggests Dumpton School
        self.assertTrue(allocated[0]["venueClash"])
        self.assertEqual(allocated[0]["suggestedPitchId"], self.pitch_alt.id)
        self.assertIn("Dumpton School", allocated[0]["clashReason"])

    def test_pitch_length_compatibility_respected(self):
        length_22 = PitchLength.objects.create(length_yards=22, description="22y")
        length_19 = PitchLength.objects.create(length_yards=19, description="19y")

        self.pitch1.supported_lengths.add(length_19)
        self.pitch2.supported_lengths.add(length_22)

        self.team.required_length = length_22
        self.team.save()

        records = [
            {
                "action": "NEW",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            }
        ]
        allocated = allocate_pitches_for_matches(
            records,
            Venue.objects.all(),
            Pitch.objects.all(),
            PitchBooking.objects.all(),
            self.team,
        )
        # Pitch 2 supports 22y, so it must be selected
        self.assertEqual(allocated[0]["pitchId"], self.pitch2.id)

    def test_batch_collision_prevention(self):
        records = [
            {
                "action": "NEW",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            },
            {
                "action": "NEW",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            },
        ]
        allocated = allocate_pitches_for_matches(
            records,
            Venue.objects.all(),
            Pitch.objects.all(),
            PitchBooking.objects.all(),
            self.team,
        )
        # Both pitches should be distinct
        assigned = {allocated[0]["pitchId"], allocated[1]["pitchId"]}
        self.assertEqual(assigned, {self.pitch1.id, self.pitch2.id})

    def test_all_venues_full_flags_critical_clash(self):
        # Book Pitch 1, Pitch 2, and Pitch Alt
        PitchBooking.objects.create(
            pitch=self.pitch1, start_date="2026-05-16", end_date="2026-05-16", time_slot="ALL_DAY"
        )
        PitchBooking.objects.create(
            pitch=self.pitch2, start_date="2026-05-16", end_date="2026-05-16", time_slot="ALL_DAY"
        )
        PitchBooking.objects.create(
            pitch=self.pitch_alt,
            start_date="2026-05-16",
            end_date="2026-05-16",
            time_slot="ALL_DAY",
        )

        records = [
            {
                "action": "NEW",
                "date": "2026-05-16",
                "timeSlot": "AFTERNOON",
                "pitchPref": "The Leaze",
                "teamId": self.team.id,
            }
        ]
        allocated = allocate_pitches_for_matches(
            records,
            Venue.objects.all(),
            Pitch.objects.all(),
            PitchBooking.objects.all(),
            self.team,
        )
        self.assertTrue(allocated[0]["venueClash"])
        self.assertIsNone(allocated[0]["suggestedPitchId"])
        self.assertIn("No pitches available across any venue", allocated[0]["clashReason"])
