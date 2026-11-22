import csv
import io
import logging
import os
from datetime import datetime

import requests
from bookings.emails import (
    notify_caterers_new_catering_request,
    notify_manager_booking_status_changed,
    notify_managers_booking_evicted,
    notify_secretaries_external_request,
    notify_secretaries_new_booking,
)
from bookings.matching import (
    allocate_pitches_for_matches,
    find_best_pitch_match,
    find_best_team_match,
    find_best_venue_match,
    infer_season_year,
    match_fixtures_for_refresh,
)
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
from django.db import connection, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views import View
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    BasePermission,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response
from users.permissions import IsCaterer, IsFixtureSecretary

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


from base.version import get_build_info


class HealthCheckView(View):
    def get(self, request, *args, **kwargs):
        # Base response - anyone can hit this safely (no DB load)
        response_data = {"status": "awake"}

        # Check for our secret token
        expected_token = os.environ.get("CRON_SECRET_TOKEN")
        provided_token = request.headers.get("X-Cron-Token")

        # Only ping the database if the token matches
        if expected_token and provided_token == expected_token:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                response_data["database"] = "awake"
            except Exception as e:
                # If the DB fails, return a 503 so your monitoring flags it
                return JsonResponse({"status": "awake", "database": "error"}, status=503)

        return JsonResponse(response_data)


class VersionView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse(get_build_info())


