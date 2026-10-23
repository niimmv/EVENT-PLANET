# EVENT PLANET — Django REST API

A production-oriented API-first event planning and management platform built with Django, Django REST Framework, PostgreSQL, token authentication, and Docker Compose.

## Requirements covered

- Token authentication and two roles: `participant` and `organizer`.
- Role-based API access and organizer ownership checks.
- Event lifecycle: `draft → published → closed → finished`; invalid transitions are rejected.
- Public listing/details for published events only.
- Multi-stage events with ordered stages, separate start/end times, and speaker/judge/coach assignments.
- Reusable dynamic attribute definitions with type-safe values stored in dedicated typed columns. **No model `JSONField` is used.**
- Event registrations with capacity checks, duplicate prevention, and a database uniqueness constraint.
- Feedback only for registered participants after an event is finished.
- Results publishing only after an event is finished; public results are exposed only when published.
- PostgreSQL Docker service, migrations, environment-based database credentials, and API tests.

## Architecture decisions

1. **Registration and capacity are event-level.** A participant registers once for the entire event, not individual stages. Capacity is enforced against the event's total registration count. This decision follows the design choice requested by the assignment and keeps multi-stage workshops/webinars simple to register for.
2. **Dynamic attributes use an EAV-style schema.** `AttributeDefinition` is reusable across events. `EventAttributeValue` stores the value for each event and definition. Five nullable typed columns (`text_value`, `integer_value`, `decimal_value`, `boolean_value`, `datetime_value`) plus validation and a database check constraint enforce one populated value column. The API validates that the chosen column matches the definition's declared type.
3. **Results are a single published result per event.** `EventResult` contains a title and text content. This is deliberately format-neutral and avoids a JSON database field.
4. **Event ownership is enforced at queryset and write boundaries.** Organizer endpoints return only the authenticated organizer's events; nested stage, attribute, registration, feedback, and result operations first resolve the event through that owned queryset.

## Run with Docker Compose (PostgreSQL)

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set a long, unique `DJANGO_SECRET_KEY` and a strong `POSTGRES_PASSWORD`.
3. Start the services:

   ```bash
   docker compose up --build
   ```

   Django waits for PostgreSQL health, applies migrations, collects static files, then starts Gunicorn on port `8000`.
4. API base URL: `http://localhost:8000/api/`.
5. Admin: `http://localhost:8000/admin/`.

### Create a superuser

In another terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

Use the admin to create/manage users or register a participant through the API. To give an account organizer permissions, set its role to `organizer` in the admin.

### Stop services

```bash
docker compose down
```

Database data persists in the `postgres_data` volume. To delete it permanently, run `docker compose down -v` (destructive).

## Local development without Docker

Python 3.12 is recommended.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

If `POSTGRES_HOST` is not set, settings use SQLite as a convenience for local development/tests. Docker Compose explicitly configures PostgreSQL and is the intended submission/deployment path.

## Authentication

Register a user and receive a token:

```http
POST /api/auth/register/
Content-Type: application/json

{
  "username": "participant1",
  "email": "participant1@example.com",
  "password": "Use-a-strong-password-123!"
}
```

Login:

```http
POST /api/auth/login/
Content-Type: application/json

{"username":"participant1","password":"Use-a-strong-password-123!"}
```

Send the returned token on protected endpoints:

```http
Authorization: Token <token>
```

For security, public registration always creates a `participant`; the role is read-only in the registration API. Create or promote organizer accounts through Django admin or a trusted provisioning process. This prevents unauthenticated callers from granting themselves organizer privileges.

## API endpoint overview

### Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register/` | Create an account and issue token |
| POST | `/api/auth/login/` | Obtain token |
| GET | `/api/auth/me/` | Current authenticated user |

### Public APIs (no token)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/public/events/` | Paginated list of published events only |
| GET | `/api/public/events/{id}/` | Published event detail, stages and dynamic attributes |
| GET | `/api/public/events/{id}/results/` | Results only if event is finished and results are published |

### Organizer APIs (organizer token required)

