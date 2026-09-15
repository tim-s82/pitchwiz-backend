import csv
import io
import logging
from datetime import datetime

import requests
from bookings.models import (
    BookingChangeRequest,
    CateringRequest,
    Fixture,
    Pitch,
    PitchBooking,
    PitchLength,
    Team,
    Venue,
)
from bookings.serializers import (
    BookingChangeRequestSerializer,
    CateringRequestSerializer,
    FixtureSerializer,
    PitchBookingSerializer,
    PitchLengthSerializer,
    PitchSerializer,
    TeamSerializer,
    VenueSerializer,
)
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import (
    BasePermission,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response
from users.permissions import IsCaterer, IsFixtureSecretary
from bookings.matching import find_best_team_match, find_best_pitch_match

logger = logging.getLogger(__name__)


class BaseRolePermission(BasePermission):
    allowed_roles = []

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        user_roles = (
            request.user.roles.all() if hasattr(request.user.roles, "all") else request.user.roles
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
                role in ["ADMIN", "FIXTURE_SECRETARY", "GROUNDSTAFF"] for role in role_names
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
                logger.warning(
                    "Maintenance booking attempt by user %s failed: no pitches selected.",
                    request.user.id,
                )
                return Response(
                    {"pitches": ["At least one pitch must be selected for ground maintenance."]},
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
                        conflicts = conflicts.filter(time_slot__in=[time_slot, "ALL_DAY"])

                    conflict_count = conflicts.count()
                    if conflict_count > 0:
                        logger.info(
                            "Ground maintenance override auto-denying %s booking(s) on pitch %s (%s to %s, slot: %s).",
                            conflict_count,
                            pitch_obj.name,
                            start_date,
                            end_date,
                            time_slot,
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
                        requested_by=(request.user if request.user.is_authenticated else None),
                        notes=data.get("notes", ""),
                    )
                    created_bookings.append(booking)

            logger.info(
                "User %s (%s) successfully created %s ground maintenance booking(s).",
                request.user.id,
                request.user.get_username(),
                len(created_bookings),
            )
            serializer = self.get_serializer(created_bookings, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # 2. Standard Fixture Booking Flow
        if not data.get("pitch"):
            logger.warning(
                "Standard booking attempt by user %s failed: missing pitch field.",
                request.user.id,
            )
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
                logger.info(
                    "Standard pitch booking #%s created by user %s for pitch %s.",
                    main_booking_id,
                    request.user.id,
                    pitch_obj.name,
                )

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
            or any(role in ["ADMIN", "FIXTURE_SECRETARY", "GROUNDSTAFF"] for role in role_names)
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
            logger.warning(
                "Fixture secretary %s attempted invalid status update for booking #%s: %s",
                request.user.id,
                booking.id,
                new_status,
            )
            return Response(
                {"status": [f"Must be one of: {', '.join(allowed_statuses)}"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = booking.status
        booking.status = new_status
        if rejection_reason:
            booking.rejection_reason = rejection_reason
        booking.save(update_fields=["status", "rejection_reason"])

        logger.info(
            "Booking #%s status changed from %s to %s by fixture secretary %s (%s).",
            booking.id,
            old_status,
            new_status,
            request.user.id,
            request.user.get_username(),
        )

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
def commit_fixtures_import_view(request):
    """
    Bulk commits a list of user-reviewed fixture rows (from spreadsheet or Play-Cricket).
    Uses an atomic transaction to ensure data integrity.
    """
    rows = request.data.get("rows", [])
    if not rows:
        return Response(
            {"detail": "No rows provided to commit."}, status=status.HTTP_400_BAD_REQUEST
        )

    synced_count = 0
    updated_count = 0
    errors = []

    with transaction.atomic():
        for idx, row in enumerate(rows):
            team_id = row.get("teamId")
            opponent = row.get("opponent")
            date_str = row.get("date")
            time_slot = row.get("timeSlot", "AFTERNOON")
            pitch_id = row.get("pitchId")
            pc_id = row.get("playCricketId")
            time_str = row.get("time", "")

            if not team_id or not opponent or not date_str:
                errors.append(f"Row {idx+1}: Missing required fields.")
                continue

            team_obj = Team.objects.filter(id=team_id).first()
            if not team_obj:
                errors.append(f"Row {idx+1}: Invalid team assigned.")
                continue

            # Idempotency: Use Play-Cricket ID if available, otherwise match on team/opponent/date
            if pc_id:
                fixture, created = Fixture.objects.update_or_create(
                    play_cricket_id=pc_id,
                    defaults={
                        "team": team_obj,
                        "opponent": opponent,
                        "start_date": date_str,
                        "end_date": date_str,
                    },
                )
            else:
                fixture, created = Fixture.objects.get_or_create(
                    team=team_obj,
                    opponent=opponent,
                    start_date=date_str,
                    defaults={
                        "end_date": date_str,
                    },
                )

            if created:
                synced_count += 1
            else:
                updated_count += 1

            # Auto-approve Pitch Booking if a pitch was assigned
            if pitch_id:
                pitch_obj = Pitch.objects.filter(id=pitch_id).first()
                if pitch_obj:
                    PitchBooking.objects.update_or_create(
                        fixture=fixture,
                        defaults={
                            "pitch": pitch_obj,
                            "start_date": date_str,
                            "end_date": date_str,
                            "time_slot": time_slot,
                            "status": "APPROVED",
                            "requested_by": request.user,
                            "notes": (
                                f"Imported Fixture (Time: {time_str})"
                                if time_str
                                else "Imported Fixture"
                            ),
                        },
                    )

    return Response(
        {
            "success": True,
            "synced_count": synced_count,
            "updated_count": updated_count,
            "errors": errors,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_spreadsheet_fixtures_view(request):
    """
    Accepts raw JSON rows from the uploaded spreadsheet, performs backend matching
    for teams and pitches, validates fields, and returns processed rows for preview.
    """
    raw_rows = request.data.get("rows", [])
    if not raw_rows:
        return Response(
            {"detail": "No rows provided for preview."}, status=status.HTTP_400_BAD_REQUEST
        )

    teams = Team.objects.all()
    pitches = Pitch.objects.all()
    venues = Venue.objects.all()

    processed_rows = []

    for index, row in enumerate(raw_rows):
        # Normalize incoming dict keys
        norm_row = {k.strip().lower().replace(" ", "_"): v for k, v in row.items()}

        team_name_raw = str(
            norm_row.get("team") or norm_row.get("club_team") or norm_row.get("club") or ""
        ).strip()
        opponent = str(norm_row.get("opponent") or norm_row.get("opposition") or "").strip()
        date_str = str(
            norm_row.get("date") or norm_row.get("match_date") or norm_row.get("day") or ""
        ).strip()
        time_str = str(
            norm_row.get("time")
            or norm_row.get("start_time")
            or norm_row.get("match_time")
            or "14:00"
        ).strip()
        pitch_pref = str(
            norm_row.get("pitch_preference") or norm_row.get("pitch") or norm_row.get("venue") or ""
        ).strip()

        # Run backend matching algorithms
        team_match = find_best_team_match(team_name_raw, teams)
        matched_pitch_id = find_best_pitch_match(pitch_pref, pitches, venues)

        # Time slot derivation
        hour = (
            int(time_str.split(":")[0])
            if ":" in time_str and time_str.split(":")[0].isdigit()
            else 14
        )
        if hour < 12:
            time_slot = "MORNING"
        elif hour >= 17:
            time_slot = "EVENING"
        else:
            time_slot = "AFTERNOON"

        # Validation / Clash checks
        clash_reason = None
        if not team_name_raw:
            clash_reason = "Missing team name"
        elif not opponent:
            clash_reason = "Missing opponent name"
        elif not date_str:
            clash_reason = "Missing match date"

        processed_rows.append(
            {
                "id": index,
                "teamNameRaw": team_name_raw,
                "teamId": team_match["team_id"],
                "teamAmbiguous": team_match["ambiguous"],
                "opponent": opponent,
                "date": date_str,
                "time": time_str,
                "timeSlot": time_slot,
                "pitchPref": pitch_pref,
                "pitchId": matched_pitch_id,
                "clashReason": clash_reason,
                "selected": not clash_reason,
            }
        )

    return Response({"success": True, "rows": processed_rows}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_play_cricket_fixtures_view(request):
    """
    Fetches raw fixtures from ECB Play-Cricket v2 API, runs backend team and ground matching,
    and returns enriched rows for frontend review and adjustment.
    """
    site_id = getattr(settings, "PLAY_CRICKET_SITE_ID", None)
    api_token = getattr(settings, "PLAY_CRICKET_API_KEY", None)
    base_url = getattr(settings, "PLAY_CRICKET_URL", "http://play-cricket.com")

    if not site_id or not api_token:
        return Response(
            {"detail": "Play-Cricket Site ID or API Key is not configured on the server."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    season = request.data.get("season", datetime.now().year)
    endpoint = f"{base_url.rstrip('/')}/api/v2/matches.json"
    params = {"api_token": api_token, "site_id": site_id, "season": season}

    try:
        response = requests.get(endpoint, params=params, timeout=15)
        if response.status_code != 200:
            return Response(
                {"detail": f"Play-Cricket API error (HTTP {response.status_code})"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = response.json()
        raw_fixtures = data.get("matches", [])

        teams = Team.objects.all()
        pitches = Pitch.objects.all()
        venues = Venue.objects.all()

        processed_rows = []

        for index, match in enumerate(raw_fixtures):
            pc_id = str(match.get("id"))
            home_team_name = match.get("home_team_name", "").strip()
            away_team_name = match.get("away_team_name", "").strip()
            date_str = match.get("match_date", "").strip()
            time_str = match.get("match_time", "14:00").strip()
            ground_name = match.get("ground_name", "").strip()
            ground_id = match.get("ground_id", "").strip()

            # Determine home vs away / team matching
            team_match = find_best_team_match(home_team_name, teams)
            opponent = away_team_name
            team_id = team_match["team_id"]
            team_ambiguous = team_match["ambiguous"]

            # If home team didn't match well, check away team
            if not Team.objects.filter(id=team_id).exists() or (
                home_team_name and not team_match["team_id"]
            ):
                away_team_match = find_best_team_match(away_team_name, teams)
                if away_team_match["team_id"]:
                    team_id = away_team_match["team_id"]
                    team_ambiguous = away_team_match["ambiguous"]
                    opponent = home_team_name

            # Date parsing (DD/MM/YYYY)
            try:
                parsed_date = datetime.strptime(date_str, "%d/%m/%Y").date().isoformat()
            except ValueError:
                parsed_date = ""

            # Match pitch/ground
            matched_pitch_id = find_best_pitch_match(ground_name, pitches, venues)

            # Time slot derivation
            hour = (
                int(time_str.split(":")[0])
                if ":" in time_str and time_str.split(":")[0].isdigit()
                else 14
            )
            if hour < 12:
                time_slot = "MORNING"
            elif hour >= 17:
                time_slot = "EVENING"
            else:
                time_slot = "AFTERNOON"

            clash_reason = None
            if not parsed_date:
                clash_reason = f"Invalid date: {date_str}"
            elif not team_id:
                clash_reason = "Unmatched team"

            processed_rows.append(
                {
                    "id": index,
                    "playCricketId": pc_id,
                    "teamNameRaw": home_team_name,
                    "teamId": team_id,
                    "teamAmbiguous": team_ambiguous,
                    "opponent": opponent,
                    "date": parsed_date,
                    "time": time_str,
                    "timeSlot": time_slot,
                    "pitchPref": ground_name,
                    "pitchId": matched_pitch_id,
                    "clashReason": clash_reason,
                    "selected": not clash_reason,
                }
            )

        return Response({"success": True, "rows": processed_rows}, status=status.HTTP_200_OK)

    except requests.RequestException as req_err:
        return Response(
            {"detail": f"Failed to connect to Play-Cricket: {str(req_err)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
