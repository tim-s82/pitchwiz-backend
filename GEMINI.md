# Project: PitchWiz - Cricket Club Pitch Booking App (Backend)

*For the original planning conversation with Gemini, see [pitchwiz-plan.md](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/pitchwiz-plan.md).*  
*For architecture audits, resolved issues, and technical debt reviews, see [design_review.md](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/design_review.md).*  
*For development best practices, TDD rules, and coding standards, see [CONTRIBUTING.md](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/CONTRIBUTING.md).*

---

## 1. Project Purpose & Scope

The primary goal of PitchWiz is to streamline cricket pitch booking, fixture scheduling, and grounds management for the club. It centralizes availability across multiple venues and pitches, automatically resolves outfield conflicts, facilitates requests and approvals, handles catering needs, and synchronizes match data from Play-Cricket and CSV spreadsheets.

**Key Stakeholders & Roles:**
*   **Fixture Secretary:** Has master control, approves/denies booking requests, handles schedule conflicts, and manages change requests.
*   **Team Managers:** Requests pitch bookings for assigned teams, submits change requests, and views fixture booking status.
*   **External Organizations (e.g., Dorset Cricket):** Submits pitch requests through a public, unauthenticated booking form.
*   **Club Caterer:** Dedicated dashboard to view and approve/reject catering requirements (teas and drinks) for fixtures.
*   **Groundstaff:** Locks pitches or entire grounds for scheduled maintenance, renovations, or weather-related closures.
*   **User Manager & Admin:** Manages club user accounts, assigns roles, unlocks users, and resets credentials.

---

## 2. Architecture & Tooling

The backend is built with Django and Django REST Framework following a Test-Driven Development (TDD) workflow.

*   **Backend Framework:** Django 6.0
*   **API Framework:** Django REST Framework (DRF) with SimpleJWT for token authentication
*   **Database:** 
    *   **Production:** Managed PostgreSQL hosted on **Supabase**, connected via `DATABASE_URL` (`dj-database-url`).
    *   **Local & Tests:** SQLite for rapid, isolated testing and offline development.
*   **Hosting:** Hosted as a Python Web Service on **Render** using Gunicorn and Whitenoise static file handling.
*   **Email Backend:** Resend API via `django-anymail` with template rendering in `bookings/emails.py`.
*   **Frontend Client:** Consumed by `pitchwiz-frontend`, hosted on **Vercel** (`https://pitchwiz-frontend.vercel.app`).

---

## 3. Implemented Features & Endpoints

### Data Models
*   **`Venue`**: Venues with automated single-default enforcement (`is_default`).
*   **`PitchLength`**: Distinct yard lengths (e.g., 17, 19, 21, 22 yards).
*   **`Pitch`**: Granular types (`GRASS`, `ASTRO`) and entity categories (`MAIN`, `YOUTH`, `OUTFIELD`, `NET`), M2M supported pitch lengths, and `blocks_pitches` self-referential relations for outfield overlap detection.
*   **`Team`**: Club and external teams, linked team managers, and required pitch length.
*   **`Fixture`**: Team, opponent, multi-day start and end dates, and unique Play-Cricket match ID.
*   **`PitchBooking`**: Booking types (`FIXTURE`, `GROUND_MAINTENANCE`), start/end dates, time slots (`MORNING`, `AFTERNOON`, `EVENING`, `ALL_DAY`), tea/drink flags, status (`PENDING`, `APPROVED`, `DENIED`), notes, rejection reason, requester user or external contact details.
*   **`CateringRequest`**: One-to-one relationship with bookings tracking catering status (`PENDING`, `APPROVED`, `REJECTED`) and tea/drink options.
*   **`BookingChangeRequest`**: Requests from managers to alter pitches, dates, or time slots on existing bookings, routed to secretaries for approval.
*   **`User`**: Custom user model with a JSON role list, password expiry timestamp, locked status, and forced reset flags.

### API Endpoints
*   `/api/token` & `/api/token/refresh`: SimpleJWT token issuance and refresh.
*   `/api/users` & `/api/users/change-password`: User management, profile retrieval (`/me`), role management, and password reset.
*   `/api/venues`: CRUD for venues.
*   `/api/pitches`: CRUD for pitches with outfield overlap links.
*   `/api/pitchlengths`: Pitch length configurations.
*   `/api/teams`: Team listing and management with manager associations.
*   `/api/fixtures`: Fixture schedule endpoints.
*   `/api/pitchbookings`: Booking lifecycle management with role-based auto-approval in `perform_create`.
*   `/api/catering-requests`: Caterer review and status updates.
*   `/api/booking-change-requests`: Creation and resolution of booking modification requests.
*   `/api/fixtures/preview-play-cricket` & `/api/fixtures/commit-import`: Play-Cricket fixture fetching and fuzzy team matching (`bookings/matching.py`).
*   `/api/fixtures/preview-spreadsheet`: CSV fixture import preview with header mapping and conflict detection.
*   `/api/health` & `/api/version`: Operational health check and build/git commit metadata service.

---

## 4. Development Best Practices & Conventions

Refer to [CONTRIBUTING.md](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/CONTRIBUTING.md) for full instructions. Key rules for developers and agents:
1. **Server-Side Authorization**: Enforce booking permissions and auto-approval status solely on the server in `perform_create`.
2. **Centralized RBAC**: Define all permissions in [users/permissions.py](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/pitchwiz_backend/users/permissions.py).
3. **TDD Coverage**: Maintain test coverage using `pytest` across models, serializers, views, permissions, and email dispatches.
4. **Code Quality**: Keep code formatted with `black` (100 char limit), `isort`, and `pylint`. Always use Python 3 exception syntax.
