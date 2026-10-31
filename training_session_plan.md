# Training Session Booking — Implementation Plan

> **Status:** Designed & confirmed. Ready for implementation.  
> **Originated:** Conversation `09bfcf85-0a98-4f3b-9f18-7c1b55d65ff6` (2026-10-24).

---

## Confirmed Design Decisions

| # | Decision |
|---|----------|
| 1 | Catering checkboxes are **hidden** for training bookings |
| 2 | Booking change requests apply to training — no special handling needed |
| 3 | Existing "notify secretaries" email template is reused for this iteration |
| 4 | **External teams are excluded** from the training team picker |
| 5 | Pitch sort-order flip (Net first) applies only to the **modal dropdown**, not the calendar grid |
| 6 | Serializer must **reject** any `TRAINING` booking that also supplies a `fixture` FK |
| 7 | `teams=[]` (club-wide) booking shows a **"Club-wide" badge** in the calendar cell |

---

## Requirements Summary

- A team manager can create a booking request for either a **fixture** (existing) or a **training session** (new).
- For a training session, multiple teams can be invited — but only teams where the requesting user is listed as a manager.
- Multi-team selection uses **toggle pills** (same pattern as team-manager picker in `TeamsManager.jsx`).
- When booking a training session the pitch dropdown sorts: **Net → Outfield → Youth → Main** (reverse of fixture order).
- An **Admin or Fixture Secretary** can book a club-wide training session with `teams=[]` (not linked to any team).

---

## Backend Changes

### 1. `bookings/models.py`

#### a) Add `TRAINING` to `PitchBooking.BOOKING_TYPES`

```python
BOOKING_TYPES = [
    ("FIXTURE", "Fixture"),
    ("GROUND_MAINTENANCE", "Ground Maintenance"),
    ("TRAINING", "Training Session"),          # NEW
]
```

#### b) Add `teams` M2M field to `PitchBooking`

```python
teams = models.ManyToManyField(
    Team,
    related_name="training_bookings",
    blank=True,
    help_text="Teams invited to this training session. Empty = club-wide.",
)
```

Place this field after the existing `fixture` and `pitch` fields.

#### c) Update `PitchBooking.__str__`

```python
def __str__(self):
    if self.booking_type == "GROUND_MAINTENANCE":
        return f"Maintenance: {self.pitch} on {self.start_date}"
    if self.booking_type == "TRAINING":
        team_names = ", ".join(t.name for t in self.teams.all()) or "Club-wide"
        return f"Training ({team_names}): {self.pitch} on {self.start_date}"
    if self.start_date == self.end_date:
        return f"{self.pitch} on {self.start_date} ({self.get_time_slot_display()})"
    return f"{self.pitch} from {self.start_date} to {self.end_date}"
```

---

### 2. `bookings/migrations/`

Run `python manage.py makemigrations bookings`. The migration will:
- Add `TRAINING` as a new choice on `booking_type` (no schema change, just a validator update).
- Add the `PitchBooking_teams` through-table for the M2M.

---

### 3. `bookings/serializers.py`

#### a) Add `teams` as a writable M2M field on `PitchBookingSerializer`

```python
teams = serializers.PrimaryKeyRelatedField(
    queryset=Team.objects.all(),
    many=True,
    required=False,
    default=list,
)
```

Add `"teams"` to `Meta.fields`.

#### b) Update `validate()`

```python
def validate(self, attrs):
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

    # FIXTURE: existing validations
    if not attrs.get("pitch"):
        raise serializers.ValidationError(
            {"pitch": ["This field is required for standard bookings."]}
        )
    return attrs
```

#### c) Override `create()` to handle M2M

```python
def create(self, validated_data):
    teams = validated_data.pop("teams", [])
    instance = super().create(validated_data)
    instance.teams.set(teams)
    return instance
```

---

### 4. `bookings/views.py`

#### a) Add a Training Session branch inside `PitchBookingViewSet.create()`

Insert **between** the existing Ground Maintenance check (block 1) and the Standard Fixture check (block 2):

