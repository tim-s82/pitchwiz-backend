import io
import csv
from datetime import datetime
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
from rest_framework.decorators import api_view, permission_classes, action

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
    permission_classes = [IsAuthenticated, IsManagementOrGroundstaff]


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

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[IsAuthenticated, IsFixtureSecretary],
        url_path="update-status",
    )
    def update_status(self, request, pk=None):
        """
        Custom action for Fixture Secretaries to update the status and
        rejection_reason of a PitchBooking. These fields are read-only in the
        standard serializer to prevent team managers from self-approving.
        """
        booking = self.get_object()
        new_status = request.data.get("status")
        rejection_reason = request.data.get("rejection_reason", "")

        allowed_statuses = ["APPROVED", "DENIED", "PENDING"]
        if new_status not in allowed_statuses:
            return Response(
                {"status": [f"Must be one of: {', '.join(allowed_statuses)}"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking.status = new_status
        if rejection_reason:
            booking.rejection_reason = rejection_reason
        booking.save(update_fields=["status", "rejection_reason"])

        serializer = self.get_serializer(booking)
        return Response(serializer.data)


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_fixtures_view(request):
    """
    Expects a file upload (CSV) or JSON payload of rows.
    Validates teams, derives time slots, checks database clashes (including pitch blocks),
    and creates fixtures/bookings.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"detail": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded_file = file_obj.read().decode("utf-8")
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        imported_count = 0
        errors = []

        for row_idx, row in enumerate(reader, start=1):
            team_name = row.get("team", "").strip()
            opponent = row.get("opponent", "").strip()
            date_str = row.get("date", "").strip()
            time_str = row.get("time", "14:00").strip()
            pitch_pref = row.get("pitch_preference", "").strip()

            # 1. Validate Team
            team = Team.objects.filter(name__iexact=team_name).first()
            if not team:
                errors.append(f"Row {row_idx}: Team '{team_name}' not found.")
                continue

            # 2. Parse Date
            try:
                match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                try:
                    match_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                except ValueError:
                    errors.append(f"Row {row_idx}: Invalid date format '{date_str}' (use YYYY-MM-DD).")
                    continue

            # 3. Derive Time Slot
            try:
                hour = int(time_str.split(":")[0])
                if hour < 12:
                    time_slot = "MORNING"
                elif hour >= 17:
                    time_slot = "EVENING"
                else:
                    time_slot = "AFTERNOON"
            except (ValueError, IndexError):
                time_slot = "AFTERNOON"

            # 4. Find Pitch
            pitch = Pitch.objects.filter(name__iexact=pitch_pref).first() or Pitch.objects.first()
            if not pitch:
                errors.append(f"Row {row_idx}: No valid pitch available.")
                continue

            # 5. Clash Detection (Checking existing bookings & blocked pitches)
            conflicting_bookings = PitchBooking.objects.filter(
                start_date=match_date,
                time_slot__in=[time_slot, "ALL_DAY"],
                status__in=["PENDING", "APPROVED"]
            ).filter(
                models.Q(pitch=pitch) | models.Q(pitch__in=pitch.blocks_pitches.all())
            )

            if conflicting_bookings.exists():
                errors.append(f"Row {row_idx}: Pitch clash detected for {pitch.name} on {match_date} ({time_slot}).")
                continue

            # 6. Create Fixture and Booking
            fixture = Fixture.objects.create(
                team=team,
                opponent=opponent,
                start_date=match_date,
                end_date=match_date
            )

            PitchBooking.objects.create(
                fixture=fixture,
                pitch=pitch,
                start_date=match_date,
                end_date=match_date,
                time_slot=time_slot,
                status="APPROVED",
                notes=f"Imported via spreadsheet (Time: {time_str})",
                requested_by=request.user
            )
            imported_count += 1

        return Response({
            "success": True,
            "imported_count": imported_count,
            "errors": errors
        }, status=status.HTTP_200_ON_CLOSE if not errors else status.HTTP_207_MULTI_STATUS)

    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)