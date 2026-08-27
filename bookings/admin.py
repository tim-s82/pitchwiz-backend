# pyrefly: ignore [missing-import]
from django.contrib import admin

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

# Register your models here.
admin.site.register(Venue)
admin.site.register(PitchLength)
admin.site.register(Pitch)
admin.site.register(Team)
admin.site.register(Fixture)
admin.site.register(PitchBooking)
admin.site.register(CateringRequest)
admin.site.register(BookingChangeRequest)
