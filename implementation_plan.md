# God-Component Decomposition Plan

Break up the three oversized components into focused sub-components, guided by the design review recommendations.

---

## Proposed Changes

### 1. `CalendarView.jsx` (1,667 lines → target ~450 lines)

Extract into a `calendar/` sub-folder:

#### [NEW] `src/components/calendar/useCalendarState.js`
Custom hook holding all `useState` declarations and derived state (sorted venues, sorted teams, filtered pitches, dates list, `allowedTeams`). Also owns `shiftWeek`, `shiftMobileDay`, `isExternalUser`, `isOnlyGroundstaff`, `isDateInBooking`.

#### [NEW] `src/components/calendar/useConflictDetection.js`
Custom hook exporting `getCellStatus` and `canEditBooking` — pure computation functions that depend on `bookings`, `pitches`, `fixtures`, `teams`, and `selectedStatus`.

#### [NEW] `src/components/calendar/BookingCreateModal.jsx`
The "Request Pitch Booking" modal (lines 1038–1314). Props: `isOpen`, `onClose`, `modalData`, `setModalData`, `pitches`, `venues`, `teams`, `pitchLengths`, `allowedTeams`, `currentUser`, `onSubmit`.

#### [NEW] `src/components/calendar/BookingEditModal.jsx`
The "Edit / Cancel Booking" modal (lines 1325–1529). Props: `isOpen`, `onClose`, `editData`, `editForm`, `setEditForm`, `onSubmit`, `onDelete`, `saving`, `pitches`, `venues`.

#### [NEW] `src/components/calendar/CellContent.jsx`
The `CellContent` function component (lines 1534–1667). Already a standalone function — just move it to its own file. Props: `cell`, `onClick`, `compact`, `isExternal`.

#### [NEW] `src/components/calendar/CalendarToolbar.jsx`
The header/filter control panel (lines 527–668). Props: `startDateStr`, `onShiftWeek`, `sortedVenues`, `selectedVenueId`, `setSelectedVenueId`, `sortedTeams`, `selectedTeamId`, `setSelectedTeamId`, `selectedStatus`, `setSelectedStatus`, `viewMode`, `setViewMode`, `mobileLayoutMode`, `setMobileLayoutMode`, `filteredTeam`, `pitchLengths`.

#### [MODIFY] [`CalendarView.jsx`](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-frontend/src/components/CalendarView.jsx)
Reduced to ~450 lines: imports the above, renders the mobile views + desktop matrix, and composes everything together.

---

### 2. `SecretaryDashboard.jsx` (1,210 lines → target ~350 lines)

Extract into a `secretary/` sub-folder:

#### [NEW] `src/components/secretary/useConflictDetection.js`
Extracts `detectCompetingPending` and `detectConflicts` logic (lines 93–239). Takes `bookings`, `pitches`, `fixtures`, `teams`, `pitchLengths` as parameters.

#### [NEW] `src/components/secretary/RejectModal.jsx`
The inline rejection reason modal (rendered when `rejectModal.open`). Props: `isOpen`, `reason`, `setReason`, `onSubmit`, `onClose`.

#### [NEW] `src/components/secretary/ConfirmApproveModal.jsx`
The "competing bookings" approval confirmation modal. Props: `isOpen`, `booking`, `competingBookings`, `isSubmitting`, `onConfirm`, `onClose`, `teams`, `fixtures`, `pitches`, `venues`.

#### [NEW] `src/components/secretary/BookingEditModal.jsx`
The secretary-side edit/delete booking modal (lines ~720–890). Same shape as CalendarView's edit modal but drives `onBookingUpdated` / `onBookingDeleted` via the dashboard's handlers.

#### [NEW] `src/components/secretary/ChangeRequestsTab.jsx`
The "Change Requests" tab panel and its nested rejection modal. Owns `changeRequests` state, `fetchChangeRequests`, `handleApproveChange`, `handleRejectChange`, `submitChangeRejection`. Uses `api.js` instead of raw `fetch` (addresses the API layer major issue simultaneously).

#### [MODIFY] [`SecretaryDashboard.jsx`](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-frontend/src/components/SecretaryDashboard.jsx)
Reduced to ~350 lines: tab navigation, `pendingBookings` / `resolvedBookings` lists, top-level handlers, and composition of the extracted modals/tabs.

---

### 3. `VenuesManager.jsx` (909 lines → target ~250 lines)

Extract into a `venues/` sub-folder:

#### [NEW] `src/components/venues/Toast.jsx`
Shared toast notification component (already used in `TeamsManager.jsx` too — a single shared version prevents duplication). Props: `toast` `{ message, type }`.

#### [NEW] `src/components/venues/VenueForm.jsx`
Add/edit venue form panel. Props: `editingVenue`, `venueName`, `setVenueName`, `venueIsDefault`, `setVenueIsDefault`, `onSubmit`, `onCancel`.

#### [NEW] `src/components/venues/PitchForm.jsx`
Add/edit pitch form panel. Props: all pitch form state + `venues`, `pitches`, `pitchLengths`, `onSubmit`, `onCancel`.

#### [NEW] `src/components/venues/PitchLengthForm.jsx`
Add/edit pitch length form panel. Props: `editingLength`, `lengthYards`, `setLengthYards`, `lengthDescription`, `setLengthDescription`, `onSubmit`, `onCancel`.

#### [NEW] `src/components/venues/DeleteConfirmModal.jsx`
Delete confirmation overlay. Props: `target`, `onConfirm`, `onClose`.

#### [MODIFY] [`VenuesManager.jsx`](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-frontend/src/components/VenuesManager.jsx)
Reduced to ~250 lines: tab navigation, list rendering for venues/pitches/pitch-lengths, and orchestration of the form/modal components.

---

## Bonus: Shared Components

#### [NEW] `src/components/shared/Toast.jsx`
Single shared toast used by both `VenuesManager` and `TeamsManager` (and any future component). Eliminates duplication.

---

## Open Questions

> [!IMPORTANT]
> **`alert()` calls** — the design review flags 6+ `alert()` calls in `CalendarView.jsx` as a major issue. The fix is to use the toast system. Should I replace these with the new shared `Toast` component **as part of this refactor**, or handle it in a separate pass?

> [!IMPORTANT]
> **`SecretaryDashboard` raw `fetch` calls** — `fetchChangeRequests`, `handleApproveChange`, `handleRejectChange`, `handleProposeAlternative` all bypass `api.js`. Should I migrate these to `api.js` as part of this refactor, or leave that to the API-layer consolidation pass?

---

## Verification Plan

### Manual Verification
- Open the calendar, create a booking, edit it, delete it — all three modals should still work correctly.
- On mobile, test the single-day and single-pitch views.
- In the Secretary Dashboard, approve a booking, deny a booking, and check the conflict detection.
- In VenuesManager, add/edit/delete a venue, pitch, and pitch length.

### Automated
- No existing test coverage for these components — no tests to break.

---

## Execution Order

1. Create `shared/Toast.jsx`
2. Create `calendar/` sub-components → refactor `CalendarView.jsx`
3. Create `secretary/` sub-components → refactor `SecretaryDashboard.jsx`
4. Create `venues/` sub-components → refactor `VenuesManager.jsx`
