# Unified Project Structure

This document defines the unified repository structure and conventions for the Cheque Processing Platform. It complements `docs/architecture/source-tree.md` and is the single source of truth for where new code should live.

## Repository Layout

```text
/ (repo root)
├─ backend/
│  ├─ app/
│  │  ├─ api/            # FastAPI routers (grouped by domain)
│  │  ├─ services/       # Business logic (pure functions where possible)
│  │  ├─ workers/        # Celery tasks
│  │  ├─ models/         # ORM models (SQLAlchemy)
│  │  ├─ schemas/        # Pydantic schemas
│  │  ├─ validations/    # Rules and gates (deterministic)
│  │  ├─ parsers/        # Regex / finite-state grammars
│  │  ├─ ocr/            # OCR adapters, MICR, layout detection
│  │  ├─ utils/          # Shared helpers
│  │  └─ main.py         # FastAPI entrypoint
│  ├─ migrations/        # Alembic
│  ├─ tests/             # Pytest suites
│  └─ pyproject.toml     # Tooling config
├─ frontend/
│  ├─ src/
│  │  ├─ components/
│  │  ├─ pages/
│  │  ├─ features/
│  │  ├─ hooks/
│  │  ├─ state/
│  │  ├─ utils/
│  │  └─ main.tsx
│  ├─ public/
│  └─ package.json
├─ ops/
│  ├─ docker/
│  ├─ k8s/
│  ├─ ci/
│  └─ scripts/
├─ docs/
│  ├─ prd/
│  └─ architecture/
├─ data/                 # Sample cheques (redacted)
├─ models/               # Model artifacts (versioned)
└─ README.md
```

[Source: architecture/source-tree.md]

## Naming Conventions
- Python modules: snake_case; Classes: PascalCase; constants: UPPER_SNAKE.
- API routers: `backend/app/api/{domain}.py` with tags and explicit responses.
- Celery tasks: `backend/app/workers/{domain}_tasks.py`.
- Tests mirror modules: `backend/tests/{module}_test.py`.
- Frontend components: PascalCase in `frontend/src/components/`.

## File Placement Rules
- Parsing logic → `backend/app/parsers/`
- Validation rules → `backend/app/validations/`
- OCR + CV routines → `backend/app/ocr/`
- Database models → `backend/app/models/`, with Alembic migrations in `backend/migrations/`
- API contracts (schemas) → `backend/app/schemas/`

## Story-to-Code Mapping
When a story specifies new backend functionality:
- Create or update router under `api/`.
- Add service functions under `services/`.
- Add validations/parsers as needed in their dedicated folders.
- Add/modify schemas in `schemas/` and create migrations if models change.

For frontend stories:
- Create components in `components/` and pages in `pages/`.
- Keep state local where possible; introduce global state only when clearly needed.

## References
- [Source: architecture/tech-stack.md]
- [Source: architecture/coding-standards.md]
