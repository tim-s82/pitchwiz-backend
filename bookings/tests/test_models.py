from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from bookings.models import Fixture, Pitch, PitchBooking, PitchLength, Team, Venue

User = get_user_model()


class VenueModelTest(TestCase):
    def test_create_venue(self):
        venue = Venue.objects.create(name="Main Ground")
        self.assertEqual(venue.name, "Main Ground")
        self.assertEqual(str(venue), "Main Ground")


class PitchLengthModelTest(TestCase):
    def test_create_pitch_length(self):
        length = PitchLength.objects.create(
            length_yards=19, description="19 Yards (U12/U13)"
        )
        self.assertEqual(length.length_yards, 19)
        self.assertEqual(str(length), "19 Yards - 19 Yards (U12/U13)")


class PitchModelTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="School Ground")
        self.length_19 = PitchLength.objects.create(
            length_yards=19, description="19 Yards"
        )
        self.length_22 = PitchLength.objects.create(
            length_yards=22, description="22 Yards"
        )

    def test_create_pitch_with_lengths(self):
        pitch = Pitch.objects.create(
            venue=self.venue, name="Pitch 1", pitch_type="ASTRO", is_active=True
        )
        pitch.supported_lengths.add(self.length_19, self.length_22)

        self.assertEqual(pitch.name, "Pitch 1")
        self.assertEqual(pitch.pitch_type, "ASTRO")
        self.assertTrue(pitch.is_active)
        self.assertEqual(pitch.supported_lengths.count(), 2)
        self.assertEqual(str(pitch), "School Ground - Pitch 1")

    def test_pitch_blocking_logic(self):
        main_pitch = Pitch.objects.create(
            venue=self.venue, name="Main Grass", pitch_type="GRASS"
        )
        outfield_pitch = Pitch.objects.create(
            venue=self.venue, name="Outfield Astro", pitch_type="ASTRO"
        )

        main_pitch.blocks_pitches.add(outfield_pitch)

        self.assertIn(outfield_pitch, main_pitch.blocks_pitches.all())


class TeamModelTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager1", password="pw")
        self.length_19 = PitchLength.objects.create(
            length_yards=19, description="19 Yards"
        )

    def test_create_internal_team(self):
        team = Team.objects.create(name="U13s Boys", required_length=self.length_19)
        team.managers.add(self.manager)
        self.assertEqual(team.name, "U13s Boys")
        self.assertFalse(team.is_external)
        self.assertEqual(str(team), "U13s Boys")

    def test_create_external_team(self):
        team = Team.objects.create(name="Dorset Cricket", is_external=True)
        self.assertTrue(team.is_external)
        self.assertEqual(str(team), "Dorset Cricket (External)")


class FixtureModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")

    def test_create_fixture(self):
        fixture = Fixture.objects.create(
            team=self.team,
            opponent="Westbourne CC",
            start_date=date(2026, 5, 16),
            end_date=date(2026, 5, 16),
            play_cricket_id="PC12345",
        )
        self.assertEqual(fixture.opponent, "Westbourne CC")
        self.assertEqual(str(fixture), "1st XI vs Westbourne CC")


class PitchBookingModelTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Main Ground")
        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Pitch 1", pitch_type="GRASS"
        )
        self.team = Team.objects.create(name="2nd XI")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Broadstone CC",
            start_date=date(2026, 5, 17),
            end_date=date(2026, 5, 17),
        )

    def test_create_internal_booking(self):
        booking = PitchBooking.objects.create(
            fixture=self.fixture,
            pitch=self.pitch,
            start_date=date(2026, 5, 17),
            end_date=date(2026, 5, 17),
            time_slot="AFTERNOON",
            requires_teas=True,
        )
        self.assertTrue(booking.requires_teas)
        self.assertFalse(booking.requires_drinks)
        self.assertEqual(booking.status, "PENDING")
        self.assertEqual(
            str(booking), "Main Ground - Pitch 1 on 2026-05-17 (Afternoon)"
        )

    def test_create_external_booking_multi_day(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 12),
            time_slot="ALL_DAY",
            external_contact_name="John Doe",
            external_contact_email="john@dorsetcricket.org",
        )
        self.assertEqual(booking.external_contact_name, "John Doe")
        self.assertEqual(
            str(booking), "Main Ground - Pitch 1 from 2026-06-10 to 2026-06-12"
        )
