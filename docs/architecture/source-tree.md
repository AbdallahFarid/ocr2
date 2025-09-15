# Source Tree

Proposed repository structure to keep responsibilities clear and enable scale.

```text
/ (repo root)
├─ backend/
│  ├─ app/
│  │  ├─ api/            # FastAPI routers
│  │  ├─ services/       # Business logic
│  │  ├─ workers/        # Celery tasks
│  │  ├─ models/         # ORM models
│  │  ├─ schemas/        # Pydantic schemas
│  │  ├─ validations/    # Rules and gates
│  │  ├─ parsers/        # Regex/grammars for fields
│  │  ├─ ocr/            # OCR wrappers, MICR, detection
│  │  ├─ utils/          # Reusable utilities
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
│  ├─ prd/               # Sharded PRD (index.md, 1-*.md, ...)
│  ├─ architecture/      # Sharded Architecture (index.md, components.md, ...)
│  └─ qa/
├─ data/                 # Sample cheques, redacted
├─ models/               # Model artifacts (versioned)
└─ README.md
```

Notes
- The `docs/prd/` and `docs/architecture/` folders are generated via `md-tree explode` from the monoliths.
- Keep CI checks for formatting, linting, types, and tests across backend and frontend.
- Place sensitive datasets under secure storage, not in VCS.
