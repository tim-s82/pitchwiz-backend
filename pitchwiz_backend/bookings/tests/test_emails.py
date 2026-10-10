"""
TDD tests for bookings/emails.py

All tests use the locmem backend and opt-in EMAIL_ENABLED=True via override_settings.
The unit_test.py settings file sets EMAIL_ENABLED=False by default, so each test
class that wants to exercise real sending uses:

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_ENABLED=True,
        EMAIL_OVERRIDE_ADDRESS="",
        DEFAULT_FROM_EMAIL="test@pitchwiz.test",
    )
"""

from datetime import date

from bookings.emails import (
    _resolve_recipients,
    notify_caterers_new_catering_request,
    notify_manager_booking_status_changed,
    notify_managers_booking_evicted,
    notify_secretaries_external_request,
    notify_secretaries_new_booking,
)
from bookings.models import (
    CateringRequest,
    Fixture,
    Pitch,
    PitchBooking,
    Team,
    Venue,
)
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

User = get_user_model()

EMAIL_SETTINGS = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_ENABLED=True,
    EMAIL_OVERRIDE_ADDRESS="",
    DEFAULT_FROM_EMAIL="test@pitchwiz.test",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_secretary(username, email="secretary@example.com"):
    user = User.objects.create_user(username=username, email=email, password="Password1!")
    user.roles = ["FIXTURE_SECRETARY"]
    user.save()
    return user


def _make_manager(username, email="manager@example.com"):
    user = User.objects.create_user(username=username, email=email, password="Password1!")
    user.roles = ["TEAM_MANAGER"]
    user.save()
    return user


def _make_caterer(username, email="caterer@example.com"):
    user = User.objects.create_user(username=username, email=email, password="Password1!")
    user.roles = ["CATERER"]
    user.save()
    return user


def _make_booking(team, pitch, status="PENDING", external_name="", external_email=""):
    fixture = Fixture.objects.create(
        team=team,
        opponent="Test CC",
        start_date=date(2026, 6, 15),
        end_date=date(2026, 6, 15),
    )
    return PitchBooking.objects.create(
        fixture=fixture,
        pitch=pitch,
        booking_type="FIXTURE",
        start_date=date(2026, 6, 15),
        end_date=date(2026, 6, 15),
        time_slot="AFTERNOON",
        status=status,
        external_contact_name=external_name,
        external_contact_email=external_email,
    )


# ---------------------------------------------------------------------------
# _resolve_recipients helper
# ---------------------------------------------------------------------------


class ResolveRecipientsTest(TestCase):
    def setUp(self):
        self.user_with_email = User.objects.create_user(
            username="u1", email="u1@example.com", password="Password1!"
        )
        self.user_without_email = User.objects.create_user(
            username="u2", email="", password="Password1!"
        )

    @override_settings(EMAIL_ENABLED=False)
    def test_returns_empty_when_disabled(self):
        qs = User.objects.filter(username="u1")
        self.assertEqual(_resolve_recipients(qs), [])

    @override_settings(EMAIL_ENABLED=True, EMAIL_OVERRIDE_ADDRESS="")
    def test_returns_email_addresses_from_queryset(self):
        qs = User.objects.filter(username__in=["u1", "u2"])
        result = _resolve_recipients(qs)
        self.assertEqual(result, ["u1@example.com"])

    @override_settings(EMAIL_ENABLED=True, EMAIL_OVERRIDE_ADDRESS="")
    def test_returns_empty_when_no_users_have_email(self):
        qs = User.objects.filter(username="u2")
        self.assertEqual(_resolve_recipients(qs), [])

    @override_settings(EMAIL_ENABLED=True, EMAIL_OVERRIDE_ADDRESS="override@example.com")
    def test_returns_override_address_when_set(self):
        qs = User.objects.filter(username="u1")
        self.assertEqual(_resolve_recipients(qs), ["override@example.com"])

    @override_settings(EMAIL_ENABLED=True, EMAIL_OVERRIDE_ADDRESS="")
    def test_returns_empty_for_empty_queryset(self):
        qs = User.objects.none()
        self.assertEqual(_resolve_recipients(qs), [])


# ---------------------------------------------------------------------------
# notify_secretaries_new_booking
# ---------------------------------------------------------------------------


