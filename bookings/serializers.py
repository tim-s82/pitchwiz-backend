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
        fields = ["id", "name"]


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
    # Make single pitch optional so multi-pitch ground maintenance requests can pass validation
    pitch = serializers.PrimaryKeyRelatedField(
        queryset=Pitch.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = PitchBooking
        fields = [
            'id', 'fixture', 'pitch', 'pitches', 'booking_type',
            'start_date', 'end_date', 'time_slot',
            'requires_teas', 'requires_drinks', 'requested_by',
            'external_contact_name', 'external_contact_email',
            'status', 'rejection_reason', 'notes'
        ]
        read_only_fields = ['status', 'rejection_reason', 'requested_by']


class CateringRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CateringRequest
        fields = "__all__"


class BookingChangeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingChangeRequest
        fields = "__all__"
