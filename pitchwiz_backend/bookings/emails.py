import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string

User = get_user_model()
logger = logging.getLogger(__name__)


def _resolve_recipients(queryset):
    """
    Compute final recipient list from a User queryset.

    Returns [] if:
    - EMAIL_ENABLED is False
    - No users in queryset have an email address

    Returns [EMAIL_OVERRIDE_ADDRESS] if that setting is non-empty,
    redirecting all mail to a single address for dev/QA purposes.
    """
    if not getattr(settings, "EMAIL_ENABLED", True):
        return []
    recipients = [u.email for u in queryset if u.email]
    if not recipients:
        return []
    override = getattr(settings, "EMAIL_OVERRIDE_ADDRESS", "")
    return [override] if override else recipients


def _users_with_role(role_name):
    """
    Return all active users who hold the given role.

    Uses Python-side filtering so this works with both SQLite (tests/local)
    and PostgreSQL (production), since JSONField `contains` lookups are
    not supported on SQLite.
    """
    return [
        u for u in User.objects.filter(is_active=True).only("id", "email", "roles")
        if role_name in (u.roles or [])
    ]


def _secretaries():
    """Return all active Fixture Secretaries."""
    return _users_with_role("FIXTURE_SECRETARY")


def _team_managers_for_team(team):
    """Return all active Team Managers linked to the given team."""
    team_manager_ids = set(team.managers.values_list("id", flat=True))
    return [
        u for u in _users_with_role("TEAM_MANAGER")
        if u.id in team_manager_ids
    ]


def _caterers():
    """Return all active Caterers."""
    return _users_with_role("CATERER")


def notify_secretaries_new_booking(booking):
    """Notify all Fixture Secretaries of a new pending booking request."""
    recipients = _resolve_recipients(_secretaries())
    if not recipients:
        return
    body = render_to_string("bookings/email/new_booking.txt", {"booking": booking})
    try:
        send_mail(
            subject="New Pitch Booking Request",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send new booking notification for booking #%s", booking.id
        )


def notify_secretaries_external_request(booking):
    """Notify all Fixture Secretaries of a new external booking request."""
    recipients = _resolve_recipients(_secretaries())
    if not recipients:
        return
    body = render_to_string("bookings/email/new_booking.txt", {"booking": booking})
    try:
        send_mail(
            subject="New External Pitch Booking Request",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send external booking notification for booking #%s", booking.id
        )


def notify_manager_booking_status_changed(booking, old_status):
    """Notify all managers of the relevant team when a booking is approved/denied."""
    recipients = _resolve_recipients(_team_managers_for_team(booking.fixture.team))
    if not recipients:
        return
    body = render_to_string(
        "bookings/email/booking_status.txt",
        {"booking": booking, "old_status": old_status},
    )
    try:
        send_mail(
            subject=f"Pitch Booking {booking.get_status_display()}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send status-change notification for booking #%s", booking.id
        )


def notify_managers_booking_evicted(booking):
    """Notify team managers when their booking is auto-denied due to ground maintenance."""
    recipients = _resolve_recipients(_team_managers_for_team(booking.fixture.team))
    if not recipients:
        return
    body = render_to_string("bookings/email/eviction.txt", {"booking": booking})
    try:
        send_mail(
            subject="Pitch Booking Cancelled — Ground Maintenance",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send eviction notification for booking #%s", booking.id
        )


def notify_caterers_new_catering_request(catering_request):
    """Notify all Caterers of a new catering requirement."""
    recipients = _resolve_recipients(_caterers())
    if not recipients:
        return
    body = render_to_string(
        "bookings/email/catering_request.txt", {"catering_request": catering_request}
    )
    try:
        send_mail(
            subject="New Catering Request",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send catering notification for request #%s",
            catering_request.id,
        )