| Method | Endpoint | Purpose |
|---|---|---|
| GET, POST | `/api/organizer/events/` | List own events / create draft |
| GET, PUT, PATCH, DELETE | `/api/organizer/events/{id}/` | Manage own event (only drafts may be deleted) |
| POST | `/api/organizer/events/{id}/transition/` | Transition status using `{"status":"published"}` etc. |
| GET, POST | `/api/organizer/events/{id}/stages/` | List/create stages for own event |
| GET, POST | `/api/organizer/events/{id}/attributes/` | List/set typed dynamic attributes |
| GET | `/api/organizer/events/{id}/registrations/` | Participants registered for the event |
| GET | `/api/organizer/events/{id}/feedback/` | Feedback for the event |
| GET, POST | `/api/organizer/events/{id}/results/` | View or publish result (event must be finished) |
| GET, POST | `/api/organizer/stages/` | List/create stages |
| GET, PUT, PATCH, DELETE | `/api/organizer/stages/{id}/` | Manage owned stages |
| GET, POST | `/api/organizer/stage-roles/` | List/assign stage speaker, judge, coach roles |
| GET, POST | `/api/organizer/attributes/` | List/create reusable attribute definitions |
| GET, PUT, PATCH, DELETE | `/api/organizer/attributes/{id}/` | Manage own definitions; used definitions cannot be deleted or have their type changed |

### Participant APIs (participant token required)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/participant/events/{id}/register/` | Register for a published event |
| GET | `/api/participant/registrations/` | List current user's registrations and their status |
| DELETE | `/api/participant/registrations/{id}/` | Cancel own registration before the event starts |
| POST | `/api/participant/events/{id}/feedback/` | Submit feedback after finishing an event |

The API uses DRF page-number pagination (20 records per page) for viewsets.

## Example workflows

1. Create an organizer account in Django admin (or promote an existing account by setting its role to `organizer`), then log in and save the token.
2. `POST /api/organizer/events/` with title, description, `starts_at`, `ends_at` (ISO-8601), and positive capacity. New events start in `draft`.
3. Add stages and reusable attribute definitions, then set event-specific values.
4. `POST /api/organizer/events/{id}/transition/` with `{"status":"published"}`.
5. Register as participant, then `POST /api/participant/events/{id}/register/`. Registration status is returned as `confirmed`; participants can cancel before the event starts with `DELETE /api/participant/registrations/{registration_id}/`.
6. After the event, transition `published → closed → finished`.
7. A registered participant can submit feedback. The organizer can publish results using `/api/organizer/events/{id}/results/` with `{"title":"Final results","content":"..."}`.

Example stage payload:

```json
{
  "title": "Opening session",
  "description": "Welcome and introduction",
  "order": 1,
  "starts_at": "2030-05-10T09:00:00Z",
  "ends_at": "2030-05-10T10:00:00Z"
}
```

Create an attribute definition:

```json
{"key":"difficulty","label":"Difficulty level","data_type":"integer"}
```

Set its value on an event:

```json
{"attribute_definition":1,"value":3}
```

For `boolean`, send JSON `true`/`false`; for `datetime`, send an ISO-8601 string; for `decimal`, send a numeric value; for `text`, send a string.

## Testing

```bash
python manage.py test events
```

The included API tests cover public visibility, organizer ownership, lifecycle transitions, registration capacity/duplicates, typed attributes, feedback eligibility, results visibility, and stage ordering. Run tests in the Docker environment if you want to test against PostgreSQL:

```bash
docker compose run --rm web python manage.py test events
```

## Security and operational notes

- Never deploy with the development secret key or `DEBUG=1`.
- Use HTTPS in production and configure secure cookies / proxy SSL settings at the deployment layer.
- Change the default database password in `.env`; do not commit `.env`.
- Token authentication is intentionally simple for this assignment; revoke a token by deleting it in Django admin or deleting its user.
- Public endpoints expose only published event details and only finished, published results.
- Organizer querysets are scoped to the current organizer; participants can only access their own registrations and submit their own feedback.
