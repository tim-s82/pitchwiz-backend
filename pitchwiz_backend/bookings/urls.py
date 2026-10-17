from bookings.views import (
    BookingChangeRequestViewSet,
    CateringRequestViewSet,
    FixtureViewSet,
    HealthCheckView,
    PitchBookingViewSet,
    PitchLengthViewSet,
    PitchViewSet,
    TeamViewSet,
    VenueViewSet,
    VersionView,
    commit_fixtures_import_view,
    preview_play_cricket_fixtures_view,
    preview_spreadsheet_fixtures_view,
)
from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)
router.register(r"venues", VenueViewSet, basename="venue")
router.register(r"pitches", PitchViewSet, basename="pitch")
router.register(r"pitchlengths", PitchLengthViewSet, basename="pitchlength")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"fixtures", FixtureViewSet, basename="fixture")
router.register(r"pitchbookings", PitchBookingViewSet, basename="pitchbooking")
router.register(r"catering-requests", CateringRequestViewSet, basename="catering-request")
router.register(
    r"booking-change-requests",
    BookingChangeRequestViewSet,
    basename="booking-change-request",
)

urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health_check"),
    path("version", VersionView.as_view(), name="version"),
    path("version/", VersionView.as_view(), name="version_slash"),
    path(
        "fixtures/preview-spreadsheet",
        preview_spreadsheet_fixtures_view,
        name="preview-spreadsheet-fixtures",
    ),
    path(
        "fixtures/preview-play-cricket",
        preview_play_cricket_fixtures_view,
        name="preview-play-cricket-fixtures",
    ),
    path("fixtures/commit-import", commit_fixtures_import_view, name="commit-fixtures-import"),
    path("", include(router.urls)),
]
