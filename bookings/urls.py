from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VenueViewSet,
    PitchViewSet,
    TeamViewSet,
    FixtureViewSet,
    PitchBookingViewSet,
    PitchLengthViewSet,
)

router = DefaultRouter()
router.register(r"venues", VenueViewSet, basename="venue")
router.register(r"pitches", PitchViewSet, basename="pitch")
router.register(r"pitchlengths", PitchLengthViewSet, basename="pitchlength")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"fixtures", FixtureViewSet, basename="fixture")
router.register(r"pitchbookings", PitchBookingViewSet, basename="pitchbooking")

urlpatterns = [
    path("", include(router.urls)),
]
