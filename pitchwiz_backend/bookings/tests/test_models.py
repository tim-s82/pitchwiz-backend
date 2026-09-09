from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from bookings.models import (
    BookingChangeRequest,
    CateringRequest,
    Fixture,
    Pitch,
    PitchBooking,
    PitchLength,
    Team,
    Venue,
)

User = get_user_model()


class VenueModelTest(TestCase):
    def setUp(self):
        self.venue1 = Venue.objects.create(name="Main Ground", is_default=True)

    def test_venue_str(self):
        self.assertEqual(str(self.venue1), "Main Ground (Default)")

        non_default = Venue.objects.create(name="Training Ground", is_default=False)
        self.assertEqual(str(non_default), "Training Ground")

    def test_single_default_venue_enforcement(self):
        """Ensure that saving a new default venue unsets the previous default venue."""
        self.assertTrue(self.venue1.is_default)

        venue2 = Venue.objects.create(name="Second Ground", is_default=True)

        self.venue1.refresh_from_db()
        self.assertTrue(venue2.is_default)
        self.assertFalse(self.venue1.is_default)


class PitchLengthModelTest(TestCase):
    def setUp(self):
        self.length = PitchLength.objects.create(
            length_yards=22, description="Standard Senior Pitch"
        )

    def test_pitch_length_str(self):
        self.assertEqual(str(self.length), "22 Yards - Standard Senior Pitch")

    def test_length_yards_uniqueness(self):
        with self.assertRaises(IntegrityError):
            PitchLength.objects.create(
                length_yards=22, description="Duplicate Senior Pitch"
            )


class PitchModelTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Sports Complex")
        self.length = PitchLength.objects.create(length_yards=22, description="Senior")
        self.pitch1 = Pitch.objects.create(
            venue=self.venue,
            name="Pitch A",
            pitch_type="GRASS",
            entity_type="MAIN",
        )
        self.pitch2 = Pitch.objects.create(
            venue=self.venue,
            name="Pitch B",
            pitch_type="ASTRO",
            entity_type="NET",
        )

    def test_pitch_relationships(self):
        self.pitch1.supported_lengths.add(self.length)
        self.assertIn(self.length, self.pitch1.supported_lengths.all())

        # Test self-referential blocks_pitches M2M
        self.pitch1.blocks_pitches.add(self.pitch2)
        self.assertIn(self.pitch2, self.pitch1.blocks_pitches.all())
        self.assertNotIn(self.pitch1, self.pitch2.blocks_pitches.all())


class TeamModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="manager1", password="password123"
        )
        self.length = PitchLength.objects.create(length_yards=20, description="Junior")
        self.team = Team.objects.create(
            name="1st XI", is_external=False, required_length=self.length
        )
        self.team.managers.add(self.user)

    def test_team_str(self):
        self.assertEqual(str(self.team), "1st XI")

        external_team = Team.objects.create(name="Visiting Club", is_external=True)
        self.assertEqual(str(external_team), "Visiting Club (External)")

    def test_team_manager_relation(self):
        self.assertIn(self.user, self.team.managers.all())
        self.assertIn(self.team, self.user.managed_teams.all())


class FixtureModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Town CC",
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 15),
            play_cricket_id="PC12345",
        )

    def test_fixture_str(self):
        self.assertEqual(str(self.fixture), "1st XI vs Town CC")

    def test_play_cricket_id_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Fixture.objects.create(
                team=self.team,
                opponent="Other CC",
                start_date=date(2026, 6, 16),
                end_date=date(2026, 6, 16),
                play_cricket_id="PC12345",
            )


class PitchBookingModelTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground")
        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Pitch 1", pitch_type="GRASS"
        )
        self.team = Team.objects.create(name="1st XI")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Rovers CC",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
        )
        self.user = User.objects.create_user(username="booker", password="password")

    def test_standard_booking_str(self):
        booking = PitchBooking.objects.create(
            fixture=self.fixture,
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
            time_slot="AFTERNOON",
            requested_by=self.user,
        )
        # Assuming venue name + pitch name formatting
        self.assertIn("Pitch 1 on 2026-07-10 (Afternoon)", str(booking))

    def test_ground_maintenance_booking_str(self):
        maintenance = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="GROUND_MAINTENANCE",
            start_date=date(2026, 7, 11),
            end_date=date(2026, 7, 11),
            requested_by=self.user,
        )
        self.assertIn("Maintenance:", str(maintenance))


class CateringRequestModelTest(TestCase):
    def setUp(self):
        venue = Venue.objects.create(name="Ground")
        pitch = Pitch.objects.create(venue=venue, name="Pitch 1", pitch_type="GRASS")
        team = Team.objects.create(name="1st XI")
        fixture = Fixture.objects.create(
            team=team,
            opponent="CC",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )

        self.booking = PitchBooking.objects.create(
            pitch=pitch,
            booking_type="FIXTURE",
            fixture=fixture,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )
        self.catering = CateringRequest.objects.create(
            booking=self.booking,
            requires_teas=True,
            requires_drinks=True,
        )

    def test_catering_str(self):
        self.assertTrue(str(self.catering).startswith("Catering for"))


class BookingChangeRequestModelTest(TestCase):
    def setUp(self):
        venue = Venue.objects.create(name="Ground")
        pitch = Pitch.objects.create(venue=venue, name="Pitch 1", pitch_type="GRASS")
        team = Team.objects.create(name="1st XI")
        fixture = Fixture.objects.create(
            team=team,
            opponent="CC",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )

        self.booking = PitchBooking.objects.create(
            pitch=pitch,
            booking_type="FIXTURE",
            fixture=fixture,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )
        self.user = User.objects.create_user(username="secretary", password="password")
        self.change_request = BookingChangeRequest.objects.create(
            original_booking=self.booking,
            requested_by=self.user,
            new_start_date=date(2026, 8, 2),
            new_end_date=date(2026, 8, 2),
        )

    def test_change_request_str(self):
        self.assertTrue(str(self.change_request).startswith("Change Request for"))