@override_settings(**EMAIL_SETTINGS)
class NotifySecretariesNewBookingTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")

    def test_sends_to_all_secretaries(self):
        sec1 = _make_secretary("sec1", "sec1@example.com")
        sec2 = _make_secretary("sec2", "sec2@example.com")
        booking = _make_booking(self.team, self.pitch)

        notify_secretaries_new_booking(booking)

        self.assertEqual(len(mail.outbox), 1)
        recipients = mail.outbox[0].to
        self.assertIn("sec1@example.com", recipients)
        self.assertIn("sec2@example.com", recipients)

    def test_correct_subject(self):
        _make_secretary("sec1")
        booking = _make_booking(self.team, self.pitch)
        notify_secretaries_new_booking(booking)
        self.assertEqual(mail.outbox[0].subject, "New Pitch Booking Request")

    def test_body_contains_pitch_name(self):
        _make_secretary("sec1")
        booking = _make_booking(self.team, self.pitch)
        notify_secretaries_new_booking(booking)
        self.assertIn("Pitch 1", mail.outbox[0].body)

    def test_no_mail_when_no_secretaries(self):
        booking = _make_booking(self.team, self.pitch)
        notify_secretaries_new_booking(booking)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_mail_when_secretaries_have_no_email(self):
        sec = User.objects.create_user(username="sec_noemail", email="", password="Password1!")
        sec.roles = ["FIXTURE_SECRETARY"]
        sec.save()
        booking = _make_booking(self.team, self.pitch)
        notify_secretaries_new_booking(booking)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**{**EMAIL_SETTINGS, "EMAIL_ENABLED": False})
    def test_no_mail_when_email_disabled(self):
        _make_secretary("sec1")
        booking = _make_booking(self.team, self.pitch)
        notify_secretaries_new_booking(booking)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**{**EMAIL_SETTINGS, "EMAIL_OVERRIDE_ADDRESS": "override@example.com"})
    def test_redirects_to_override_address(self):
        _make_secretary("sec1", "sec1@example.com")
        booking = _make_booking(self.team, self.pitch)
        notify_secretaries_new_booking(booking)
        self.assertEqual(mail.outbox[0].to, ["override@example.com"])


# ---------------------------------------------------------------------------
# notify_secretaries_external_request
# ---------------------------------------------------------------------------


@override_settings(**EMAIL_SETTINGS)
class NotifySecretariesExternalRequestTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="External Team", is_external=True)

    def test_sends_with_external_subject(self):
        _make_secretary("sec1")
        booking = _make_booking(
            self.team,
            self.pitch,
            external_name="Dorset CC",
            external_email="contact@dorset.cc",
        )
        notify_secretaries_external_request(booking)
        self.assertEqual(mail.outbox[0].subject, "New External Pitch Booking Request")

    def test_body_contains_external_name(self):
        _make_secretary("sec1")
        booking = _make_booking(
            self.team,
            self.pitch,
            external_name="Dorset CC",
            external_email="contact@dorset.cc",
        )
        notify_secretaries_external_request(booking)
        self.assertIn("Dorset CC", mail.outbox[0].body)


# ---------------------------------------------------------------------------
# notify_manager_booking_status_changed
# ---------------------------------------------------------------------------


