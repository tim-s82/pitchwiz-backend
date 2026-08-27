from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly

from users.permissions import (
    IsAdminOrManagerOrSecretaryOrReadOnly,
    IsBookingOwnerOrSecretary,
    IsCaterer,
    IsFixtureManagerOrReadOnly,
    IsFixtureSecretary,
    IsTeamManager,
)

from .models import (
    BookingChangeRequest,
    CateringRequest,
    Fixture,
    Pitch,
    PitchBooking,
    PitchLength,
    Team,
    Venue,
)
from .serializers import (
    BookingChangeRequestSerializer,
    CateringRequestSerializer,
    FixtureSerializer,
    PitchBookingSerializer,
    PitchLengthSerializer,
    PitchSerializer,
    TeamSerializer,
    VenueSerializer,
)


def health_check(request):
    return JsonResponse({"status": "awake"})


class VenueViewSet(viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [IsAdminOrManagerOrSecretaryOrReadOnly]


class PitchLengthViewSet(viewsets.ModelViewSet):
    queryset = PitchLength.objects.all()
    serializer_class = PitchLengthSerializer
    permission_classes = [IsAdminOrManagerOrSecretaryOrReadOnly]


class PitchViewSet(viewsets.ModelViewSet):
    queryset = Pitch.objects.all()
    serializer_class = PitchSerializer
    permission_classes = [IsAdminOrManagerOrSecretaryOrReadOnly]


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsAdminOrManagerOrSecretaryOrReadOnly]


class FixtureViewSet(viewsets.ModelViewSet):
    queryset = Fixture.objects.all()
    serializer_class = FixtureSerializer
    permission_classes = [IsFixtureManagerOrReadOnly]


class PitchBookingViewSet(viewsets.ModelViewSet):
    queryset = PitchBooking.objects.all()
    serializer_class = PitchBookingSerializer

    def get_permissions(self):
        if self.action in ["create", "destroy", "update", "partial_update"]:
            return [IsAuthenticated(), IsBookingOwnerOrSecretary()]
        return [IsAuthenticatedOrReadOnly()]


class CateringRequestViewSet(viewsets.ModelViewSet):
    queryset = CateringRequest.objects.all()
    serializer_class = CateringRequestSerializer

    def get_permissions(self):
        if self.request.method in ["POST", "PUT", "PATCH"]:
            return [IsCaterer()]
        return [IsAuthenticatedOrReadOnly()]


class BookingChangeRequestViewSet(viewsets.ModelViewSet):
    queryset = BookingChangeRequest.objects.all()
    serializer_class = BookingChangeRequestSerializer

    def get_permissions(self):
        if self.request.method in ["POST", "PUT", "PATCH"]:
            return [IsFixtureSecretary()]
        return [IsAuthenticatedOrReadOnly()]
