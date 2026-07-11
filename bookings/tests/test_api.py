from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from bookings.models import Venue, Pitch, PitchLength, Team, Fixture, PitchBooking
from django.contrib.auth.models import User
from datetime import date


class VenueAPITest(APITestCase):
    def setUp(self):
        self.venue1 = Venue.objects.create(name="Main Ground")
        self.venue2 = Venue.objects.create(name="School Ground")
        # DRF ViewSets automatically create URL names like 'venue-list'
        self.url = reverse("venue-list")

    def test_get_venues_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that both venues are returned in the JSON response
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["name"], "Main Ground")


class PitchAPITest(APITestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Main Ground")
        self.length_19 = PitchLength.objects.create(
            length_yards=19, description="19 Yards"
        )

        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Pitch 1", pitch_type="GRASS"
        )
        self.pitch.supported_lengths.add(self.length_19)
        self.url = reverse("pitch-list")

    def test_get_pitches_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Pitch 1")
        # Ensure the relationship returns the venue ID
        self.assertEqual(response.data[0]["venue"], self.venue.id)


class TeamAPITest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="testmanager", password="password"
        )
        self.pitch_length_19 = PitchLength.objects.create(
            length_yards=19, description="19 Yards"
        )

        self.team1 = Team.objects.create(
            name="U13s Boys",
            manager=self.manager,
            required_length=self.pitch_length_19,
            is_external=False,
        )
        self.team2 = Team.objects.create(name="Dorset Cricket", is_external=True)
        self.url = reverse("team-list")

    def test_get_teams_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Check internal team data
        self.assertEqual(response.data[0]["name"], "U13s Boys")
        self.assertFalse(response.data[0]["is_external"])
        self.assertEqual(response.data[0]["required_length"], self.pitch_length_19.id)

        # Check external team data
        self.assertEqual(response.data[1]["name"], "Dorset Cricket")
        self.assertTrue(response.data[1]["is_external"])
        self.assertIsNone(
            response.data[1]["required_length"]
        )  # External teams might not have a required length


class FixtureAPITest(APITestCase):
    def setUp(self):
        self.team = Team.objects.create(name="1st XI")
        self.fixture1 = Fixture.objects.create(
            team=self.team,
            opponent="Opponent A",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1),
            play_cricket_id="PC001",
        )
        self.fixture2 = Fixture.objects.create(
            team=self.team,
            opponent="Opponent B",
            start_date=date(2026, 6, 5),
            end_date=date(2026, 6, 7),  # Multi-day fixture
            play_cricket_id="PC002",
        )
        self.url = reverse("fixture-list")

    def test_get_fixtures_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        self.assertEqual(response.data[0]["opponent"], "Opponent A")
        self.assertEqual(response.data[0]["start_date"], "2026-06-01")
        self.assertEqual(response.data[0]["end_date"], "2026-06-01")
        self.assertEqual(response.data[0]["play_cricket_id"], "PC001")
        self.assertEqual(response.data[0]["team"], self.team.id)

        self.assertEqual(response.data[1]["opponent"], "Opponent B")
        self.assertEqual(response.data[1]["start_date"], "2026-06-05")
        self.assertEqual(response.data[1]["end_date"], "2026-06-07")


class PitchBookingAPITest(APITestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Main Ground")
        self.pitch = Pitch.objects.create(
            venue=self.venue, name="Pitch 1", pitch_type="GRASS"
        )
        self.team = Team.objects.create(name="U15s")
        self.fixture = Fixture.objects.create(
            team=self.team,
            opponent="Opponent C",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
        )
        self.user = User.objects.create_user(username="fixturesec", password="password")

        self.booking1 = PitchBooking.objects.create(
            fixture=self.fixture,
            pitch=self.pitch,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
            time_slot="AFTERNOON",
            requires_teas=True,
            requires_drinks=False,
            requested_by=self.user,
            status="PENDING",
        )
        self.booking2 = PitchBooking.objects.create(
            pitch=self.pitch,
            start_date=date(2026, 7, 15),
            end_date=date(2026, 7, 17),
            time_slot="ALL_DAY",
            external_contact_name="John Doe",
            external_contact_email="john@example.com",
            status="APPROVED",
        )
        self.url = reverse("pitchbooking-list")

    def test_get_pitch_bookings_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Check booking1 data
        self.assertEqual(response.data[0]["fixture"], self.fixture.id)
        self.assertEqual(response.data[0]["pitch"], self.pitch.id)
        self.assertEqual(response.data[0]["start_date"], "2026-07-10")
        self.assertEqual(response.data[0]["end_date"], "2026-07-10")
        self.assertEqual(response.data[0]["time_slot"], "AFTERNOON")
        self.assertTrue(response.data[0]["requires_teas"])
        self.assertFalse(response.data[0]["requires_drinks"])
        self.assertEqual(response.data[0]["requested_by"], self.user.id)
        self.assertEqual(response.data[0]["status"], "PENDING")
        self.assertEqual(
            response.data[0]["external_contact_name"], ""
        )  # Should be empty for internal booking

        # Check booking2 data (external, multi-day)
        self.assertIsNone(response.data[1]["fixture"])
        self.assertEqual(response.data[1]["start_date"], "2026-07-15")
        self.assertEqual(response.data[1]["end_date"], "2026-07-17")
        self.assertEqual(response.data[1]["time_slot"], "ALL_DAY")
        self.assertEqual(response.data[1]["external_contact_name"], "John Doe")
        self.assertEqual(response.data[1]["status"], "APPROVED")
