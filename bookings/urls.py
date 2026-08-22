from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VenueViewSet,
    PitchViewSet,
    TeamViewSet,
    FixtureViewSet,
    PitchBookingViewSet,
    PitchLengthViewSet,
    CateringRequestViewSet,
    BookingChangeRequestViewSet,
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
]
