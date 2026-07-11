# Project: PitchWiz - Cricket Club Pitch Booking App

*For the original planning conversation with Gemini, see [pitchwiz-plan.md](file:///c:/Users/timsh/github/pitchwiz-backend/pitchwiz-plan.md).*

## 1. Project Purpose

The primary goal of PitchWiz is to streamline the management of cricket pitch bookings for home matches at the club. It aims to centralize the booking process, providing a clear overview of pitch availability and facilitating requests and approvals.

**Key Stakeholders & Roles:**
*   **Fixture Secretary:** Has overall control, approves/denies all pitch booking requests.
*   **Team Managers:** Can request pitch bookings for their team's fixtures and view the status of all bookings (pending and confirmed).
*   **External Organizations (e.g., Dorset Cricket):** Can request pitches via a public form.
*   **Club Caterer:** Needs a dedicated dashboard to view catering requirements for booked fixtures.

**Core Functionality:**
*   **Pitch Booking Management:** Allow team managers to request pitches for fixtures, with approval/denial by the Fixture Secretary.
*   **Interactive Calendar View:** A responsive calendar showing pitch availability across multiple venues and pitches, suitable for both mobile and desktop.
*   **Fixture Import:** Ability to import fixtures from Play-Cricket (via API) and from spreadsheets (CSV).
*   **Pitch Specifics:** Handle various pitch lengths (e.g., 17, 19, 22 yards) and filter availability based on team requirements.
*   **Outfield Overlap Logic:** Automatically mark youth pitches as unavailable if a main adult pitch (on whose outfield they reside) is booked.
*   **Multi-Day Fixtures:** Support bookings spanning multiple days.
*   **Catering Requirements:** Track requests for "drinks" and "teas" for fixtures.
*   **External Booking Form:** A public-facing form for non-club entities to request pitches.

## 2. Architectural & Tooling Decisions

The project follows a Test-Driven Development (TDD) approach. It is structured as two separate applications: a Django backend providing an API, and a separate frontend consuming that API.

*   **Backend Framework:** Django (Python)
*   **API Framework:** Django REST Framework (DRF)
*   **Database:** PostgreSQL (SQLite for local development/MVP)
*   **Frontend Technologies (Planned):** HTML, Tailwind CSS (for styling and responsiveness). A JavaScript framework (React, Vue, or HTMX) is anticipated for interactive components like the calendar.
*   **Hosting (Planned):** Render or Railway for the Django backend.

## 3. Current Progress

The Django backend project (`pitchwiz-backend`) has been initialized.

*   **Django App:** `bookings`
*   **Models Implemented (with TDD):**
    *   `Venue`
    *   `PitchLength`
    *   `Pitch` (including `supported_lengths` and `blocks_pitches` for outfield logic)
    *   `Team` (including `required_length` and `is_external` flags)
    *   `Fixture` (now supporting `start_date` and `end_date` for multi-day)
    *   `PitchBooking` (including `start_date`, `end_date`, `time_slot`, `requires_teas`, `requires_drinks`, and fields for external contact info)
*   **API Endpoints Implemented (with TDD, using DRF `ReadOnlyModelViewSet`):**
    *   `/api/venues/` (list and retrieve)
    *   `/api/pitches/` (list and retrieve)

## 4. Next Steps & Future Considerations

*   Continue TDD for remaining API endpoints (Team, Fixture, PitchBooking).
*   Set up the separate frontend project.
*   Implement the interactive calendar rendering logic.
*   Develop the Play-Cricket API integration and CSV import functionality.
*   Build the Fixture Secretary Dashboard and Caterer Dashboard.
*   Implement user authentication and permissions (using Django's built-in system).
*   Refine coding style, linting, and formatting rules.
