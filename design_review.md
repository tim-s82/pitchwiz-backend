# PitchWiz Design Review

## Code Review Summary

PitchWiz is a well-structured, feature-complete cricket pitch booking application with a clear separation between a Django REST Framework backend and a React/Tailwind CSS frontend. The UI is visually polished with a consistent dark-mode design system. The primary architectural concerns are (1) the monolithic `App.jsx` and `CalendarView.jsx` carrying too much responsibility, and (2) inconsistent use of the centralised API service (`api.js`) — several components bypass it with raw `fetch` calls. The backend is clean and readable, but has a permission architecture that is duplicated across two layers and an exception-handling syntax bug in production code.

---

## Critical Issues (Must Fix)

- **[RESOLVED] `bookings/views.py:380`** — **SyntaxError in `import_fixtures_view`**: `except ValueError, IndexError:` is Python 2 syntax. Python 3 requires `except (ValueError, IndexError):`. This will cause an `ImportError`/`SyntaxError` at startup in Python 3, meaning the entire application will fail to run with this code present. **Fix:** change to `except (ValueError, IndexError):`.

- **[RESOLVED] `src/components/AuthScreens.jsx:139`** — **API endpoint mismatch**: `ForcePasswordResetScreen` calls `/api/users/change_password` (underscore), but the actual backend URL is `/api/users/change-password` (hyphen, confirmed at `users/urls.py`). This means forced password resets always silently fail. **Fix:** change the URL to `/api/users/change-password`.

- **[RESOLVED] `src/App.jsx:72–78`** — **Conditional API method call with inline fallback fetch**: The `loadData` function checks `api.getMe ? api.getMe() : fetch(...)`. Since `getMe` is always defined in `api.js`, the fallback branch is dead code — but it also embeds auth header construction inline. This is fragile; if `api.js` is ever refactored, a regression is easy to miss. More importantly, the fallback branch duplicates auth token logic that already lives in `apiRequest()`. **Fix:** remove the conditional and call `api.getMe()` directly.

---

## Major Issues (Should Fix)

### Architecture / Design

- **[RESOLVED] `src/components/CalendarView.jsx`** — **God component (1,667 lines)**: This single file contains calendar rendering, mobile view logic, booking creation modal, booking edit modal, delete confirmation, ground maintenance modal state, and outfield blocking logic. It has 12+ `useState` declarations. This makes the component extremely hard to test, reuse, or reason about in isolation. **Recommendation:** extract at minimum `BookingCreateModal`, `BookingEditModal`, and the cell status calculation logic (`getCellStatus`) into their own files. The outfield/blocking logic is a good candidate for a custom hook (`useConflictDetection`).

- **[RESOLVED] `src/components/SecretaryDashboard.jsx` (1,210 lines) and `VenuesManager.jsx` (909 lines)** — **Oversized components**: The same problem as `CalendarView.jsx`. `SecretaryDashboard.jsx` contains conflict detection logic, change request fetching, rejection modals, approval modals, and edit/delete forms — all in one file. **Recommendation:** each modal and tab panel should be its own component.

- **[RESOLVED] `src/App.jsx:234`** — **`hasRole` defined after early return**: `hasRole` is declared at line 234, but it is called in a `useEffect` at line 99 (inside the `restrictedViews` computation). Because `hasRole` is a function declaration via arrow-function const, the call inside `useEffect` at line 99 will throw a `ReferenceError` (temporal dead zone). **Fix:** move `hasRole` above the `useEffect` hooks or hoist it to module level as a pure utility function receiving `currentUser` as a parameter.

- **[RESOLVED] Inconsistent API layer usage (multiple files)**: Several components previously bypassed the centralised `api.js` and used raw `fetch` with manual auth headers:
  - `SecretaryDashboard.jsx:71` / `ChangeRequestsTab.jsx` — previously fetched `/api/booking-change-requests` directly
  - `TeamsManager.jsx:35` — previously fetched `/api/users` directly
  - `UserManagement.jsx:54` — previously fetched `/api/users` directly
  - `AuthScreens.jsx:17, 138` — previously fetched `/api/token` and `/api/users/change-password` directly
  - `CatererDashboard.jsx:37, 85, 109` — previously fetched `/api/catering-requests` directly

  **Fix:** Added `login`, `getUsers`, `createUser`, `updateUser`, `deleteUser`, `getCateringRequests`, and `updateCateringRequest` to [api.js](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-frontend/src/services/api.js). All components now route their requests through `api.js`, standardising token injection, refresh/reset events, and error handling. Redundant `API_BASE_URL` imports across components have also been removed.

