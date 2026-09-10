from datetime import date

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
from bookings.serializers import (
    BookingChangeRequestSerializer,
    CateringRequestSerializer,
    FixtureSerializer,
    PitchBookingSerializer,
    PitchLengthSerializer,
    PitchSerializer,
    TeamSerializer,
    VenueSerializer,
)
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class VenueSerializerTest(TestCase):
    def test_serialization(self):
        venue = Venue.objects.create(name="Central Ground", is_default=True)
        serializer = VenueSerializer(venue)
        expected = {"id": venue.id, "name": "Central Ground", "is_default": True}
        self.assertEqual(serializer.data, expected)

    def test_deserialization(self):
        data = {"name": "North Pavilion", "is_default": False}
        serializer = VenueSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        venue = serializer.save()
        self.assertEqual(venue.name, "North Pavilion")
        self.assertFalse(venue.is_default)


class PitchLengthSerializerTest(TestCase):
    def test_serialization(self):
        length = PitchLength.objects.create(length_yards=22, description="Senior Standard")
        serializer = PitchLengthSerializer(length)
        expected = {
            "id": length.id,
            "length_yards": 22,
            "description": "Senior Standard",
        }
        self.assertEqual(serializer.data, expected)


class PitchSerializerTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Sports Complex")
        self.pitch_length = PitchLength.objects.create(length_yards=22, description="Full")
        self.pitch = Pitch.objects.create(
            venue=self.venue,
            name="Pitch 1",
            pitch_type="GRASS",
            entity_type="MAIN",
        )
        self.pitch.supported_lengths.add(self.pitch_length)

    def test_serialization(self):
        serializer = PitchSerializer(self.pitch)
        data = serializer.data
        self.assertEqual(data["name"], "Pitch 1")
        self.assertEqual(data["venue"], self.venue.id)
        self.assertEqual(data["pitch_type"], "GRASS")
        self.assertEqual(data["entity_type"], "MAIN")
        self.assertIn(self.pitch_length.id, data["supported_lengths"])


class TeamSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="team_manager", password="password")
        self.length = PitchLength.objects.create(length_yards=18, description="Junior")
        self.team = Team.objects.create(
            name="Under 15s", required_length=self.length, is_external=False
        )
        self.team.managers.add(self.user)

    def test_serialization(self):
        serializer = TeamSerializer(self.team)
        data = serializer.data
        self.assertEqual(data["name"], "Under 15s")
        self.assertEqual(data["required_length"], self.length.id)
        self.assertIn(self.user.id, data["managers"])
        self.assertFalse(data["is_external"])


class FixtureSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Visitors CC",
            start_date=date(2026, 6, 20),
            end_date=date(2026, 6, 20),
            play_cricket_id="PC98765",
        )

    def test_serialization(self):
        serializer = FixtureSerializer(self.fixture)
        data = serializer.data
        self.assertEqual(data["team"], self.team.id)
        self.assertEqual(data["opponent"], "Visitors CC")
        self.assertEqual(data["play_cricket_id"], "PC98765")


class PitchBookingSerializerTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Home Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch A", pitch_type="GRASS")
        self.team = Team.objects.create(name="2nd XI")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Away CC",
            start_date=date(2026, 7, 5),
            end_date=date(2026, 7, 5),
        )

    def test_standard_booking_requires_pitch(self):
        """Standard fixture bookings must fail validation if 'pitch' is omitted."""
        data = {
            "fixture": self.fixture.id,
            "booking_type": "FIXTURE",
            "start_date": "2026-07-05",
            "end_date": "2026-07-05",
            "time_slot": "AFTERNOON",
        }
        serializer = PitchBookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("pitch", serializer.errors)
        self.assertEqual(
            serializer.errors["pitch"],
            ["This field is required for standard bookings."],
        )

    def test_standard_booking_valid(self):
        """Standard fixture bookings pass validation when a pitch is supplied."""
        data = {
            "fixture": self.fixture.id,
            "pitch": self.pitch.id,
            "booking_type": "FIXTURE",
            "start_date": "2026-07-05",
            "end_date": "2026-07-05",
            "time_slot": "AFTERNOON",
        }
        serializer = PitchBookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_ground_maintenance_bypasses_single_pitch_requirement(self):
        """Ground maintenance bookings use the write-only 'pitches' array and skip single pitch checks."""
        data = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
            "time_slot": "ALL_DAY",
            "notes": "Square aeration",
        }
        serializer = PitchBookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class CateringRequestSerializerTest(TestCase):
    def setUp(self):
        venue = Venue.objects.create(name="Ground")
        pitch = Pitch.objects.create(venue=venue, name="Pitch 1", pitch_type="GRASS")
        team = Team.objects.create(name="1st XI")
        fixture = Fixture.objects.create(
            team=team,
            opponent="CC",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
        )
        self.booking = PitchBooking.objects.create(
            pitch=pitch,
            booking_type="FIXTURE",
            fixture=fixture,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
        )

    def test_serialization(self):
        catering = CateringRequest.objects.create(
            booking=self.booking,
            requires_teas=True,
            requires_drinks=False,
            status="APPROVED",
        )
        serializer = CateringRequestSerializer(catering)
        self.assertEqual(serializer.data["booking"], self.booking.id)
        self.assertTrue(serializer.data["requires_teas"])
        self.assertEqual(serializer.data["status"], "APPROVED")


class BookingChangeRequestSerializerTest(TestCase):
    def setUp(self):
        venue = Venue.objects.create(name="Ground")
        pitch = Pitch.objects.create(venue=venue, name="Pitch 1", pitch_type="GRASS")
        team = Team.objects.create(name="1st XI")
        fixture = Fixture.objects.create(
            team=team,
            opponent="CC",
            start_date=date(2026, 8, 15),
            end_date=date(2026, 8, 15),
        )
        self.booking = PitchBooking.objects.create(
            pitch=pitch,
            booking_type="FIXTURE",
            fixture=fixture,
            start_date=date(2026, 8, 15),
            end_date=date(2026, 8, 15),
        )
        self.user = User.objects.create_user(username="secretary", password="password")

    def test_serialization(self):
        change_req = BookingChangeRequest.objects.create(
            original_booking=self.booking,
            requested_by=self.user,
            new_start_date=date(2026, 8, 16),
            new_end_date=date(2026, 8, 16),
            status="PENDING",
        )
        serializer = BookingChangeRequestSerializer(change_req)
        self.assertEqual(serializer.data["original_booking"], self.booking.id)
        self.assertEqual(serializer.data["requested_by"], self.user.id)
        self.assertEqual(serializer.data["new_start_date"], "2026-08-16")
