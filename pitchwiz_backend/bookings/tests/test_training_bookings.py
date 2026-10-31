"""
Unit and integration tests for Training Session bookings.
Covers:
- Model: TRAINING choice accepted, teams M2M persistence, __str__ representation
- Serializer: validation with/without fixture, pitch requirement, teams M2M round-trip
- ViewSet: role permissions (team manager own vs unmanaged vs empty teams, fixture secretary, admin club-wide),
  auto-approval logic, fixture rejection.
"""

from datetime import date

from bookings.models import Fixture, Pitch, PitchBooking, Team, Venue
from bookings.serializers import PitchBookingSerializer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.test import APITestCase

User = get_user_model()


def _make_user(username, roles=None, is_superuser=False):
    user = User.objects.create_user(username=username, password="password123")
    user.roles = roles or []
    if is_superuser:
        user.is_superuser = True
    user.save()
    return user


class TrainingBookingModelTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground A")
        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Net 1", pitch_type="ASTRO", entity_type="NET"
        )
        self.team1 = Team.objects.create(name="1st XI")
        self.team2 = Team.objects.create(name="2nd XI")

    def test_model_training_choice_accepted(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="TRAINING",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
            time_slot="EVENING",
        )
        self.assertEqual(booking.booking_type, "TRAINING")
        self.assertEqual(booking.status, "PENDING")

    def test_model_teams_m2m_persists(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="TRAINING",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
            time_slot="EVENING",
        )
        booking.teams.set([self.team1, self.team2])
        self.assertEqual(booking.teams.count(), 2)
        self.assertIn(self.team1, booking.teams.all())
        self.assertIn(self.team2, booking.teams.all())

    def test_model_training_str_with_teams_and_club_wide(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="TRAINING",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
            time_slot="EVENING",
        )
        self.assertEqual(str(booking), f"Training (Club-wide): {self.pitch} on 2026-05-10")

        booking.teams.set([self.team1, self.team2])
        self.assertEqual(str(booking), f"Training (1st XI, 2nd XI): {self.pitch} on 2026-05-10")


class TrainingBookingSerializerTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground A")
        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Net 1", pitch_type="ASTRO", entity_type="NET"
        )
        self.team1 = Team.objects.create(name="1st XI")
        self.team2 = Team.objects.create(name="2nd XI")
        self.fixture = Fixture.objects.create(
            team=self.team1,
            opponent="Opponent CC",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
        )

    def test_serializer_validates_without_fixture(self):
        data = {
            "pitch": self.pitch.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [self.team1.id, self.team2.id],
        }
        serializer = PitchBookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNone(instance.fixture)
        self.assertEqual(instance.teams.count(), 2)

    def test_serializer_rejects_fixture_on_training(self):
        data = {
            "pitch": self.pitch.id,
            "fixture": self.fixture.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [self.team1.id],
        }
        serializer = PitchBookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("fixture", serializer.errors)
        self.assertIn(
            "Training bookings cannot be linked to a fixture.",
            serializer.errors["fixture"],
        )

    def test_serializer_requires_pitch_on_training(self):
        data = {
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [self.team1.id],
        }
        serializer = PitchBookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("pitch", serializer.errors)

    def test_serializer_teams_ids_round_trip(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="TRAINING",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
            time_slot="EVENING",
        )
        booking.teams.set([self.team1, self.team2])
        serializer = PitchBookingSerializer(booking)
        self.assertIn("teams", serializer.data)
        self.assertEqual(set(serializer.data["teams"]), {self.team1.id, self.team2.id})


class TrainingBookingViewTests(APITestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground A")
        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Net 1", pitch_type="ASTRO", entity_type="NET"
        )
        self.manager = _make_user("manager_bob", roles=["TEAM_MANAGER"])
        self.secretary = _make_user("sec_alice", roles=["FIXTURE_SECRETARY"])
        self.admin = _make_user("admin_charlie", roles=["ADMIN"])

        self.team_managed = Team.objects.create(name="Under 15s")
        self.team_managed.managers.add(self.manager)

        self.team_unmanaged = Team.objects.create(name="Under 13s")

        self.fixture = Fixture.objects.create(
            team=self.team_managed,
            opponent="Visitors CC",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
        )
        self.url = reverse("pitchbooking-list")

    def test_manager_books_own_team_returns_201_pending(self):
        self.client.force_authenticate(user=self.manager)
        payload = {
            "pitch": self.pitch.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [self.team_managed.id],
            "notes": "U15 Net practice",
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "PENDING")
        self.assertEqual(res.data["teams"], [self.team_managed.id])
        self.assertEqual(res.data["booking_type"], "TRAINING")

    def test_manager_books_unmanaged_team_returns_403(self):
        self.client.force_authenticate(user=self.manager)
        payload = {
            "pitch": self.pitch.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [self.team_unmanaged.id],
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("teams", res.data)

    def test_manager_empty_teams_returns_403(self):
        self.client.force_authenticate(user=self.manager)
        payload = {
            "pitch": self.pitch.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [],
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("teams", res.data)

    def test_secretary_books_any_teams_returns_201_approved(self):
        self.client.force_authenticate(user=self.secretary)
        payload = {
            "pitch": self.pitch.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [self.team_unmanaged.id],
            "notes": "Secretary booking",
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "APPROVED")
        self.assertEqual(res.data["teams"], [self.team_unmanaged.id])

    def test_admin_club_wide_empty_teams_returns_201_approved(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "pitch": self.pitch.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [],
            "notes": "All-club preseason training",
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "APPROVED")
        self.assertEqual(res.data["teams"], [])

    def test_view_fixture_provided_on_training_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "pitch": self.pitch.id,
            "fixture": self.fixture.id,
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [],
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fixture", res.data)

    def test_view_missing_pitch_on_training_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "booking_type": "TRAINING",
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
            "time_slot": "EVENING",
            "teams": [],
        }
        res = self.client.post(self.url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pitch", res.data)