- **[TO BE CHECKED] `src/App.jsx:170–173`** — **Status determination duplicated on client and server**: `App.jsx` re-implements auto-approval logic (checking if the user is `ADMIN` or `FIXTURE_SECRETARY`) to set `initialStatus`, then also passes `status` in the booking payload. The server's `perform_create` in `bookings/views.py:230–247` correctly re-derives the status independently. The client-side version is redundant and a potential source of drift. **Recommendation:** remove the `initialStatus` logic from `App.jsx`; the server is the single source of truth.

- **[TO BE CHECKED] `bookings/views.py:43–63`** — **Duplicate permission class**: `BaseRolePermission`, `IsManagementOrGroundstaff`, and `IsManagementTeam` are defined inline in `bookings/views.py`, despite `users/permissions.py` already containing a complete, well-structured set of per-role permission classes. This creates two separate permission systems. `IsManagementOrGroundstaff` and `IsManagementTeam` could be expressed using the existing classes in `users/permissions.py`. **Recommendation:** consolidate all permissions in `users/permissions.py`.

- **[TO BE CHECKED] `bookings/views.py:108–127`** — **Business logic in `get_permissions`**: `PitchBookingViewSet.get_permissions` contains user role inspection logic (fetching roles, checking strings) rather than simply returning permission class instances. This logic belongs in a dedicated permission class (e.g. an `IsPrivilegedBookingUser` class). **Recommendation:** extract this into a `users/permissions.py` class.

- **[TO BE CHECKED] `src/components/CalendarView.jsx:357–386`** — **`alert()` calls for UX feedback**: Browser `alert()` is used in 6+ places across `CalendarView.jsx` for error messages and booking details. This is jarring, blocks the UI thread, is not dismissible with custom styling, and breaks the premium feel of the rest of the application. **Recommendation:** replace with an inline toast or a styled modal — a toast system already exists in `VenuesManager.jsx` and `TeamsManager.jsx`; extract it into a shared component.

### Backend

- **[RESOLVED] `users/views.py:29`** — **`permission_classes=[]` on `/me` endpoint**: The `me` action explicitly sets `permission_classes=[]` then manually checks `request.user.is_authenticated`. An empty permission list makes the endpoint unauthenticated from DRF's perspective, meaning any unauthenticated request that reaches it won't be rejected by the framework — it relies on the manual check. **Recommendation:** use `permission_classes=[IsAuthenticated]` and remove the manual authentication check, which is exactly what DRF is designed to handle.

- **[RESOLVED] `users/views.py:68`** — **`ChangePasswordView` comment leaks intent**: `permission_classes = [] # or IsAuthenticated if you handle auth globally/locally` is a TODO-style comment left in production code. **Recommendation:** use `permission_classes=[IsAuthenticated]`, remove the manual check, and delete the comment.

- **[RESOLVED] `bookings/views.py:471`** — **`requests` module not imported**: `sync_play_cricket_fixtures_view` calls `requests.get(...)` but `requests` is never imported at the top of `bookings/views.py`. This is a `NameError` at runtime. **Fix:** add `import requests` to the imports at the top of the file.

---

## Minor Issues (Consider Fixing)

- **[RESOLVED] `src/components/SecretaryDashboard.jsx:19`** and **`TeamsManager.jsx:16`** and **`UserManagement.jsx:15`** — `const API_BASE_URL = import.meta.env.VITE_API_URL;` is re-declared in every component that bypasses `api.js`. This is both redundant and a coupling risk. Centralise in `api.js` (already done there) and stop copying it into components.

- **[RESOLVED] `src/App.jsx:477`** — **Typo in class name**: `text-slate-405` does not exist in Tailwind's default palette (`405` is not a valid shade). This silently produces no colour, likely defaulting to transparent. The intended value was probably `text-slate-400`. **Fix:** change to `text-slate-400`.

- **`bookings/models.py:154`** — **`BookingChangeRequest` reuses `CateringRequest.STATUS_CHOICES`**: The `BookingChangeRequest.status` field references `CateringRequest.STATUS_CHOICES` which uses `"REJECTED"`, whereas `PitchBooking.STATUS_CHOICES` uses `"DENIED"`. This inconsistency means the same conceptual action has different string values depending on the model. **Recommendation:** define a shared `STATUS_CHOICES` at module level or in a base model.

- **`src/services/mockData.js`** — The mock data file is used only by `api.test.js` but lives in `src/services/`. It should either be colocated with the tests in `src/tests/` or placed in a dedicated `__mocks__` folder to avoid being inadvertently included in production builds.

- **`src/components/CalendarView.jsx:234–242`** — **Magic string protocol**: `approvedBooking.notes?.startsWith("AUTO_LOCK:")` parses a colon-delimited string to detect outfield lock semantics. This is a fragile, undocumented protocol. If the notes format ever changes, this silently breaks. **Recommendation:** add a dedicated `booking_type` value (e.g., `"OUTFIELD_LOCK"`) or a boolean flag on the model.