```python
# 1b. Training Session Flow
if booking_type == "TRAINING":
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
        team_ids = [int(tid) for tid in data.get("teams", [])]
        managed_ids = set(
            Team.objects.filter(managers=user).values_list("id", flat=True)
        )
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
            booking = PitchBooking.objects.get(id=response.data["id"])
            team_ids = [int(tid) for tid in data.get("teams", [])]
            booking.teams.set(team_ids)
            logger.info(
                "Training session booking #%s created by user %s (teams: %s).",
                booking.id,
                user.id,
                team_ids or "club-wide",
            )
    return response
```

> **Note:** The serializer's `create()` override also sets `teams`, so calling `booking.teams.set()` in the view is redundant — keep only one of these approaches for clarity. Prefer the **serializer `create()` override** (step 3c) and remove the `booking.teams.set()` call from the view, keeping only the permission check in the view.

#### b) `perform_create()` — no change required

Team managers go `PENDING`; secretaries/admins go `APPROVED`. The existing logic covers this correctly.

---

### 5. Tests — `bookings/tests/`

New test file: `bookings/tests/test_training_bookings.py`

| Test | Assertion |
|------|-----------|
| Model: `TRAINING` choice accepted | `PitchBooking.objects.create(booking_type="TRAINING", ...)` saves without error |
| Model: `teams` M2M persists | `booking.teams.set([team1, team2])` → `booking.teams.count() == 2` |
| Serializer: validates without `fixture` | No `ValidationError` when `fixture` is absent |
| Serializer: rejects `fixture` on TRAINING | `ValidationError` raised when `fixture` is provided |
| Serializer: `teams` IDs round-trip | `teams` appears in serializer output |
| View — Manager, own team → 201 PENDING | Manager books training for their own team |
| View — Manager, unmanaged team → 403 | Rejected with teams permission error |
| View — Secretary, any teams → 201 APPROVED | Secretary books training for any team, auto-approved |
| View — Admin, `teams=[]` → 201 APPROVED | Club-wide booking accepted with empty teams list |
| View — `fixture` provided → 400 | Rejected with fixture validation error |

---

## Frontend Changes

### 6. `useCalendarState.js` — extend `modalData` initial state

```js
const [modalData, setModalData] = useState({
  pitchId: "",
  date: "",
  timeSlot: "ALL_DAY",
  bookingType: "FIXTURE",       // NEW — "FIXTURE" | "TRAINING"
  teamId: "",
  opponent: "",
  trainingTeamIds: [],          // NEW — for TRAINING multi-select
  requiresTeas: false,
  requiresDrinks: false,
  notes: "",
  isMultiDay: false,
  endDate: "",
});
```

Also update the two `setModalData(...)` calls inside `handleCellClick` (both the `PENDING_MULTI` branch and the default branch) to include the new fields with their defaults:

```js
setModalData({
  pitchId: pitchId.toString(),
  date: dateStr,
  timeSlot,
  bookingType: "FIXTURE",
  teamId: selectedTeamId !== "all" ? selectedTeamId : "",
  opponent: "",
  trainingTeamIds: [],
  requiresTeas: false,
  requiresDrinks: false,
  notes: "",
  isMultiDay: false,
  endDate: dateStr,
});
```

---

### 7. `CalendarView.jsx` — update `handleFormSubmit`

Replace the current validation and payload block:

```js
const handleFormSubmit = async (e) => {
  e.preventDefault();
  const isTraining = modalData.bookingType === "TRAINING";

  // Validation
  if (!modalData.pitchId || !modalData.date) {
    alert("Please select a pitch and date.");
    return;
  }
  if (!isTraining && (!modalData.teamId || !modalData.opponent)) {
    alert("Please fill in all required fields.");
    return;
  }

  const payload = {
    pitch: parseInt(modalData.pitchId, 10),
    booking_type: modalData.bookingType,
    start_date: modalData.date,
    end_date: modalData.isMultiDay ? modalData.endDate : modalData.date,
    time_slot: modalData.timeSlot,
    notes: modalData.notes,
    ...(isTraining
      ? {
          teams: modalData.trainingTeamIds,
        }
      : {
          requires_teas: modalData.requiresTeas,
          requires_drinks: modalData.requiresDrinks,
          fixture_team: parseInt(modalData.teamId, 10),
          fixture_opponent: modalData.opponent,
        }),
  };

  try {
    await onBookingCreated(payload);
    setIsModalOpen(false);
  } catch (err) {
    console.error(err);
    alert(`Failed to submit request:\n${err.message}`);
  }
};
```

