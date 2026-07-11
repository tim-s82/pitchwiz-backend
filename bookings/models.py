from django.contrib.auth.models import User
from django.db import models


class Venue(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class PitchLength(models.Model):
    length_yards = models.IntegerField(unique=True)
    description = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.length_yards} Yards - {self.description}"


class Pitch(models.Model):
    PITCH_TYPES = [
        ("GRASS", "Grass"),
        ("ASTRO", "Artificial / Astro"),
    ]
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="pitches")
    name = models.CharField(max_length=50)
    pitch_type = models.CharField(max_length=10, choices=PITCH_TYPES)

    supported_lengths = models.ManyToManyField(PitchLength, blank=True)
    blocks_pitches = models.ManyToManyField(
        "self", symmetrical=False, blank=True, null=True
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.venue.name} - {self.name}"


class Team(models.Model):
    name = models.CharField(max_length=100)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    required_length = models.ForeignKey(
        PitchLength, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_external = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} {'(External)' if self.is_external else ''}".strip()


class Fixture(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    opponent = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()
    play_cricket_id = models.CharField(
        max_length=50, blank=True, null=True, unique=True
    )

    def __str__(self):
        return f"{self.team.name} vs {self.opponent}"


class PitchBooking(models.Model):
    TIME_SLOTS = [
        ("MORNING", "Morning"),
        ("AFTERNOON", "Afternoon"),
        ("EVENING", "Evening"),
        ("ALL_DAY", "All Day"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending Approval"),
        ("APPROVED", "Confirmed"),
        ("DENIED", "Denied"),
    ]

    fixture = models.OneToOneField(
        Fixture, on_delete=models.CASCADE, null=True, blank=True
    )
    pitch = models.ForeignKey(Pitch, on_delete=models.CASCADE)

    start_date = models.DateField()
    end_date = models.DateField()
    time_slot = models.CharField(max_length=15, choices=TIME_SLOTS, default="ALL_DAY")

    requires_teas = models.BooleanField(default=False)
    requires_drinks = models.BooleanField(default=False)

    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    external_contact_name = models.CharField(max_length=100, blank=True)
    external_contact_email = models.EmailField(blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    notes = models.TextField(blank=True)

    def __str__(self):
        if self.start_date == self.end_date:
            return f"{self.pitch} on {self.start_date} ({self.get_time_slot_display()})"
        return f"{self.pitch} from {self.start_date} to {self.end_date}"