- **`bookings/serializers.py:111`** — `CateringRequestSerializer` and `BookingChangeRequestSerializer` both use `fields = "__all__"`. This exposes all model fields (including internal ones) without explicit declaration, which is an API surface control risk. **Recommendation:** use explicit field lists.

- **`bookings/views.py:384`** — **Pitch selection fallback is unpredictable**: `Pitch.objects.first()` is used as a fallback when no matching pitch is found during CSV import. `first()` returns a random pitch depending on database ordering, which could silently assign an incorrect pitch. **Recommendation:** make this an error case and add it to the `errors` list with a meaningful message.

- **`src/components/VenuesManager.jsx:19–21`** — **Using `sessionStorage` for UI state**: Tab persistence via `sessionStorage` is a minor anti-pattern; this state doesn't need to survive page navigations or tab switches and adds unexpected statefulness. For a view-level tab, lifting the state to the component or using a URL query param is cleaner.

- **`package.json` production `dependencies`**: Several packages listed as production dependencies (`browserslist`, `caniuse-lite`, `electron-to-chromium`, `postcss-value-parser`, `source-map-js`, `baseline-browser-mapping`) are build tools that should only be in `devDependencies`. This bloats the production bundle unnecessarily if any bundler were to include them.

- **`src/components/AuthScreens.jsx`** — **No accessible `for`/`htmlFor` labels**: The `<label>` elements in the login and password reset forms lack `htmlFor` attributes linked to their `<input>` ids. This makes the form non-accessible to screen readers. **Recommendation:** add `id` attributes to inputs and matching `htmlFor` to labels.

- **`bookings/views.py:492`** — **Play-Cricket time field parsing is fragile**: `match.get("$time" if "$time" in match else "match_time", "14:00")` — conditional key selection inside `.get()` is unnecessarily clever. A simple `match.get("$time") or match.get("match_time", "14:00")` is clearer.

---

## Positive Observations

- **Clean API service layer (`api.js`)**: The centralised `apiRequest` function with built-in auth headers, `401`/`403` dispatching via custom DOM events, and clean error enrichment is an excellent pattern. The event-driven logout (`auth-unauthorized`) cleanly decouples the service from the component tree.

- **JWT token management**: The backend JWT configuration (2-hour access, 7-day refresh) with middleware-driven password expiry enforcement (`PasswordExpiryMiddleware`) is a solid security posture.

- **Role-based permission system (`users/permissions.py`)**: The per-role DRF permission classes are clean, single-purpose, and easy to compose. The `IsBookingOwnerOrSecretary` object-level permission correctly enforces team manager scope.

- **Outfield blocking logic**: The `blocks_pitches` many-to-many relationship on `Pitch` and the corresponding `getCellStatus` logic in the frontend is a well-thought-out domain model for cricket's outfield overlap problem.

- **`User.save()` auto-roles**: The `save()` override that automatically promotes superusers to `ADMIN` role is a good guardrail, as is the `EXTERNAL` mutual-exclusivity validation in `clean()`.

- **TDD approach with meaningful tests**: The backend has model, serializer, and view tests. The frontend has MSW-based API service tests with proper setup/teardown (`beforeAll`/`afterAll`/`afterEach`). The `build` script gates on `lint && test` before building, which is excellent practice.

- **Settings split by environment**: The `base/settings/` split (common, dev, dev_local, prod, unit_test) is a mature Django project structure.

- **`Venue.save()` default enforcement**: Automatically clearing the `is_default` flag on all other venues when a new default is set at the model level (rather than the view or serializer layer) is correct and robust.

- **Tailwind design system**: The emerald/slate palette, glass-panel utility class, custom scrollbar, and consistent use of `font-display` (Outfit) and `font-sans` (Inter) create a premium, cohesive dark-mode UI.

- **`perform_create` server-side auto-approval**: Determining booking status server-side in `perform_create` (rather than trusting the client-supplied `status` field) is the correct security pattern. The `read_only_fields = ["status", "rejection_reason", "requested_by"]` in the serializer reinforces this.

---

## Overall Assessment

PitchWiz is an impressively feature-complete application for its stage of development. The domain modelling is sound, the security thinking is solid (JWT, role guards, server-side status enforcement), and the UI is genuinely polished. 

The most urgent fixes are the **Python 2 `except` syntax** in `views.py:380` (startup crash), the **missing `requests` import** in `views.py:471` (runtime crash on Play-Cricket sync), and the **password reset URL typo** in `AuthScreens.jsx:139` (silent feature failure).

The most impactful architectural improvements are **breaking up the three god-components** (`CalendarView.jsx`, `SecretaryDashboard.jsx`, `VenuesManager.jsx`) into focused sub-components, and **routing all API calls through `api.js`** to ensure consistent auth error handling.

Once those are addressed, the codebase will be in excellent shape for a club-scale production deployment.
