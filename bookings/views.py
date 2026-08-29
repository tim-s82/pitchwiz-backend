from bookings import models
from django.http import JsonResponse
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import (
    BasePermission,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)

from users.permissions import (
    IsCaterer,
    IsFixtureSecretary,
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


class BaseRolePermission(BasePermission):
    allowed_roles = []

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        user_roles = (
            request.user.roles.all()
            if hasattr(request.user.roles, "all")
            else request.user.roles
        )
        role_names = [r.name if hasattr(r, "name") else str(r) for r in user_roles]
        return any(role in self.allowed_roles for role in role_names)


class IsManagementOrGroundstaff(BaseRolePermission):
    allowed_roles = ["ADMIN", "TEAM_MANAGER", "FIXTURE_SECRETARY", "GROUNDSTAFF"]


class IsManagementTeam(BaseRolePermission):
    allowed_roles = ["ADMIN", "TEAM_MANAGER", "FIXTURE_SECRETARY"]


def health_check(request):
    return JsonResponse({"status": "awake"})


class VenueViewSet(viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [IsAuthenticated, IsManagementOrGroundstaff]


class PitchLengthViewSet(viewsets.ModelViewSet):
    queryset = PitchLength.objects.all()
    serializer_class = PitchLengthSerializer
    permission_classes = [IsAuthenticated, IsManagementOrGroundstaff]


class PitchViewSet(viewsets.ModelViewSet):
    queryset = Pitch.objects.all()
    serializer_class = PitchSerializer
    permission_classes = [IsAuthenticated, IsManagementOrGroundstaff]


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated, IsManagementTeam]


class FixtureViewSet(viewsets.ModelViewSet):
    queryset = Fixture.objects.all()
    serializer_class = FixtureSerializer

    def get_permissions(self):
        if self.action in ["create", "destroy", "update", "partial_update"]:
            return [IsAuthenticated(), IsManagementOrGroundstaff()]
        return [IsAuthenticatedOrReadOnly()]


class PitchBookingViewSet(viewsets.ModelViewSet):
    queryset = PitchBooking.objects.all()
    serializer_class = PitchBookingSerializer

    def get_permissions(self):
        if self.action in ["create", "destroy", "update", "partial_update"]:
            if not self.request.user or not self.request.user.is_authenticated:
                return [IsAuthenticated()]

            user = self.request.user
            user_roles = user.roles.all() if hasattr(user.roles, "all") else user.roles
            role_names = [r.name if hasattr(r, "name") else str(r) for r in user_roles]

            is_privileged = user.is_superuser or any(
                role in ["ADMIN", "FIXTURE_SECRETARY", "GROUNDSTAFF"]
                for role in role_names
            )
            if is_privileged:
                return [IsAuthenticated()]
            else:
                from users.permissions import IsBookingOwnerOrSecretary

                return [IsAuthenticated(), IsBookingOwnerOrSecretary()]

        return [IsAuthenticatedOrReadOnly()]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        booking_type = data.get("booking_type", "FIXTURE")
        pitches_list = data.get("pitches", [])

        # 1. Ground Maintenance Multi-Pitch Flow
        if booking_type == "GROUND_MAINTENANCE" or pitches_list:
            if not pitches_list:
                return Response(
                    {
                        "pitches": [
                            "At least one pitch must be selected for ground maintenance."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            created_bookings = []
            start_date = data.get("start_date")
            end_date = data.get("end_date") or start_date
            time_slot = data.get("time_slot", "ALL_DAY")

            with transaction.atomic():
                for pitch_id in pitches_list:
                    pitch_obj = Pitch.objects.get(id=pitch_id)

                    # Auto-cancel conflicting bookings on this pitch
                    conflicts = PitchBooking.objects.filter(
                        pitch_id=pitch_id,
                        status__in=["PENDING", "APPROVED"],
                        start_date__lte=end_date,
                        end_date__gte=start_date,
                    )
                    if time_slot != "ALL_DAY":
                        conflicts = conflicts.filter(
                            time_slot__in=[time_slot, "ALL_DAY"]
                        )

                    conflicts.update(
                        status="DENIED",
                        rejection_reason="Cancelled automatically due to scheduled ground maintenance override.",
                    )

                    # Create maintenance booking
                    booking = PitchBooking.objects.create(
                        pitch=pitch_obj,
                        booking_type="GROUND_MAINTENANCE",
                        start_date=start_date,
                        end_date=end_date,
                        time_slot=time_slot,
                        status="APPROVED",
                        requested_by=(
                            request.user if request.user.is_authenticated else None
                        ),
                        notes=data.get("notes", ""),
                    )
                    created_bookings.append(booking)

            serializer = self.get_serializer(created_bookings, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # 2. Standard Fixture Booking Flow
        if not data.get("pitch"):
            return Response(
                {"pitch": ["This field is required for standard bookings."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            response = super().create(request, *args, **kwargs)

            if response.status_code == status.HTTP_201_CREATED:
                main_booking_id = response.data.get("id")
                main_pitch_id = int(data.get("pitch"))
                pitch_obj = Pitch.objects.get(id=main_pitch_id)

        return response

    def perform_create(self, serializer):
        user = self.request.user
        user_roles = (
            user.roles.all()
            if hasattr(user.roles, "all")
            else (user.roles if user.is_authenticated else [])
        )
        role_names = [r.name if hasattr(r, "name") else str(r) for r in user_roles]

        is_auto_approved = user.is_authenticated and (
            user.is_superuser
            or any(
                role in ["ADMIN", "FIXTURE_SECRETARY", "GROUNDSTAFF"]
                for role in role_names
            )
        )

        serializer.save(
            requested_by=user if user.is_authenticated else None,
            status="APPROVED" if is_auto_approved else "PENDING",
        )


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
