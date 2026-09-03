from bookings.views import import_fixtures_view, sync_play_cricket_fixtures_view
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BookingChangeRequestViewSet,
    CateringRequestViewSet,
    FixtureViewSet,
    PitchBookingViewSet,
    PitchLengthViewSet,
    PitchViewSet,
    TeamViewSet,
    VenueViewSet,
    health_check,
)

router = DefaultRouter()
router.register(r"venues", VenueViewSet, basename="venue")
router.register(r"pitches", PitchViewSet, basename="pitch")
router.register(r"pitchlengths", PitchLengthViewSet, basename="pitchlength")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"fixtures", FixtureViewSet, basename="fixture")
router.register(r"pitchbookings", PitchBookingViewSet, basename="pitchbooking")
router.register(
    r"catering-requests", CateringRequestViewSet, basename="catering-request"
)
router.register(
    r"booking-change-requests",
    BookingChangeRequestViewSet,
    basename="booking-change-request",
)

urlpatterns = [
    path("", include(router.urls)),
    path("api/health/", health_check, name="health_check"),
    path("api/fixtures/import/", import_fixtures_view, name="import-fixtures"),
    path(
        "api/fixtures/sync-play-cricket/",
        sync_play_cricket_fixtures_view,
        name="sync-play-cricket",
    ),
]
