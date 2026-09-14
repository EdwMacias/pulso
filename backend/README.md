# Backend — first working increment

FastAPI backend for authentication, per-user tasks and reminders, basic analytics,
preferences, persistent reminder scheduling, and optional Groq tool-calling chat.
SQLite is the local default; `DATABASE_URL` accepts a PostgreSQL psycopg URL such as
`postgresql+psycopg://user:password@postgres:5432/assistant`.

## Local setup

Python 3.12 is recommended.

```bash
cp .env.example .env
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
```

If the system Python lacks `venv`, `uv venv .venv` is an equivalent setup. The API
is under `/api/v1`, OpenAPI is at `/docs`, and the health endpoint is `/health`.

Run the persistent scheduler separately from the web process:

```bash
.venv/bin/python -m app.scheduler run
# one polling/publishing pass, useful for jobs and tests:
.venv/bin/python -m app.scheduler once
```

The first increment writes notification occurrences to the database and publishes
their JSON payloads to the scheduler process stdout. A unique database constraint
deduplicates each reminder occurrence. Production delivery transports are not yet
implemented, so stdout is not a WhatsApp or push delivery guarantee.

Run tests with `.venv/bin/pytest`.

## Authentication and CSRF

Passwords use Argon2id. Login sessions are opaque random values whose HMAC hashes
are stored in the database. The `session` cookie is HttpOnly and SameSite=Lax;
set `COOKIE_SECURE=true` behind HTTPS. Authenticated `POST` and `PATCH` routes
require `X-CSRF-Token` to equal the readable `csrf_token` cookie. Login and register
also return `csrf_token` in JSON for browser clients.

Email verification and password-reset tokens are single-use and are never returned
by their API endpoints. In development, explicitly enable `DEV_OUTBOX_ENABLED` to
write them to `DEV_OUTBOX_PATH`, or use `DEV_AUTO_VERIFY_EMAIL`. In production,
leave both flags false and configure `SMTP_HOST` and `SMTP_FROM` (plus credentials
when needed). Set `APP_URL` to the public frontend origin; messages link to its
verification and reset pages. Password-recovery responses are generic to avoid
account discovery.

## Container

Build from this directory:

```bash
docker build -t assistant-backend .
docker run --rm -p 8000:8000 --env-file .env assistant-backend
```

Use the same image for the scheduler with command `python -m app.scheduler run`.
The image runs as an unprivileged `app` user. For deployment, use PostgreSQL and
run the API and scheduler against the same database. Row locking plus occurrence
uniqueness coordinate multiple scheduler replicas.

## Current API

- `POST /api/v1/auth/register|login|logout|verify-email|forgot-password|reset-password`
- `GET /api/v1/auth/me`
- `GET|PATCH /api/v1/me/preferences`
- `GET|POST /api/v1/tasks`, `PATCH /api/v1/tasks/{id}`
- `GET|POST /api/v1/reminders`, `PATCH /api/v1/reminders/{id}`
- `GET /api/v1/analytics/summary`
- `GET|POST /api/v1/chat/messages`
- `GET /api/v1/integrations/status`
- `GET /api/v1/notifications`

Groq chat is enabled only when `GROQ_API_KEY` is configured. The coordinator may
call narrowly scoped tools for the authenticated user's tasks, reminders, time
context, and analytics, with a configurable call limit. If Groq is missing or
unavailable, the chat write returns an explicit 503 and stores no message.

## Deliberate limitations

This is a runnable foundation, not the complete MVP. It does not yet include
Alembic migrations, login rate limiting, Redis/Celery, WhatsApp/Evolution webhooks,
voice/STT/TTS, actual outbound notification delivery, quiet hours, notification
history endpoints, bulk-confirmation flows, or account export/deletion. The
integrations status route reports WhatsApp and TTS as `available: false` even when
configuration placeholders are present. `create_all` is used for this first
increment; add migrations before evolving a production database schema.
