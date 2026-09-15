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

    def test_import_fixtures_csv_upload(self):
        url = reverse("import-fixtures")
        self.client.force_authenticate(user=self.secretary_user)

        csv_content = (
            "team,opponent,date,time,pitch_preference\n" "1st XI,Test CC,2026-08-01,14:00,Pitch 1"
        )
        file_obj = BytesIO(csv_content.encode("utf-8"))
        file_obj.name = "fixtures.csv"

        response = self.client.post(url, {"file": file_obj}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["imported_count"], 1)
        self.assertEqual(Fixture.objects.count(), 2)

    def test_import_fixtures_missing_file(self):
        url = reverse("import-fixtures")
        self.client.force_authenticate(user=self.secretary_user)

        response = self.client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], "No file uploaded.")


class PlayCricketSyncViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="adminuser", password="password123")
        self.client.force_authenticate(user=self.user)
        self.url = reverse("sync-play-cricket")

        # Create a sample local team matching the mock data
        self.local_team = Team.objects.create(name="Friendly XI")

    @patch("requests.get")
    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", "3540", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", "xxxxxx", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_URL", "http://play-cricket.com", create=True)
    def test_successful_sync_new_and_updated_fixtures(self, mock_get):
        # Mock response containing a new fixture and an existing fixture to update
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": 5681166,
                    "match_date": "08/04/2023",
                    "home_team_name": "Friendly XI",
                    "away_team_name": "Fillongley CC",
                },
                {
                    "id": 5580570,
                    "match_date": "16/04/2023",
                    "home_team_name": "Friendly XI",
                    "away_team_name": "Barby CC, Northants",
                },
            ]
        }

        # Pre-create one fixture to test update idempotency
        Fixture.objects.create(
            team=self.local_team,
            opponent="Old Opponent",
            start_date=date(2023, 4, 16),
            end_date=date(2023, 4, 16),
            play_cricket_id="5580570",
        )

        response = self.client.post(self.url, {"season": "2023"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["synced_count"], 1)  # ID 5681166 created
        self.assertEqual(data["updated_count"], 1)  # ID 5580570 updated
        self.assertEqual(data["skipped_count"], 0)
        self.assertEqual(data["errors"], [])

        # Verify database state
        f_new = Fixture.objects.get(play_cricket_id="5681166")
        self.assertEqual(f_new.opponent, "Fillongley CC")
        self.assertEqual(f_new.start_date, date(2023, 4, 8))

        f_updated = Fixture.objects.get(play_cricket_id="5580570")
        self.assertEqual(f_updated.opponent, "Barby CC, Northants")  # Updated from Old Opponent

    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", None, create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", None, create=True)
    def test_missing_configuration(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not configured", response.json()["detail"])

    @patch("requests.get")
    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", "3540", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", "xxxxxx", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_URL", "http://play-cricket.com", create=True)
    def test_api_http_error(self, mock_get):
        mock_response = mock_get.return_value
        mock_response.status_code = 502

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("Play-Cricket API error", response.json()["detail"])

    @patch("requests.get")
    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", "3540", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", "xxxxxx", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_URL", "http://play-cricket.com", create=True)
    def test_empty_result_set(self, mock_get):
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {"matches": []}

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["synced_count"], 0)
        self.assertEqual(data["updated_count"], 0)
        self.assertEqual(data["skipped_count"], 0)

    @patch("requests.get")
    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", "3540", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", "xxxxxx", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_URL", "http://play-cricket.com", create=True)
    def test_unmatched_teams_skipped(self, mock_get):
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": 9999999,
                    "match_date": "10/05/2023",
                    "home_team_name": "Unknown Club Team A",
                    "away_team_name": "Unknown Club Team B",
                }
            ]
        }

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["skipped_count"], 1)
        self.assertEqual(data["synced_count"], 0)
        self.assertEqual(Fixture.objects.count(), 0)

    @patch("requests.get")
    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", "3540", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", "xxxxxx", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_URL", "http://play-cricket.com", create=True)
    def test_invalid_date_format_handling(self, mock_get):
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "matches": [
                {
                    "id": 8888888,
                    "match_date": "2023-04-08",  # Malformed (ISO instead of DD/MM/YYYY)
                    "home_team_name": "Friendly XI",
                    "away_team_name": "Fillongley CC",
                }
            ]
        }

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("Invalid date format", data["errors"][0])
        self.assertEqual(data["synced_count"], 0)

    @patch("requests.get")
    @patch("django.conf.settings.PLAY_CRICKET_SITE_ID", "3540", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_API_KEY", "xxxxxx", create=True)
    @patch("django.conf.settings.PLAY_CRICKET_URL", "http://play-cricket.com", create=True)
    def test_connection_exception(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("Connection timeout")

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("Failed to connect to Play-Cricket", response.json()["detail"])
