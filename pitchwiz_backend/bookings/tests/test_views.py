"""
Comprehensive unit tests for bookings/views.py

Covers:
  - health_check
  - Role-based permission enforcement across ViewSets
  - PitchBookingViewSet: standard booking, ground maintenance multi-pitch,
    conflict auto-cancellation, perform_create auto-approval logic,
    update_status secretary action
  - CateringRequestViewSet: caterer-only write access
  - BookingChangeRequestViewSet: secretary-only write access
  - preview_spreadsheet_fixtures_view: empty input, row normalization,
    time slot derivation, clash detection
  - preview_play_cricket_fixtures_view: missing config, mock API success,
    API error responses, connection errors
  - commit_fixtures_import_view: empty input, missing fields, Play-Cricket
    idempotency, standard get_or_create, auto pitch booking creation
"""

from datetime import date
from unittest.mock import MagicMock, patch

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
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(username, roles=None, is_superuser=False):
    """Create a User with the given roles list."""
    user = User.objects.create_user(username=username, password="password")
    user.roles = roles or []
    if is_superuser:
        user.is_superuser = True
    user.save()
    return user


def _base_fixture_setup(test_case):
    """Shared setup for tests that need a Venue, Pitch, Team and Fixture."""
    test_case.venue = Venue.objects.create(name="Main Ground")
    test_case.pitch = Pitch.objects.create(
        venue=test_case.venue, name="Pitch 1", pitch_type="GRASS"
    )
    test_case.team = Team.objects.create(name="1st XI")
    test_case.fixture = Fixture.objects.create(
        team=test_case.team,
        opponent="Wanderers CC",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 20),
    )


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class HealthCheckTest(APITestCase):
    def test_returns_200_and_awake_status(self):
        url = reverse("health_check")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "awake"})


# ---------------------------------------------------------------------------
# Role-based permission tests for management ViewSets
# ---------------------------------------------------------------------------