@override_settings(**EMAIL_SETTINGS)
class NotifyManagerStatusChangedTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")
        self.other_team = Team.objects.create(name="2nd XI")

    def test_sends_to_managers_of_correct_team_only(self):
        manager1 = _make_manager("mgr1", "mgr1@example.com")
        manager2 = _make_manager("mgr2", "mgr2@example.com")
        self.team.managers.add(manager1)
        self.other_team.managers.add(manager2)

        booking = _make_booking(self.team, self.pitch, status="APPROVED")
        notify_manager_booking_status_changed(booking, "PENDING")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("mgr1@example.com", mail.outbox[0].to)
        self.assertNotIn("mgr2@example.com", mail.outbox[0].to)

    def test_correct_subject_contains_new_status(self):
        manager1 = _make_manager("mgr1")
        self.team.managers.add(manager1)
        booking = _make_booking(self.team, self.pitch, status="APPROVED")
        notify_manager_booking_status_changed(booking, "PENDING")
        self.assertIn("Confirmed", mail.outbox[0].subject)

    def test_no_mail_when_no_managers(self):
        booking = _make_booking(self.team, self.pitch, status="APPROVED")
        notify_manager_booking_status_changed(booking, "PENDING")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**{**EMAIL_SETTINGS, "EMAIL_ENABLED": False})
    def test_no_mail_when_email_disabled(self):
        manager1 = _make_manager("mgr1")
        self.team.managers.add(manager1)
        booking = _make_booking(self.team, self.pitch, status="APPROVED")
        notify_manager_booking_status_changed(booking, "PENDING")
        self.assertEqual(len(mail.outbox), 0)

    def test_multiple_managers_all_receive(self):
        mgr1 = _make_manager("mgr1", "mgr1@example.com")
        mgr2 = _make_manager("mgr2", "mgr2@example.com")
        self.team.managers.add(mgr1, mgr2)
        booking = _make_booking(self.team, self.pitch, status="APPROVED")
        notify_manager_booking_status_changed(booking, "PENDING")
        self.assertIn("mgr1@example.com", mail.outbox[0].to)
        self.assertIn("mgr2@example.com", mail.outbox[0].to)

    def test_no_crash_when_booking_has_no_fixture(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 15),
            time_slot="AFTERNOON",
            status="APPROVED",
        )
        notify_manager_booking_status_changed(booking, "PENDING")
        self.assertEqual(len(mail.outbox), 0)


# ---------------------------------------------------------------------------
# notify_managers_booking_evicted
# ---------------------------------------------------------------------------


@override_settings(**EMAIL_SETTINGS)
class NotifyManagersEvictedTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")

    def test_sends_eviction_email(self):
        mgr = _make_manager("mgr1")
        self.team.managers.add(mgr)
        booking = _make_booking(self.team, self.pitch)
        notify_managers_booking_evicted(booking)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Maintenance", mail.outbox[0].subject)

    def test_no_mail_when_no_managers(self):
        booking = _make_booking(self.team, self.pitch)
        notify_managers_booking_evicted(booking)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_crash_when_booking_has_no_fixture(self):
        booking = PitchBooking.objects.create(
            pitch=self.pitch,
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 15),
            time_slot="AFTERNOON",
            status="DENIED",
        )
        notify_managers_booking_evicted(booking)
        self.assertEqual(len(mail.outbox), 0)


# ---------------------------------------------------------------------------
# notify_caterers_new_catering_request
# ---------------------------------------------------------------------------


@override_settings(**EMAIL_SETTINGS)
class NotifyCaterersTest(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name="Ground")
        self.pitch = Pitch.objects.create(venue=self.venue, name="Pitch 1", pitch_type="GRASS")
        self.team = Team.objects.create(name="1st XI")
        booking = _make_booking(self.team, self.pitch)
        self.catering_request = CateringRequest.objects.create(
            booking=booking,
            requires_teas=True,
            requires_drinks=False,
        )

    def test_sends_to_all_caterers(self):
        cat1 = _make_caterer("cat1", "cat1@example.com")
        cat2 = _make_caterer("cat2", "cat2@example.com")
        notify_caterers_new_catering_request(self.catering_request)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("cat1@example.com", mail.outbox[0].to)
        self.assertIn("cat2@example.com", mail.outbox[0].to)

    def test_correct_subject(self):
        _make_caterer("cat1")
        notify_caterers_new_catering_request(self.catering_request)
        self.assertEqual(mail.outbox[0].subject, "New Catering Request")

    def test_no_mail_when_no_caterers(self):
        notify_caterers_new_catering_request(self.catering_request)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**{**EMAIL_SETTINGS, "EMAIL_ENABLED": False})
    def test_no_mail_when_email_disabled(self):
        _make_caterer("cat1")
        notify_caterers_new_catering_request(self.catering_request)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**{**EMAIL_SETTINGS, "EMAIL_OVERRIDE_ADDRESS": "override@example.com"})
    def test_redirects_to_override(self):
        _make_caterer("cat1", "cat1@example.com")
        notify_caterers_new_catering_request(self.catering_request)
        self.assertEqual(mail.outbox[0].to, ["override@example.com"])
