from rest_framework import serializers

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

    class Meta:
        model = PitchBooking
        fields = [
            "id",
            "fixture",
            "pitch",
            "pitches",
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

        # For standard bookings, ensure a single pitch is provided
        if not attrs.get("pitch"):
            raise serializers.ValidationError(
                {"pitch": ["This field is required for standard bookings."]}
            )

        return attrs


class CateringRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CateringRequest
        fields = "__all__"


class BookingChangeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingChangeRequest
        fields = "__all__"