class VenueViewSetPermissionTest(APITestCase):
    def setUp(self):
        self.url = reverse("venue-list")
        self.venue = Venue.objects.create(name="Test Ground")
        self.payload = {"name": "New Ground", "is_default": False}

    def test_unauthenticated_cannot_create(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_external_user_cannot_create(self):
        user = _make_user("external", roles=["EXTERNAL"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_manager_can_create(self):
        user = _make_user("manager", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_fixture_secretary_can_create(self):
        user = _make_user("secretary", roles=["FIXTURE_SECRETARY"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_groundstaff_can_create(self):
        user = _make_user("groundstaff", roles=["GROUNDSTAFF"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_superuser_can_create(self):
        user = _make_user("superadmin", is_superuser=True)
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class PitchViewSetPermissionTest(APITestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Test Venue")
        self.url = reverse("pitch-list")
        self.payload = {"venue": self.venue.id, "name": "Pitch A", "pitch_type": "GRASS"}

    def test_unauthenticated_cannot_create(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_external_user_cannot_create(self):
        user = _make_user("ext", roles=["EXTERNAL"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create(self):
        user = _make_user("admin", roles=["ADMIN"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# FixtureViewSet permissions
# ---------------------------------------------------------------------------


class FixtureViewSetPermissionTest(APITestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")
        self.url = reverse("fixture-list")
        self.payload = {
            "team": self.team.id,
            "opponent": "Bournemouth CC",
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
        }

    def test_unauthenticated_cannot_create(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_list(self):
        user = _make_user("reader", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_management_user_can_create(self):
        user = _make_user("mgr", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_external_user_cannot_create(self):
        user = _make_user("ext", roles=["EXTERNAL"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# PitchBookingViewSet – standard fixture booking
# ---------------------------------------------------------------------------


class PitchBookingStandardTest(APITestCase):
    def setUp(self):
        _base_fixture_setup(self)
        self.url = reverse("pitchbooking-list")
        self.secretary = _make_user("secretary", roles=["FIXTURE_SECRETARY"])

    def test_standard_booking_succeeds(self):
        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "FIXTURE",
            "pitch": self.pitch.id,
            "fixture": self.fixture.id,
            "start_date": "2026-07-20",
            "end_date": "2026-07-20",
            "time_slot": "AFTERNOON",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PitchBooking.objects.count(), 1)

    def test_standard_booking_missing_pitch_returns_400(self):
        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "FIXTURE",
            "fixture": self.fixture.id,
            "start_date": "2026-07-20",
            "end_date": "2026-07-20",
            "time_slot": "AFTERNOON",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pitch", response.data)

    def test_unauthenticated_cannot_create_booking(self):
        payload = {
            "booking_type": "FIXTURE",
            "pitch": self.pitch.id,
            "fixture": self.fixture.id,
            "start_date": "2026-07-20",
            "end_date": "2026-07-20",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# PitchBookingViewSet – ground maintenance flow
# ---------------------------------------------------------------------------


class PitchBookingGroundMaintenanceTest(APITestCase):
    def setUp(self):
        _base_fixture_setup(self)
        self.url = reverse("pitchbooking-list")
        self.secretary = _make_user("secretary", roles=["FIXTURE_SECRETARY"])

    def test_maintenance_booking_created_with_approved_status(self):
        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "ALL_DAY",
            "notes": "Pitch rolling",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = PitchBooking.objects.get(booking_type="GROUND_MAINTENANCE")
        self.assertEqual(booking.status, "APPROVED")

    def test_maintenance_empty_pitches_returns_400(self):
        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "ALL_DAY",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pitches", response.data)

    def test_maintenance_auto_cancels_conflicting_bookings(self):
        """Existing PENDING/APPROVED bookings on the pitch should be DENIED."""
        # Create a pre-existing approved booking on the same pitch
        existing = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 25),
            end_date=date(2026, 7, 25),
            time_slot="AFTERNOON",
            status="APPROVED",
            requested_by=self.secretary,
        )

        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "ALL_DAY",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        existing.refresh_from_db()
        self.assertEqual(existing.status, "DENIED")
        self.assertIn("maintenance", existing.rejection_reason.lower())

    def test_maintenance_does_not_cancel_non_overlapping_booking(self):
        """Bookings on different dates should NOT be auto-cancelled."""
        non_conflicting = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            time_slot="AFTERNOON",
            status="APPROVED",
            requested_by=self.secretary,
        )

        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "ALL_DAY",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        non_conflicting.refresh_from_db()
        self.assertEqual(non_conflicting.status, "APPROVED")

    def test_maintenance_time_slot_conflict_same_slot(self):
        """MORNING maintenance should cancel an MORNING booking on the same date."""
        morning_booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 25),
            end_date=date(2026, 7, 25),
            time_slot="MORNING",
            status="PENDING",
            requested_by=self.secretary,
        )

        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "MORNING",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        morning_booking.refresh_from_db()
        self.assertEqual(morning_booking.status, "DENIED")

    def test_maintenance_time_slot_does_not_cancel_different_slot(self):
        """MORNING maintenance should NOT cancel an EVENING booking."""
        evening_booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 25),
            end_date=date(2026, 7, 25),
            time_slot="EVENING",
            status="PENDING",
            requested_by=self.secretary,
        )

        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "MORNING",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        evening_booking.refresh_from_db()
        self.assertEqual(evening_booking.status, "PENDING")

    def test_maintenance_multi_pitch(self):
        """Multiple pitches in a single maintenance request each get a booking."""
        pitch2 = Pitch.objects.create(venue=self.venue, name="Pitch 2", pitch_type="ASTRO")
        self.client.force_authenticate(user=self.secretary)
        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id, pitch2.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "ALL_DAY",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PitchBooking.objects.filter(booking_type="GROUND_MAINTENANCE").count(), 2)


# ---------------------------------------------------------------------------
# PitchBookingViewSet – perform_create auto-approval
# ---------------------------------------------------------------------------


class PitchBookingAutoApprovalTest(APITestCase):
    def setUp(self):
        _base_fixture_setup(self)
        self.url = reverse("pitchbooking-list")

    def _standard_payload(self):
        return {
            "booking_type": "FIXTURE",
            "pitch": self.pitch.id,
            "fixture": self.fixture.id,
            "start_date": "2026-07-20",
            "end_date": "2026-07-20",
            "time_slot": "AFTERNOON",
        }

    def test_fixture_secretary_booking_auto_approved(self):
        user = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self._standard_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = PitchBooking.objects.first()
        self.assertEqual(booking.status, "APPROVED")

    def test_admin_booking_auto_approved(self):
        user = _make_user("admin", roles=["ADMIN"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self._standard_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PitchBooking.objects.first().status, "APPROVED")

    def test_groundstaff_booking_auto_approved(self):
        user = _make_user("gs", roles=["GROUNDSTAFF"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self._standard_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PitchBooking.objects.first().status, "APPROVED")

    def test_team_manager_booking_is_pending(self):
        user = _make_user("tm", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, self._standard_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PitchBooking.objects.first().status, "PENDING")

    def test_booking_created_with_correct_requested_by(self):
        user = _make_user("sec2", roles=["FIXTURE_SECRETARY"])
        self.client.force_authenticate(user=user)
        self.client.post(self.url, self._standard_payload(), format="json")
        booking = PitchBooking.objects.first()
        self.assertEqual(booking.requested_by, user)


# ---------------------------------------------------------------------------
# PitchBookingViewSet – update_status action
# ---------------------------------------------------------------------------


class UpdateStatusActionTest(APITestCase):
    def setUp(self):
        _base_fixture_setup(self)
        self.secretary = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.manager = _make_user("mgr", roles=["TEAM_MANAGER"])
        self.booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
            time_slot="AFTERNOON",
            status="PENDING",
            requested_by=self.manager,
        )
        self.url = reverse("pitchbooking-update-status", kwargs={"pk": self.booking.pk})

    def test_secretary_can_approve_booking(self):
        self.client.force_authenticate(user=self.secretary)
        response = self.client.patch(self.url, {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "APPROVED")

    def test_secretary_can_deny_booking_with_reason(self):
        self.client.force_authenticate(user=self.secretary)
        response = self.client.patch(
            self.url,
            {"status": "DENIED", "rejection_reason": "Pitch unavailable"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "DENIED")
        self.assertEqual(self.booking.rejection_reason, "Pitch unavailable")

    def test_invalid_status_returns_400(self):
        self.client.force_authenticate(user=self.secretary)
        response = self.client.patch(self.url, {"status": "INVALID_STATUS"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_team_manager_cannot_update_status(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.patch(self.url, {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_update_status(self):
        response = self.client.patch(self.url, {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# CateringRequestViewSet – permissions
# ---------------------------------------------------------------------------


class CateringRequestViewSetPermissionTest(APITestCase):
    def setUp(self):
        _base_fixture_setup(self)
        self.sec = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
            time_slot="AFTERNOON",
            status="APPROVED",
            requested_by=self.sec,
        )
        self.url = reverse("catering-request-list")
        self.payload = {
            "booking": self.booking.id,
            "requires_teas": True,
            "requires_drinks": False,
        }

    def test_caterer_can_create(self):
        caterer = _make_user("caterer", roles=["CATERER"])
        self.client.force_authenticate(user=caterer)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_caterer_cannot_create(self):
        manager = _make_user("mgr", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=manager)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_can_list(self):
        user = _make_user("reader", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# BookingChangeRequestViewSet – permissions
# ---------------------------------------------------------------------------


class BookingChangeRequestViewSetPermissionTest(APITestCase):
    def setUp(self):
        _base_fixture_setup(self)
        self.sec = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.booking = PitchBooking.objects.create(
            pitch=self.pitch,
            booking_type="FIXTURE",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
            time_slot="AFTERNOON",
            status="APPROVED",
            requested_by=self.sec,
        )
        self.url = reverse("booking-change-request-list")
        self.payload = {
            "original_booking": self.booking.id,
            "requested_by": self.sec.id,
            "new_start_date": "2026-07-22",
            "new_end_date": "2026-07-22",
        }

    def test_fixture_secretary_can_create(self):
        self.client.force_authenticate(user=self.sec)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_team_manager_cannot_create(self):
        mgr = _make_user("mgr", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=mgr)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_list(self):
        user = _make_user("reader", roles=["TEAM_MANAGER"])
        self.client.force_authenticate(user=user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# preview_spreadsheet_fixtures_view
# ---------------------------------------------------------------------------


class PreviewSpreadsheetFixturesViewTest(APITestCase):
    def setUp(self):
        self.url = reverse("preview-spreadsheet-fixtures")
        self.user = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.client.force_authenticate(user=self.user)
        self.venue = Venue.objects.create(name="Home Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Main Pitch", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")

    def test_empty_rows_returns_400(self):
        response = self.client.post(self.url, {"rows": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_access(self):
        self.client.logout()
        response = self.client.post(self.url, {"rows": [{"team": "1st XI"}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_row_returns_processed_result(self):
        row = {
            "team": "1st XI",
            "opponent": "Poole CC",
            "date": "2026-08-01",
            "time": "14:00",
            "pitch": "Main Pitch",
        }
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        processed = response.data["rows"][0]
        self.assertEqual(processed["opponent"], "Poole CC")
        self.assertEqual(processed["date"], "2026-08-01")

    def test_alternate_column_headers_normalised(self):
        """Checks that "Club Team" and "Opposition" columns are understood."""
        row = {
            "Club Team": "1st XI",
            "Opposition": "Dorset CC",
            "Match Date": "2026-09-01",
            "Start Time": "10:30",
        }
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        processed = response.data["rows"][0]
        self.assertEqual(processed["opponent"], "Dorset CC")
        self.assertEqual(processed["teamNameRaw"], "1st XI")

    def test_morning_time_slot_derivation(self):
        row = {
            "team": "1st XI",
            "opponent": "Test CC",
            "date": "2026-08-01",
            "time": "09:30",
        }
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.data["rows"][0]["timeSlot"], "MORNING")

    def test_afternoon_time_slot_derivation(self):
        row = {
            "team": "1st XI",
            "opponent": "Test CC",
            "date": "2026-08-01",
            "time": "14:00",
        }
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.data["rows"][0]["timeSlot"], "AFTERNOON")

    def test_evening_time_slot_derivation(self):
        row = {
            "team": "1st XI",
            "opponent": "Test CC",
            "date": "2026-08-01",
            "time": "18:00",
        }
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.data["rows"][0]["timeSlot"], "EVENING")

    def test_missing_team_sets_clash_reason(self):
        row = {"opponent": "Test CC", "date": "2026-08-01"}
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        processed = response.data["rows"][0]
        self.assertIsNotNone(processed["clashReason"])
        self.assertIn("team", processed["clashReason"].lower())

    def test_missing_opponent_sets_clash_reason(self):
        row = {"team": "1st XI", "date": "2026-08-01"}
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        processed = response.data["rows"][0]
        self.assertIsNotNone(processed["clashReason"])
        self.assertIn("opponent", processed["clashReason"].lower())

    def test_missing_date_sets_clash_reason(self):
        row = {"team": "1st XI", "opponent": "Test CC"}
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        processed = response.data["rows"][0]
        self.assertIsNotNone(processed["clashReason"])
        self.assertIn("date", processed["clashReason"].lower())

    def test_valid_row_is_selected_by_default(self):
        row = {"team": "1st XI", "opponent": "Test CC", "date": "2026-08-01"}
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertTrue(response.data["rows"][0]["selected"])

    def test_invalid_row_is_not_selected(self):
        row = {"opponent": "Test CC", "date": "2026-08-01"}  # missing team
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertFalse(response.data["rows"][0]["selected"])


# ---------------------------------------------------------------------------
# preview_play_cricket_fixtures_view
# ---------------------------------------------------------------------------


class PreviewPlayCricketFixturesViewTest(APITestCase):
    def setUp(self):
        self.url = reverse("preview-play-cricket-fixtures")
        self.user = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.client.force_authenticate(user=self.user)
        self.venue = Venue.objects.create(name="Home Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Main Pitch", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")

    def test_missing_config_returns_400(self):
        with self.settings(PLAY_CRICKET_SITE_ID=None, PLAY_CRICKET_API_KEY=None):
            response = self.client.post(self.url, {"season": 2026}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("configured", response.data["detail"])

    def test_unauthenticated_cannot_access(self):
        self.client.logout()
        response = self.client.post(self.url, {"season": 2026}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("bookings.views.requests.get")
    def test_successful_api_response_processed(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": "12345",
                    "home_team_name": "1st XI",
                    "away_team_name": "Poole CC",
                    "match_date": "01/08/2026",
                    "match_time": "14:00",
                    "ground_name": "Home Ground Main Pitch",
                    "ground_id": "99",
                }
            ]
        }
        mock_get.return_value = mock_response

        with self.settings(PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc"):
            response = self.client.post(self.url, {"season": 2026}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        row = response.data["rows"][0]
        self.assertEqual(row["playCricketId"], "12345")
        self.assertEqual(row["opponent"], "Poole CC")
        self.assertEqual(row["date"], "2026-08-01")

    @patch("bookings.views.requests.get")
    def test_api_date_parsing_failure_sets_clash_reason(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": "99",
                    "home_team_name": "1st XI",
                    "away_team_name": "Test CC",
                    "match_date": "NOT-A-DATE",
                    "match_time": "14:00",
                    "ground_name": "",
                    "ground_id": "",
                }
            ]
        }
        mock_get.return_value = mock_response

        with self.settings(PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc"):
            response = self.client.post(self.url, {"season": 2026}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        self.assertIsNotNone(row["clashReason"])
        self.assertIn("date", row["clashReason"].lower())

    @patch("bookings.views.requests.get")
    def test_upstream_api_non_200_returns_502(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        with self.settings(PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc"):
            response = self.client.post(self.url, {"season": 2026}, format="json")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    @patch("bookings.views.requests.get")
    def test_request_exception_returns_500(self, mock_get):
        import requests as req_lib

        mock_get.side_effect = req_lib.RequestException("Connection refused")

        with self.settings(PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc"):
            response = self.client.post(self.url, {"season": 2026}, format="json")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("Failed to connect", response.data["detail"])

    @patch("bookings.views.requests.get")
    def test_time_slot_derivation_morning(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": "1",
                    "home_team_name": "1st XI",
                    "away_team_name": "Test CC",
                    "match_date": "01/08/2026",
                    "match_time": "09:00",
                    "ground_name": "",
                    "ground_id": "",
                }
            ]
        }
        mock_get.return_value = mock_response

        with self.settings(PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc"):
            response = self.client.post(self.url, {"season": 2026}, format="json")

        self.assertEqual(response.data["rows"][0]["timeSlot"], "MORNING")

    @patch("bookings.views.requests.get")
    def test_time_slot_derivation_evening(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": "2",
                    "home_team_name": "1st XI",
                    "away_team_name": "Test CC",
                    "match_date": "01/08/2026",
                    "match_time": "18:30",
                    "ground_name": "",
                    "ground_id": "",
                }
            ]
        }
        mock_get.return_value = mock_response

        with self.settings(PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc"):
            response = self.client.post(self.url, {"season": 2026}, format="json")

        self.assertEqual(response.data["rows"][0]["timeSlot"], "EVENING")


# ---------------------------------------------------------------------------
# commit_fixtures_import_view
# ---------------------------------------------------------------------------


class CommitFixturesImportViewTest(APITestCase):
    def setUp(self):
        self.url = reverse("commit-fixtures-import")
        self.user = _make_user("sec", roles=["FIXTURE_SECRETARY"])
        self.client.force_authenticate(user=self.user)
        self.venue = Venue.objects.create(name="Home Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")

    def _make_row(self, **overrides):
        row = {
            "teamId": self.team.id,
            "opponent": "Test CC",
            "date": "2026-08-01",
            "timeSlot": "AFTERNOON",
            "pitchId": None,
            "playCricketId": None,
            "time": "",
        }
        row.update(overrides)
        return row

    def test_empty_rows_returns_400(self):
        response = self.client.post(self.url, {"rows": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_access(self):
        self.client.logout()
        response = self.client.post(self.url, {"rows": [self._make_row()]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_row_creates_fixture(self):
        response = self.client.post(self.url, {"rows": [self._make_row()]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["synced_count"], 1)
        self.assertEqual(Fixture.objects.count(), 1)

    def test_missing_required_field_records_error(self):
        # Row missing 'opponent'
        row = {"teamId": self.team.id, "date": "2026-08-01"}
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["errors"]), 1)
        self.assertIn("Row 1", response.data["errors"][0])
        self.assertEqual(Fixture.objects.count(), 0)

    def test_invalid_team_id_records_error(self):
        row = self._make_row(teamId=99999)  # non-existent team
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["errors"]), 1)
        self.assertIn("Invalid team", response.data["errors"][0])

    def test_play_cricket_id_uses_update_or_create(self):
        """Same Play-Cricket ID submitted twice should not create a duplicate fixture."""
        row = self._make_row(playCricketId="PC-001")
        self.client.post(self.url, {"rows": [row]}, format="json")
        row2 = self._make_row(playCricketId="PC-001", opponent="Updated CC")
        response = self.client.post(self.url, {"rows": [row2]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Fixture.objects.count(), 1)
        self.assertEqual(response.data["updated_count"], 1)
        fixture = Fixture.objects.first()
        self.assertEqual(fixture.opponent, "Updated CC")

    def test_no_play_cricket_id_uses_get_or_create(self):
        """Same team/opponent/date submitted twice is idempotent."""
        row = self._make_row()
        self.client.post(self.url, {"rows": [row]}, format="json")
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Fixture.objects.count(), 1)
        self.assertEqual(response.data["updated_count"], 1)

    def test_pitch_id_creates_approved_pitch_booking(self):
        row = self._make_row(pitchId=self.pitch.id)
        response = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        fixture = Fixture.objects.first()
        booking = PitchBooking.objects.filter(fixture=fixture).first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.status, "APPROVED")
        self.assertEqual(booking.pitch, self.pitch)

    def test_no_pitch_id_does_not_create_booking(self):
        row = self._make_row(pitchId=None)
        self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(PitchBooking.objects.count(), 0)

    def test_multiple_rows_processed_together(self):
        team2 = Team.objects.create(name="2nd XI")
        rows = [
            self._make_row(opponent="Team A"),
            self._make_row(teamId=team2.id, opponent="Team B", date="2026-08-02"),
        ]
        response = self.client.post(self.url, {"rows": rows}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Fixture.objects.count(), 2)
        self.assertEqual(response.data["synced_count"], 2)

    def test_booking_time_str_included_in_notes(self):
        row = self._make_row(pitchId=self.pitch.id, time="14:30")
        self.client.post(self.url, {"rows": [row]}, format="json")
        booking = PitchBooking.objects.first()
        self.assertIn("14:30", booking.notes)

    def test_booking_without_time_str_has_generic_notes(self):
        row = self._make_row(pitchId=self.pitch.id, time="")
        self.client.post(self.url, {"rows": [row]}, format="json")
        booking = PitchBooking.objects.first()
        self.assertEqual(booking.notes, "Imported Fixture")
