# Repository Guidelines

## Project Structure & Module Organization

Pulso has a FastAPI backend and Vue 3 frontend. Backend code lives in `backend/app/`; keep routes, schemas, models, and integrations in focused modules. Backend tests are in `backend/tests/`. Frontend source is under `frontend/src/`, with views in `views/`, state in `stores/`, and API access in `services/`. Playwright tests live in `frontend/e2e/`; Vitest tests are in `frontend/tests/`. Docker definitions are in `infra/`, and deployment notes are in `docs/`.

## Build, Test, and Development Commands

- `docker compose -f infra/compose.yaml up -d --build`: start PostgreSQL, API, scheduler, and web UI.
- `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`: create the backend environment.
- `cd backend && .venv/bin/uvicorn app.main:app --reload`: run the API locally on port 8000.
- `cd backend && .venv/bin/pytest`: run the backend test suite.
- `cd frontend && npm ci && npm run dev`: install dependencies and start Vite.
- `cd frontend && npm run test:unit`: run Vitest tests.
- `cd frontend && npm run build`: type-check and create the production bundle.
- `cd frontend && npm run test:e2e`: run Playwright tests; the development API must be available.

## Coding Style & Naming Conventions

Use four spaces in Python and two in TypeScript, Vue, CSS, and JSON. Follow `snake_case` for Python functions and modules, `PascalCase` for classes and Vue components, and `camelCase` for TypeScript identifiers. Keep TypeScript strict and type service boundaries. Prefer small domain modules and existing Pydantic and Pinia patterns. No formatter or linter is configured, so match nearby code.

## Testing Guidelines

Use pytest for backend tests, Vitest for frontend unit/API tests, and Playwright for workflows. Name Python tests `test_<behavior>.py`, frontend tests `*.test.ts`, and E2E specs `*.spec.ts`. Add regression coverage for bug fixes. E2E runs create accounts and tasks, so use disposable databases.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout. Use short, imperative subjects, optionally scoped, such as `backend: validate reminder timezone`. Keep commits focused. Pull requests should explain the change, list verification commands, link issues, and include screenshots for UI changes.

## Security & Configuration

Never commit `.env` files, API keys, SMTP credentials, or production secrets. Keep `GROQ_API_KEY` server-side. Review cookie, auto-verification, outbox, database, and public URL settings before deployment; local defaults are intentionally unsuitable for production.
