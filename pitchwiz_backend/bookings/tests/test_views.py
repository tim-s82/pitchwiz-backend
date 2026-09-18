from datetime import date
from io import BytesIO
from unittest.mock import patch

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


class PitchBookingWorkflowTest(APITestCase):
    def setUp(self):
        self.secretary_user = User.objects.create_user(username="secretary", password="password")
        self.secretary_user.roles = ["FIXTURE_SECRETARY"]
        self.secretary_user.save()

        self.venue = Venue.objects.create(name="Main Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Wanderers CC",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
        )

    def test_ground_maintenance_multi_pitch_creation(self):
        url = reverse("pitchbooking-list")
        self.client.force_authenticate(user=self.secretary_user)

        payload = {
            "booking_type": "GROUND_MAINTENANCE",
            "pitches": [self.pitch.id],
            "start_date": "2026-07-25",
            "end_date": "2026-07-25",
            "time_slot": "ALL_DAY",
            "notes": "Pitch rolling",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PitchBooking.objects.count(), 1)
        booking = PitchBooking.objects.first()
        self.assertEqual(booking.booking_type, "GROUND_MAINTENANCE")
        self.assertEqual(booking.status, "APPROVED")
