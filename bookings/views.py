from rest_framework import viewsets
from .models import Venue, Pitch, Team, Fixture, PitchBooking, PitchLength, CateringRequest, BookingChangeRequest
from .serializers import (
    VenueSerializer,
    PitchSerializer,
    TeamSerializer,
    FixtureSerializer,
    PitchBookingSerializer,
    PitchLengthSerializer,
    CateringRequestSerializer,
    BookingChangeRequestSerializer,
)
from users.permissions import (
    IsAdminOrManagerOrSecretaryOrReadOnly,
    IsFixtureSecretary,
    IsCaterer,
    IsTeamManager,
)
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated


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
    permission_classes = [IsAdminOrManagerOrSecretaryOrReadOnly]


class PitchBookingViewSet(viewsets.ModelViewSet):
    queryset = PitchBooking.objects.all()
    serializer_class = PitchBookingSerializer

    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            # Either Secretary or Team Manager
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated()]
        return [IsAuthenticatedOrReadOnly()]

class CateringRequestViewSet(viewsets.ModelViewSet):
    queryset = CateringRequest.objects.all()
    serializer_class = CateringRequestSerializer

    def get_permissions(self):
        if self.request.method in ['POST', 'PUT', 'PATCH']:
            return [IsCaterer()]
        return [IsAuthenticatedOrReadOnly()]

class BookingChangeRequestViewSet(viewsets.ModelViewSet):
    queryset = BookingChangeRequest.objects.all()
    serializer_class = BookingChangeRequestSerializer

    def get_permissions(self):
        if self.request.method in ['POST', 'PUT', 'PATCH']:
            return [IsFixtureSecretary()]
        return [IsAuthenticatedOrReadOnly()]