class VenueViewSet(viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer

    def get_permissions(self):
        if self.action in ["create", "destroy", "update", "partial_update"]:
            return [IsAuthenticated(), IsManagementOrGroundstaff()]
        return [AllowAny()]


class PitchLengthViewSet(viewsets.ModelViewSet):
    queryset = PitchLength.objects.all()
    serializer_class = PitchLengthSerializer
    permission_classes = [IsAuthenticated, IsManagementOrGroundstaff]


class PitchViewSet(viewsets.ModelViewSet):
    queryset = Pitch.objects.all()
    serializer_class = PitchSerializer

    def get_permissions(self):
        if self.action in ["create", "destroy", "update", "partial_update"]:
            return [IsAuthenticated(), IsManagementOrGroundstaff()]
        return [AllowAny()]


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
        # The @action decorator's permission_classes kwarg is ignored when
        # get_permissions() is overridden. Explicitly enforce secretary-only
        # access for the update_status action here.
        if self.action == "update_status":
            return [IsAuthenticated(), IsFixtureSecretary()]

        if self.action in ["destroy", "update", "partial_update"]:
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

        if self.action == "create":
            return [AllowAny()]

        return [IsAuthenticatedOrReadOnly()]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        booking_type = data.get("booking_type", "FIXTURE")
        pitches_list = data.get("pitches", [])

        # 1. Ground Maintenance Multi-Pitch Flow
        if booking_type == "GROUND_MAINTENANCE" or pitches_list:
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {"detail": "Authentication credentials were not provided."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
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

                    # Collect before bulk update so we can notify each evicted booking
                    evicted_bookings = list(conflicts)
                    for evicted in evicted_bookings:
                        notify_managers_booking_evicted(evicted)

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

        # 1b. Training Session Flow
        if booking_type == "TRAINING":
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {"detail": "Authentication credentials were not provided."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not data.get("pitch"):
                return Response(
                    {"pitch": ["This field is required for training bookings."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Server-side: team manager may only book teams they manage
            user = request.user
            user_roles = user.roles.all() if hasattr(user.roles, "all") else user.roles
            role_names = [r.name if hasattr(r, "name") else str(r) for r in user_roles]
            is_privileged = user.is_superuser or any(
                role in ["ADMIN", "FIXTURE_SECRETARY"] for role in role_names
            )
            if not is_privileged:
                raw_teams = data.get("teams") or []
                team_ids = [int(tid) for tid in raw_teams]
                if not team_ids:
                    return Response(
                        {"teams": ["You can only book training for teams you manage."]},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                managed_ids = set(Team.objects.filter(managers=user).values_list("id", flat=True))
                for tid in team_ids:
                    if tid not in managed_ids:
                        logger.warning(
                            "User %s attempted to book training for unmanaged team %s.",
                            user.id,
                            tid,
                        )
                        return Response(
                            {"teams": ["You can only book training for teams you manage."]},
                            status=status.HTTP_403_FORBIDDEN,
                        )

            with transaction.atomic():
                response = super().create(request, *args, **kwargs)
                if response.status_code == status.HTTP_201_CREATED:
                    logger.info(
                        "Training session booking #%s created by user %s (teams: %s).",
                        response.data["id"],
                        user.id,
                        data.get("teams", []) or "club-wide",
                    )
            return response

        # 2. Standard Fixture Booking Flow
        if not request.user or not request.user.is_authenticated:
            if (
                not data.get("external_contact_name")
                or not data.get("external_contact_email")
                or data.get("fixture")
            ):
                return Response(
                    {"detail": "Authentication credentials were not provided."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        if not data.get("pitch"):
            logger.warning(
                "Standard booking attempt by user %s failed: missing pitch field.",
                request.user.id if request.user.is_authenticated else "anonymous",
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
                    request.user.id if request.user.is_authenticated else "anonymous",
                    pitch_obj.name,
                )

        return response

    def perform_create(self, serializer):
        user = self.request.user
        if user and user.is_authenticated:
            user_roles = user.roles.all() if hasattr(user.roles, "all") else user.roles
        else:
            user_roles = []
        role_names = [r.name if hasattr(r, "name") else str(r) for r in user_roles]

        is_auto_approved = user.is_authenticated and (
            user.is_superuser
            or any(role in ["ADMIN", "FIXTURE_SECRETARY", "GROUNDSTAFF"] for role in role_names)
        )

        serializer.save(
            requested_by=user if user.is_authenticated else None,
            status="APPROVED" if is_auto_approved else "PENDING",
        )
        instance = serializer.instance
        if instance.status == "PENDING":
            if instance.external_contact_name:
                notify_secretaries_external_request(instance)
            else:
                notify_secretaries_new_booking(instance)

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

        notify_manager_booking_status_changed(booking, old_status)

        serializer = self.get_serializer(booking)
        return Response(serializer.data)


class CateringRequestViewSet(viewsets.ModelViewSet):
    queryset = CateringRequest.objects.all()
    serializer_class = CateringRequestSerializer

    def get_permissions(self):
        if self.request.method in ["POST", "PUT", "PATCH"]:
            return [IsCaterer()]
        return [IsAuthenticatedOrReadOnly()]

    def perform_create(self, serializer):
        instance = serializer.save()
        notify_caterers_new_catering_request(instance)


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
    deleted_count = 0
    errors = []

    with transaction.atomic():
        for idx, row in enumerate(rows):
            action = row.get("action", "")
            existing_fixture_id = row.get("existing_fixture_id")

            # Handle REMOVED fixtures
            if action == "REMOVED":
                if existing_fixture_id:
                    deleted_f_count, _ = Fixture.objects.filter(id=existing_fixture_id).delete()
                    if deleted_f_count > 0:
                        deleted_count += 1
                continue

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

            fixture = None
            if action == "RESCHEDULED" and existing_fixture_id:
                fixture = Fixture.objects.filter(id=existing_fixture_id).first()
                if fixture:
                    fixture.team = team_obj
                    fixture.opponent = opponent
                    fixture.start_date = date_str
                    fixture.end_date = date_str
                    fixture.save()
                    updated_count += 1

            if not fixture:
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
            "deleted_count": deleted_count,
            "errors": errors,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_spreadsheet_fixtures_view(request):
    """
    Accepts raw JSON rows from the uploaded spreadsheet, infers the season year,
    detects teams present in the data, performs matching and pitch allocation.
    Supports filtering by selected_team_ids.
    """
    raw_rows = request.data.get("rows", [])
    if not raw_rows:
        return Response(
            {"detail": "No rows provided for preview."}, status=status.HTTP_400_BAD_REQUEST
        )

    selected_team_ids = request.data.get("selected_team_ids")
    if selected_team_ids is not None:
        selected_team_ids = [int(tid) for tid in selected_team_ids]

    teams = list(Team.objects.all())
    pitches = list(
        Pitch.objects.filter(is_active=True).prefetch_related("supported_lengths", "blocks_pitches")
    )
    venues = list(Venue.objects.all())

    # Infer season from row dates
    raw_dates = []
    for r in raw_rows:
        norm_r = {k.strip().lower().replace(" ", "_"): v for k, v in r.items()}
        d = str(norm_r.get("date") or norm_r.get("match_date") or norm_r.get("day") or "").strip()
        if d:
            raw_dates.append(d)
    inferred_season = infer_season_year(raw_dates)

    parsed_incoming_by_team = {}
    team_meta = {}

    for index, row in enumerate(raw_rows):
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

        team_match = find_best_team_match(team_name_raw, teams)
        team_id = team_match["team_id"]
        team_ambiguous = team_match["ambiguous"]

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
        if not team_name_raw:
            clash_reason = "Missing team name"
        elif not opponent:
            clash_reason = "Missing opponent name"
        elif not date_str:
            clash_reason = "Missing match date"

        parsed_row = {
            "id": f"row_{index}",
            "teamNameRaw": team_name_raw,
            "teamId": team_id,
            "teamAmbiguous": team_ambiguous,
            "opponent": opponent,
            "date": date_str,
            "time": time_str,
            "timeSlot": time_slot,
            "pitchPref": pitch_pref,
            "clashReason": clash_reason,
            "selected": not clash_reason,
        }

        if team_id:
            parsed_incoming_by_team.setdefault(team_id, []).append(parsed_row)
            if team_id not in team_meta:
                t_obj = next((t for t in teams if t.id == team_id), None)
                team_meta[team_id] = {
                    "team_id": team_id,
                    "team_name": t_obj.name if t_obj else team_name_raw,
                    "ambiguous": team_ambiguous,
                }
        else:
            # Row has no matched team, keep it for clash visibility
            parsed_incoming_by_team.setdefault(None, []).append(parsed_row)

    # Also detect teams with existing fixtures in the DB for this season
    existing_team_ids = set(
        Fixture.objects.filter(start_date__year=inferred_season)
        .values_list("team_id", flat=True)
        .distinct()
    )
    for tid in existing_team_ids:
        if tid and tid not in team_meta:
            t_obj = next((t for t in teams if t.id == tid), None)
            if t_obj:
                team_meta[tid] = {
                    "team_id": tid,
                    "team_name": t_obj.name,
                    "ambiguous": False,
                }

    detected_teams = []
    for tid, meta in team_meta.items():
        incoming_count = len(parsed_incoming_by_team.get(tid, []))
        existing_count = Fixture.objects.filter(
            team_id=tid, start_date__year=inferred_season
        ).count()
        detected_teams.append(
            {
                "team_id": tid,
                "team_name": meta["team_name"],
                "incoming_count": incoming_count,
                "existing_count": existing_count,
                "ambiguous": meta["ambiguous"],
            }
        )

    valid_team_ids = [tid for tid in team_meta.keys() if tid is not None]
    teams_to_process = (
        [tid for tid in valid_team_ids if tid in selected_team_ids]
        if selected_team_ids is not None
        else valid_team_ids
    )

    all_processed_rows = []
    all_bookings = list(
        PitchBooking.objects.filter(
            status__in=["PENDING", "APPROVED"],
            start_date__year=inferred_season,
        ).select_related("pitch", "fixture")
    )

    for tid in teams_to_process:
        t_rows = parsed_incoming_by_team.get(tid, [])
        t_obj = next((t for t in teams if t.id == tid), None)
        existing_fixtures = list(
            Fixture.objects.filter(team_id=tid, start_date__year=inferred_season).select_related(
                "pitchbooking__pitch"
            )
        )

        matched_records = match_fixtures_for_refresh(
            team_id=tid,
            incoming_rows=t_rows,
            existing_fixtures_qs=existing_fixtures,
            is_play_cricket=False,
        )

        allocated_records = allocate_pitches_for_matches(
            records=matched_records,
            venues_qs=venues,
            pitches_qs=pitches,
            existing_bookings_qs=all_bookings,
            team_obj=t_obj,
        )

        all_processed_rows.extend(allocated_records)

    # Include unmatched team rows if not filtering or if selected_team_ids is None
    if selected_team_ids is None and None in parsed_incoming_by_team:
        all_processed_rows.extend(parsed_incoming_by_team[None])

    return Response(
        {
            "success": True,
            "inferred_season": inferred_season,
            "detected_teams": detected_teams,
            "rows": all_processed_rows,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_play_cricket_fixtures_view(request):
    """
    Fetches raw fixtures from ECB Play-Cricket v2 API, runs backend team and ground matching,
    detects teams present in the data, filters for HOME fixtures only, and returns enriched
    rows with change categorization (NEW, RESCHEDULED, UNCHANGED, REMOVED) and pitch allocation.
    """
    site_id = getattr(settings, "PLAY_CRICKET_SITE_ID", None)
    api_token = getattr(settings, "PLAY_CRICKET_API_KEY", None)
    base_url = getattr(settings, "PLAY_CRICKET_URL", "http://play-cricket.com")
    home_club_name = getattr(settings, "HOME_CLUB_NAME", "").lower()

    if not site_id or not api_token:
        return Response(
            {"detail": "Play-Cricket Site ID or API Key is not configured on the server."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    season = request.data.get("season", datetime.now().year)
    selected_team_ids = request.data.get("selected_team_ids")
    if selected_team_ids is not None:
        selected_team_ids = [int(tid) for tid in selected_team_ids]

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

        teams = list(Team.objects.all())
        pitches = list(
            Pitch.objects.filter(is_active=True).prefetch_related(
                "supported_lengths", "blocks_pitches"
            )
        )
        venues = list(Venue.objects.all())

        parsed_incoming_by_team = {}
        team_meta = {}

        for index, match in enumerate(raw_fixtures):
            home_team_name = match.get("home_team_name", "").strip()
            away_team_name = match.get("away_team_name", "").strip()

            # Skip away fixtures: Only process if our club is the home team
            if home_club_name and home_club_name not in home_team_name.lower():
                continue

            pc_id = str(match.get("id"))
            date_str = match.get("match_date", "").strip()
            time_str = match.get("match_time", "14:00").strip()
            ground_name = match.get("ground_name", "").strip()

            team_match = find_best_team_match(home_team_name, teams)
            opponent = away_team_name
            team_id = team_match["team_id"]
            team_ambiguous = team_match["ambiguous"]

            if not any(t.id == team_id for t in teams) or (
                home_team_name and not team_match["team_id"]
            ):
                away_team_match = find_best_team_match(away_team_name, teams)
                if away_team_match["team_id"]:
                    team_id = away_team_match["team_id"]
                    team_ambiguous = away_team_match["ambiguous"]
                    opponent = home_team_name

            try:
                parsed_date = datetime.strptime(date_str, "%d/%m/%Y").date().isoformat()
            except ValueError:
                parsed_date = ""

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

            parsed_row = {
                "id": f"row_{index}",
                "playCricketId": pc_id,
                "teamNameRaw": home_team_name,
                "teamId": team_id,
                "teamAmbiguous": team_ambiguous,
                "opponent": opponent,
                "date": parsed_date,
                "time": time_str,
                "timeSlot": time_slot,
                "pitchPref": ground_name,
                "clashReason": clash_reason,
                "selected": not clash_reason,
            }

            if team_id:
                parsed_incoming_by_team.setdefault(team_id, []).append(parsed_row)
                if team_id not in team_meta:
                    t_obj = next((t for t in teams if t.id == team_id), None)
                    team_meta[team_id] = {
                        "team_id": team_id,
                        "team_name": t_obj.name if t_obj else home_team_name,
                        "ambiguous": team_ambiguous,
                    }
            else:
                parsed_incoming_by_team.setdefault(None, []).append(parsed_row)

        # Also detect teams with existing fixtures in the DB for this season
        existing_team_ids = set(
            Fixture.objects.filter(start_date__year=season)
            .values_list("team_id", flat=True)
            .distinct()
        )
        for tid in existing_team_ids:
            if tid and tid not in team_meta:
                t_obj = next((t for t in teams if t.id == tid), None)
                if t_obj:
                    team_meta[tid] = {
                        "team_id": tid,
                        "team_name": t_obj.name,
                        "ambiguous": False,
                    }

        detected_teams = []
        for tid, meta in team_meta.items():
            incoming_count = len(parsed_incoming_by_team.get(tid, []))
            existing_count = Fixture.objects.filter(team_id=tid, start_date__year=season).count()
            detected_teams.append(
                {
                    "team_id": tid,
                    "team_name": meta["team_name"],
                    "incoming_count": incoming_count,
                    "existing_count": existing_count,
                    "ambiguous": meta["ambiguous"],
                }
            )

        valid_team_ids = [tid for tid in team_meta.keys() if tid is not None]
        teams_to_process = (
            [tid for tid in valid_team_ids if tid in selected_team_ids]
            if selected_team_ids is not None
            else valid_team_ids
        )

        all_processed_rows = []
        all_bookings = list(
            PitchBooking.objects.filter(
                status__in=["PENDING", "APPROVED"],
                start_date__year=season,
            ).select_related("pitch", "fixture")
        )

        for tid in teams_to_process:
            t_rows = parsed_incoming_by_team.get(tid, [])
            t_obj = next((t for t in teams if t.id == tid), None)
            existing_fixtures = list(
                Fixture.objects.filter(team_id=tid, start_date__year=season).select_related(
                    "pitchbooking__pitch"
                )
            )

            matched_records = match_fixtures_for_refresh(
                team_id=tid,
                incoming_rows=t_rows,
                existing_fixtures_qs=existing_fixtures,
                is_play_cricket=True,
            )

            allocated_records = allocate_pitches_for_matches(
                records=matched_records,
                venues_qs=venues,
                pitches_qs=pitches,
                existing_bookings_qs=all_bookings,
                team_obj=t_obj,
            )

            all_processed_rows.extend(allocated_records)

        if selected_team_ids is None and None in parsed_incoming_by_team:
            all_processed_rows.extend(parsed_incoming_by_team[None])

        return Response(
            {
                "success": True,
                "season": season,
                "detected_teams": detected_teams,
                "rows": all_processed_rows,
            },
            status=status.HTTP_200_OK,
        )

    except requests.RequestException as req_err:
        return Response(
            {"detail": f"Failed to connect to Play-Cricket: {str(req_err)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