---

### 8. `BookingCreateModal.jsx` — major update

#### a) Import additions

```js
import { Calendar, X, Dumbbell, Users } from "lucide-react";
```

#### b) Pitch sorting inside the modal

Add this `useMemo` at the top of the component body:

```js
const sortedPitches = useMemo(() => {
  const rank =
    modalData.bookingType === "TRAINING"
      ? { net: 1, outfield: 2, youth: 3, main: 4 }   // training: nets first
      : { main: 1, youth: 2, outfield: 3, net: 4 };   // fixture: main first
  return [...pitches].sort(
    (a, b) =>
      (rank[(a.entity_type || "").toLowerCase()] || 99) -
      (rank[(b.entity_type || "").toLowerCase()] || 99)
  );
}, [pitches, modalData.bookingType]);
```

Use `sortedPitches` in the pitch `<select>` instead of `pitches`.

#### c) Booking type toggle (top of form, above the pitch/time-slot grid)

```jsx
{/* Booking Type Toggle */}
<div className="flex rounded-xl overflow-hidden border border-slate-700 mb-2">
  {[
    { value: "FIXTURE", label: "Fixture", Icon: Calendar },
    { value: "TRAINING", label: "Training Session", Icon: Dumbbell },
  ].map(({ value, label, Icon }) => {
    const active = modalData.bookingType === value;
    return (
      <button
        key={value}
        type="button"
        onClick={() =>
          setModalData({
            ...modalData,
            bookingType: value,
            teamId: "",
            opponent: "",
            trainingTeamIds: [],
          })
        }
        className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-semibold font-display transition-colors ${
          active
            ? "bg-emerald-600/80 text-white"
            : "bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        }`}
      >
        <Icon size={14} />
        {label}
      </button>
    );
  })}
</div>
```

#### d) Fixture-mode fields (conditionally shown)

Wrap the **Team dropdown** and **Opponent input** in `{modalData.bookingType === "FIXTURE" && (...)}`.

#### e) Training-mode fields (new, conditionally shown)

Shown when `modalData.bookingType === "TRAINING"`:

```jsx
{modalData.bookingType === "TRAINING" && (
  <div>
    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
      Invited Teams
      <span className="ml-1 text-slate-500 normal-case font-normal">
        (leave empty for club-wide)
      </span>
    </label>
    <div className="flex flex-wrap gap-2">
      {/* Club-wide pill — Admin/Secretary only */}
      {(currentUser?.roles?.includes("ADMIN") ||
        currentUser?.roles?.includes("FIXTURE_SECRETARY")) && (
        <button
          type="button"
          onClick={() =>
            setModalData({ ...modalData, trainingTeamIds: [] })
          }
          className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition flex items-center gap-1.5 ${
            modalData.trainingTeamIds.length === 0
              ? "bg-teal-500/20 text-teal-400 border-teal-500/40"
              : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700"
          }`}
        >
          <Users size={13} />
          Club-wide
        </button>
      )}

      {/* Individual team pills */}
      {allowedTeams
        .filter((t) => !t.is_external)
        .map((t) => {
          const isSelected = modalData.trainingTeamIds.includes(t.id);
          return (
            <button
              type="button"
              key={t.id}
              onClick={() => {
                const next = isSelected
                  ? modalData.trainingTeamIds.filter((id) => id !== t.id)
                  : [...modalData.trainingTeamIds, t.id];
                setModalData({ ...modalData, trainingTeamIds: next });
              }}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition flex items-center gap-1.5 ${
                isSelected
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700"
              }`}
            >
              {t.name}
            </button>
          );
        })}
    </div>
  </div>
)}
```

#### f) Hide catering checkboxes for training

Wrap the teas/drinks block in `{modalData.bookingType === "FIXTURE" && (...)}`.

#### g) Modal title & icon

```jsx
<h3 className="text-lg font-bold font-display text-slate-100">
  {modalData.bookingType === "TRAINING"
    ? "Request Training Session"
    : "Request Pitch Booking"}
