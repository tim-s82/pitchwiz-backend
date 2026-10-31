import logging

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
from rest_framework import serializers

logger = logging.getLogger(__name__)


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "name", "is_default"]


class PitchLengthSerializer(serializers.ModelSerializer):
    class Meta:
        model = PitchLength
        fields = ["id", "length_yards", "description"]


class PitchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pitch
        fields = [
            "id",
            "venue",
            "name",
            "pitch_type",
            "entity_type",
            "supported_lengths",
            "blocks_pitches",
            "is_active",
        ]


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "name", "managers", "required_length", "is_external"]


class FixtureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fixture
        fields = ["id", "team", "opponent", "start_date", "end_date", "play_cricket_id"]


class PitchBookingSerializer(serializers.ModelSerializer):
    pitches = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    pitch = serializers.PrimaryKeyRelatedField(
        queryset=Pitch.objects.all(), required=False, allow_null=True
    )
    teams = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        many=True,
        required=False,
        default=list,
    )

    class Meta:
        model = PitchBooking
        fields = [
            "id",
            "fixture",
            "pitch",
            "pitches",
            "teams",
            "booking_type",
            "start_date",
            "end_date",
            "time_slot",
            "requires_teas",
            "requires_drinks",
            "requested_by",
            "external_contact_name",
            "external_contact_email",
            "status",
            "rejection_reason",
            "notes",
        ]
        read_only_fields = ["status", "rejection_reason", "requested_by"]

    def validate(self, attrs):
        # If it's a ground maintenance booking, a single pitch isn't required
        # because it uses the 'pitches' array instead.
        booking_type = attrs.get("booking_type", "FIXTURE")
        if booking_type == "GROUND_MAINTENANCE":
            return attrs

        if booking_type == "TRAINING":
            # Reject if a fixture FK was also provided
            if attrs.get("fixture"):
                raise serializers.ValidationError(
                    {"fixture": ["Training bookings cannot be linked to a fixture."]}
                )
            if not attrs.get("pitch"):
                raise serializers.ValidationError(
                    {"pitch": ["This field is required for training bookings."]}
                )
            return attrs

        # For standard bookings, ensure a single pitch is provided
        if not attrs.get("pitch"):
            logger.warning(
                "PitchBooking validation failed: Standard booking missing 'pitch' field "
                "(booking_type: %s).",
                booking_type,
            )
            raise serializers.ValidationError(
                {"pitch": ["This field is required for standard bookings."]}
            )

        return attrs

    def create(self, validated_data):
        teams = validated_data.pop("teams", [])
        instance = super().create(validated_data)
        instance.teams.set(teams)
        return instance

    def update(self, instance, validated_data):
        if "teams" in validated_data:
            teams = validated_data.pop("teams")
            instance.teams.set(teams)
        return super().update(instance, validated_data)


class CateringRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CateringRequest
        fields = "__all__"


class BookingChangeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingChangeRequest
        fields = "__all__"
