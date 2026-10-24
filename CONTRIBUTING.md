# Contributing to PitchWiz Backend

This guide defines the engineering standards, architecture patterns, and contribution practices for the `pitchwiz-backend` application. All contributors and AI coding agents must adhere to these conventions to maintain code quality, security, and architectural consistency.

For historical review insights and architectural discussion, refer to [design_review.md](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/design_review.md).

---

## 1. Core Architectural Principles

1. **Server-Side Single Source of Truth**:
   - Business logic, authorization, and booking status transitions must be enforced strictly on the server.
   - Never trust client-supplied status fields (e.g., in `PitchBookingViewSet.perform_create`, booking status is derived based on the requesting user's roles).

2. **Test-Driven Development (TDD)**:
   - Every bug fix, endpoint addition, or model modification must be accompanied by unit and integration tests.
   - Write tests first or alongside implementation. Ensure tests run against the `base.settings.unit_test` configuration using SQLite for speed and isolation.

3. **Separation of Concerns & Modularity**:
   - Keep views focused on request validation, response serialization, and dispatching to services.
   - Domain logic like matching algorithms (`bookings/matching.py`) and transactional emails (`bookings/emails.py`) must live in dedicated service modules.
   - Database integrity logic (such as auto-clearing default venue flags or role mutual-exclusivity) belongs in model `clean()` or `save()` methods.

---

## 2. Authentication & Permission Architecture

1. **Role-Based Access Control (RBAC)**:
   - All role-checking permissions must be defined in [users/permissions.py](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/pitchwiz_backend/users/permissions.py).
   - Avoid defining duplicate or inline permission classes in view files.
   - Valid user roles are defined in `User.Role`:
     - `ADMIN`: Full system administrative privileges.
     - `FIXTURE_SECRETARY`: Approves/denies booking requests, resolves fixture conflicts, manages fixtures.
     - `TEAM_MANAGER`: Requests bookings on behalf of assigned teams, views team bookings.
     - `CATERER`: Views and manages catering (teas and drinks) requests.
     - `GROUNDSTAFF`: Manages pitch maintenance, ground locks, and pitch availability.
     - `USER_MANAGER`: Manages club accounts, user roles, and account resets.
     - `EXTERNAL`: External requesting organizations (mutually exclusive with internal roles).

2. **Explicit Permissions on Endpoints**:
   - Never leave endpoints with empty `permission_classes = []` unless an endpoint is intentionally unauthenticated and public (e.g. public health check or public booking creation).
   - Any endpoint requiring an authenticated user must include `IsAuthenticated` at minimum.
   - Object-level permissions (e.g., `IsBookingOwnerOrSecretary`) must implement `has_object_permission(self, request, view, obj)`.

3. **JWT Handling & Security**:
   - Authentication uses `rest_framework_simplejwt`.
   - Standard access tokens are valid for 2 hours; refresh tokens are valid for 7 days.
   - Enforce password expiration via `PasswordExpiryMiddleware`.

---

## 3. Serializers & API Design

1. **Explicit Field Lists**:
   - Always declare explicit `fields = [...]` in `ModelSerializer` classes.
   - Avoid `fields = "__all__"` on write-capable serializers to prevent unintended exposure of internal or sensitive fields.

2. **Explicit Read-Only Fields**:
   - Fields that are populated server-side (e.g., `status`, `rejection_reason`, `requested_by`) must be included in `read_only_fields` to prevent client tampering.

3. **Validation**:
   - Validate field formats and cross-field constraints in serializer `validate()` or `validate_<fieldname>()` methods.
   - Return descriptive DRF `serializers.ValidationError` messages with clear keys.

---

## 4. Email Notification Standards

All transactional emails are sent through [bookings/emails.py](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/pitchwiz_backend/bookings/emails.py) using `django-anymail` with Resend in production.

1. **Templates**:
   - Email templates reside in `bookings/templates/bookings/email/`.
   - Keep templates clean, concise, and focused on cricket fixture details (date, venue, pitch, time slot, catering, notes).

2. **Safety Switches**:
   - Always respect `settings.EMAIL_ENABLED` before sending.
   - If `settings.EMAIL_OVERRIDE_ADDRESS` is specified (e.g. in staging/QA), redirect all recipient lists to that address.
   - Catch and log email exceptions without crashing the parent transaction unless email delivery is strictly mandatory for the workflow.

---

## 5. Coding Standards & Python Conventions

1. **Python 3 Syntax**:
   - Python 3 exception syntax must always be used: `except (ValueError, IndexError) as exc:`.
   - Never use obsolete Python 2 syntax (e.g. `except ValueError, IndexError:`).

2. **Formatting & Linting**:
   - Line length limit: **100 characters**.
   - Code formatting: `black` with `--line-length 100`.
   - Import sorting: `isort` with Black profile.
   - Linting: `pylint` with `pylint-django` configured via [pitchwiz_backend/.pylintrc](file:///c:/Users/timsh/OneDrive/Documents/github/pitchwiz-backend/pitchwiz_backend/.pylintrc).
   - Keep imports organized: standard library, third-party packages, internal Django modules.

3. **Error Handling**:
   - Log exceptions with proper context using `logger.exception(...)` or `logger.error(...)`.
   - Avoid bare `except: pass` blocks. Catch specific exceptions.

---

## 6. Database & Migration Rules

1. **Dual Database Support**:
   - Local and test environments use SQLite; production uses Supabase PostgreSQL (`dj-database-url`).
   - Avoid writing queries that rely on PostgreSQL-only features without providing SQLite fallback compatibility (e.g., JSONField contains filtering in Python when querying SQLite).

2. **Migrations**:
   - Run `python manage.py makemigrations` and inspect generated migrations before committing.
   - Ensure default values are provided for newly added non-nullable fields.
   - Never edit existing, applied migrations that have been deployed to production.

---

## 7. Development & Testing Workflow

1. **Running Tests**:
   ```bash
   cd pitchwiz_backend
   pytest
   ```
   To run with coverage:
   ```bash
   pytest --cov=bookings --cov=users
   ```

2. **Code Checks Before Submitting**:
   ```bash
   black --check .
   isort --check-only .
   pylint --rcfile=.pylintrc bookings users base
   ```
