# PitchWiz Backend

The backend REST API service for **PitchWiz**, a cricket club pitch booking, fixture scheduling, and grounds management platform.

Built with Python and Django REST Framework, the backend provides robust scheduling logic, outfield conflict detection, external booking workflows, Play-Cricket & spreadsheet fixture synchronization, catering request management, role-based access control (RBAC), and automated transactional email notifications.

---

## 1. Architecture & Hosting

- **API Framework**: Django 6.0 & Django REST Framework (DRF)
- **Production Hosting**: Hosted as a Web Service on [Render](https://render.com) using Gunicorn and Whitenoise.
- **Production Database**: Managed PostgreSQL on [Supabase](https://supabase.com) connected via `DATABASE_URL` and `dj-database-url`.
- **Local / Test Database**: SQLite for fast local development and hermetic unit testing.
- **Authentication**: JWT authentication with `djangorestframework-simplejwt` and custom password expiration middleware.
- **Transactional Emails**: Resend API integrated via `django-anymail`.
- **CORS**: Configured to accept requests from the frontend client hosted on Vercel (`https://pitchwiz-frontend.vercel.app`) and local development ports.

---

## 2. Key Implemented Features

- **Venue & Pitch Management**:
  - Multi-venue configuration with single default venue enforcement.
  - Granular pitch types (Grass, Artificial/Astro) and entity types (Main Pitch, Youth Pitch, Outfield Area, Batting Net).
  - Outfield overlap detection: Models `blocks_pitches` relations so booking a main pitch automatically locks overlapping youth pitches or outfield strips.
  - Multi-length pitch configuration (e.g., 17, 19, 21, 22 yards) matched against team requirements.

- **Booking & Fixture Workflows**:
  - Multi-day fixture bookings and time-slot scheduling (Morning, Afternoon, Evening, All Day).
  - Privileged instant approvals for Fixture Secretaries and Administrators; approval queues for Team Managers.
  - Public booking request endpoint for external cricket bodies (e.g., Dorset Cricket) with contact validation.
  - Booking Change Requests workflow with secretary review, approval, or rejection.
  - Ground Maintenance mode to lock specific pitches or entire grounds with reason tracking.

- **Integrations & Batch Import**:
  - **Play-Cricket API Sync**: Pulls matches by site ID and date range, performs fuzzy team/opponent matching (`bookings/matching.py`), and previews updates before committing.
  - **Spreadsheet / CSV Import**: Upload CSV fixture sheets, parse headers, map teams and opponents, validate conflicts, and commit in batch transactions.

- **Catering Management**:
  - Automatic `CateringRequest` tracking for bookings requesting teas or drinks.
  - Caterer review dashboard endpoints to confirm or reject catering requirements.

- **User & Security Management**:
  - Custom `User` model with JSON role lists (`ADMIN`, `FIXTURE_SECRETARY`, `TEAM_MANAGER`, `CATERER`, `GROUNDSTAFF`, `USER_MANAGER`, `EXTERNAL`).
  - Strict mutual exclusivity validation for `EXTERNAL` users.
  - Password complexity validation, password expiration middleware, and forced password reset flags.

- **Transactional Email Notifications**:
  - Templated notifications for new booking requests, external submissions, approval confirmations, rejections, change requests, and catering updates.
  - Master kill-switch (`EMAIL_ENABLED`) and staging redirect override (`EMAIL_OVERRIDE_ADDRESS`).

- **Observability & Diagnostics**:
  - `/api/health`: Database connection and operational health check.
  - `/api/version`: Service version, git commit hash, and build timestamp.

---

## 3. Project Structure

```
pitchwiz-backend/
├── Pipfile / Pipfile.lock       # Python dependencies
├── pyproject.toml               # Black, isort, pylint configuration
├── design_review.md             # Architecture review & code health audit
├── CONTRIBUTING.md              # Engineering best practices and TDD rules
├── pitchwiz_backend/
│   ├── manage.py
│   ├── base/
│   │   ├── settings/            # common.py, dev.py, dev_local.py, prod.py, unit_test.py
│   │   ├── urls.py              # Root URL router
│   │   ├── version.py           # Git & version inspection service
│   │   └── wsgi.py / asgi.py
│   ├── users/
│   │   ├── models.py            # Custom User model and roles
│   │   ├── permissions.py       # DRF RBAC permission classes
│   │   ├── middleware.py        # Password expiry middleware
│   │   ├── validators.py        # Password complexity validation
│   │   ├── views.py / urls.py   # User management & password reset endpoints
│   │   └── tests.py
│   └── bookings/
│       ├── models.py            # Venue, Pitch, Team, Fixture, Booking, Catering, ChangeRequest
│       ├── serializers.py       # DRF serializers
│       ├── views.py             # CRUD viewsets, Play-Cricket sync, CSV import
│       ├── matching.py          # Fuzzy matching algorithm for fixtures
│       ├── emails.py            # Transactional email service
│       ├── templates/           # Plain text email notification templates
│       └── tests/               # Test suites (models, serializers, views, emails, matching)
```

---

## 4. Local Development Setup

### Prerequisites
- Python 3.14 (or Python 3.11+)
- Pipenv (or standard `pip` with `venv`)

### Installation Steps

1. **Clone the repository and enter directory**:
   ```bash
   cd pitchwiz-backend
   ```

2. **Install dependencies**:
   Using Pipenv:
   ```bash
   pipenv install --dev
   pipenv shell
   ```
   Or using standard venv:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   # source .venv/bin/activate  # macOS / Linux
   pip install -r <(pipenv requirements)
   ```

3. **Configure Environment Variables**:
   Create a `.env` file inside `pitchwiz_backend/` (or set environment variables):
   ```ini
   DJANGO_SETTINGS_MODULE=base.settings.dev_local
   DJANGO_SECRET_KEY=local-dev-insecure-key-12345
   DEBUG=True
   EMAIL_ENABLED=False
   ```

4. **Apply database migrations**:
   ```bash
   cd pitchwiz_backend
   python manage.py migrate
   ```

5. **Create a superuser (Admin)**:
   ```bash
   python manage.py createsuperuser
   ```

6. **Start the development server**:
   ```bash
   python manage.py runserver 8000
   ```
   The API will be available at `http://127.0.0.1:8000/api/`.

---

## 5. Running Tests & Quality Checks

Run the automated test suite:
```bash
cd pitchwiz_backend
pytest
```

Run test coverage report:
```bash
pytest --cov=bookings --cov=users --cov-report=term-missing
```

Run formatters and linters:
```bash
black --check .
isort --check-only .
pylint --rcfile=.pylintrc bookings users base
```

---

## 6. Contributing & Guidelines

Please read [CONTRIBUTING.md](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/CONTRIBUTING.md) for detailed guidelines on Test-Driven Development (TDD), permissions, API design contracts, and coding standards.