</h3>
```

---

### 9. `useConflictDetection.js` — label training bookings

In `getCellStatus`, after the `GROUND_MAINTENANCE` check and before the fixture label logic, add a training branch:

```js
if (approvedBooking.booking_type === "TRAINING") {
  const teamList = approvedBooking.teams?.length
    ? approvedBooking.teams
        .map((tid) => teams.find((t) => t.id === tid)?.name)
        .filter(Boolean)
        .join(", ")
    : null;
  return {
    type: "BOOKED",
    booking: approvedBooking,
    label: teamList ? `Training — ${teamList}` : "Training — Club-wide",
    status: approvedBooking.status,
    isMaintenance: false,
    isTraining: true,
  };
}
```

> **Note:** This requires the API to return `teams` as a list of IDs on each `PitchBooking` object. Confirm the serializer includes `"teams"` in its output fields (it will, once step 3a is done).

---

### 10. `CellContent.jsx` — training visual treatment

Add a `Dumbbell` icon import. In the approved/pending render block, detect training and apply a distinct colour scheme (cyan/sky instead of emerald):

```jsx
const isTraining = cell.isTraining;

// In the className ternary:
isMaintenance
  ? "bg-amber-950/40 border-amber-800/80 hover:border-amber-500 shadow-sm"
  : isTraining
    ? "bg-cyan-950/30 border-cyan-900/80 hover:border-cyan-500 shadow-sm"
    : isApproved
      ? "bg-emerald-950/30 border-emerald-900/80 hover:border-blue-500 shadow-sm"
      : "bg-amber-950/20 border-amber-900/50 hover:border-blue-500"

// Badge:
isTraining ? (
  <span className="text-[9px] px-1.5 py-0.5 rounded font-extrabold uppercase font-display truncate bg-cyan-900/50 text-cyan-400 flex items-center gap-1">
    <Dumbbell size={10} />
    Training
  </span>
) : /* existing Maintenance / Booked / Pending badges */
```

The cell label already shows `"Training — Club-wide"` or `"Training — Team A, Team B"` from `useConflictDetection`.

---

### 11. `canEditBooking` in `useConflictDetection.js`

Extend the team-manager check to also allow editing training bookings for managed teams:

```js
if (currentUser.roles?.includes("TEAM_MANAGER")) {
  if (booking.requested_by === currentUser.id) return true;
  // Fixture bookings
  if (booking.fixture) {
    const fix = fixtures.find((f) => f.id === booking.fixture);
    if (fix) {
      const team = teams.find((t) => t.id === fix.team);
      if (team && team.managers?.includes(currentUser.id)) return true;
    }
  }
  // Training bookings
  if (booking.booking_type === "TRAINING" && booking.teams?.length) {
    const manages = booking.teams.some((tid) => {
      const team = teams.find((t) => t.id === tid);
      return team?.managers?.includes(currentUser.id);
    });
    if (manages) return true;
  }
}
```

---

## API Contract

### `POST /api/pitchbookings/` — Training Session

**Request:**
```json
{
  "pitch": 3,
  "booking_type": "TRAINING",
  "start_date": "2026-05-10",
  "end_date": "2026-05-10",
  "time_slot": "EVENING",
  "teams": [1, 4],
  "notes": "Pre-season nets"
}
```

**Response (201):**
```json
{
  "id": 42,
  "booking_type": "TRAINING",
  "teams": [1, 4],
  "pitch": 3,
  "status": "PENDING",
  "start_date": "2026-05-10",
  "end_date": "2026-05-10",
  "time_slot": "EVENING",
  "notes": "Pre-season nets",
  "fixture": null,
  "requires_teas": false,
  "requires_drinks": false
}
```

For a club-wide session, send `"teams": []`.

---

## Implementation Order

1. **Backend**
   1. `models.py` — add `TRAINING` choice + `teams` M2M field
   2. `makemigrations bookings`
   3. `serializers.py` — `teams` field, `create()` override, `validate()` update
   4. `views.py` — training branch + team-scope permission check
   5. Write & run tests in `bookings/tests/test_training_bookings.py`

2. **Frontend** (after backend deployed / local server running)
   1. `useCalendarState.js` — extend `modalData` with `bookingType` + `trainingTeamIds`
   2. `CalendarView.jsx` — update `setModalData` reset calls + `handleFormSubmit`
   3. `BookingCreateModal.jsx` — type toggle, team pills, pitch re-sort, hide catering, title
   4. `useConflictDetection.js` — training label + `canEditBooking` extension
   5. `CellContent.jsx` — training colour scheme + Dumbbell badge
