# Training Session Booking — Implementation Progress Log

This log tracks the step-by-step implementation of the Training Session Booking feature according to `training_session_plan.md`.

## Phase 1: Backend Implementation

- [x] **1. `bookings/models.py`**
  - [x] Add `("TRAINING", "Training Session")` to `PitchBooking.BOOKING_TYPES`
  - [x] Add `teams = models.ManyToManyField(Team, related_name="training_bookings", blank=True, help_text="Teams invited to this training session. Empty = club-wide.")` to `PitchBooking`
  - [x] Update `PitchBooking.__str__` to format `TRAINING` sessions (`Training ({team_names}): {pitch} on {date}`)
- [x] **2. Database Migrations**
  - [x] Run `python manage.py makemigrations bookings` (generated `0008_pitchbooking_teams_alter_pitchbooking_booking_type.py`)
  - [x] Verified migration applied cleanly to local database
- [x] **3. `bookings/serializers.py`**
  - [x] Add `teams = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), many=True, required=False, default=list)` to `PitchBookingSerializer`
  - [x] Add `"teams"` to `Meta.fields`
  - [x] Update `validate()` to reject fixture on `TRAINING` and require pitch
  - [x] Override `create()` and `update()` in `PitchBookingSerializer` to set `teams` M2M
- [x] **4. `bookings/views.py`**
  - [x] Add `TRAINING` branch in `PitchBookingViewSet.create()`
  - [x] Enforce team manager permissions (only managed teams can be booked for training; privileged users can book any/none)
- [x] **5. Backend Tests (`bookings/tests/test_training_bookings.py`)**
  - [x] Model tests: `TRAINING` choice, `teams` M2M persistence, `__str__`
  - [x] Serializer tests: validates without `fixture`, rejects `fixture` on `TRAINING`, `teams` round-trip
  - [x] View tests: Manager own team -> 201 PENDING; Manager unmanaged team -> 403; Manager empty teams -> 403; Secretary/Admin -> 201 APPROVED; club-wide (`teams=[]`) -> 201 APPROVED; fixture provided -> 400; missing pitch -> 400
  - [x] All 153 tests pass, formatted with `black` and `isort`

## Phase 2: Frontend Implementation

- [x] **6. `useCalendarState.js`**
  - [x] Add `bookingType: "FIXTURE"` and `trainingTeamIds: []` to initial `modalData`
  - [x] Update reset calls in `handleCellClick`
- [x] **7. `CalendarView.jsx` & `App.jsx`**
  - [x] Update `handleFormSubmit` payload and validation for `TRAINING`
  - [x] Forward `booking_type` and `teams` in `App.jsx:handleBookingCreated` to API
- [x] **8. `BookingCreateModal.jsx`**
  - [x] Import `Dumbbell`, `Users` from `lucide-react`
  - [x] Add `sortedPitches` with Net-first sorting when `bookingType === "TRAINING"`
  - [x] Add Booking Type toggle (`Fixture` vs `Training Session`)
  - [x] Conditionally show team dropdown & opponent input for `FIXTURE`
  - [x] Conditionally show team toggle pills + Club-wide button for `TRAINING` (excluding external teams)
  - [x] Hide catering checkboxes when `TRAINING`
  - [x] Dynamic modal title ("Request Training Session" vs "Request Pitch Booking")
- [x] **9. `useConflictDetection.js`**
  - [x] Label training bookings in `getCellStatus` ("Training — {teams}" or "Training — Club-wide")
  - [x] Extend `canEditBooking` for training bookings
- [x] **10. `CellContent.jsx`**
  - [x] Add `Dumbbell` badge and cyan/sky visual styling for training bookings
- [x] **11. Frontend Testing & Verification**
  - [x] Added `src/tests/trainingBookings.test.js` covering training status labelling and permissions
  - [x] Ran `npm run lint` (0 errors, 0 warnings)
  - [x] Ran `npm run test` (all 11 tests pass)
  - [x] Ran `npm run build` (production build succeeds)

---
*Status: Complete. All plan items successfully implemented and verified.*
