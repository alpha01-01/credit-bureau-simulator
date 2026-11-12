# SimB — Credit Bureau Simulator

A business simulation in which you run a credit bureau in Ghana: receive real (synthetic) credit data from lenders, clean and match it, sell reports, keep the books, and grow the company. You can step into any desk and do the work yourself.

Design documents live in [`docs/`](docs/README.md). Start with [Document 07](docs/07-core-gameplay-design.md) (core gameplay) and [Document 06](docs/06-development-roadmap.md) (roadmap).

> All people, lenders and credit data in SimB are synthetic. Never add real customer data to this repository.

## Stack

| Part | Technology |
| --- | --- |
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework |
| Database | PostgreSQL (developed on 18) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, TanStack Query |
| Quality | ruff, mypy, import-linter, pytest · oxlint, Prettier, Vitest |

## First-time setup (Windows)

Prerequisites: Python 3.12+, Node.js 24+, PostgreSQL 18 (native installer or Docker), Git.

1. **Database.** Create the development role and database (asks for your `postgres` password):

   ```bash
   psql -h localhost -U postgres -f scripts/create_dev_db.sql
   ```

2. **Environment.** Copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY` to a long random value.

3. **Backend.**

   ```bash
   cd backend
   py -3.12 -m venv .venv
   .venv/Scripts/python -m pip install -r requirements/dev.txt
   .venv/Scripts/python manage.py migrate
   ```

4. **Frontend.**

   ```bash
   cd frontend
   npm install
   ```

5. **Git hooks** (runs fast checks before each commit):

   ```bash
   git config core.hooksPath .githooks
   ```

## Running

In two terminals:

```bash
backend/.venv/Scripts/python backend/manage.py runserver
```

```bash
npm --prefix frontend run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to Django on port 8000.

## Checks

Run everything (formatting, lint, module boundaries, types, migrations, tests) before merging:

```bash
backend/.venv/Scripts/python scripts/check.py
```

`--fast` runs only the quick subset used by the pre-commit hook.

## Ground rules

* **The truth boundary.** `apps.world` holds the hidden ground truth. Bureau-side modules must never import it; `import-linter` fails the build if they do.
* **Determinism.** All randomness comes from seeded streams; queries that affect results have an explicit `ORDER BY`; money is `Decimal`.
* **Assumptions.** Anything not yet confirmed from reference material is marked `ASSUMPTION` and listed in [`docs/assumptions.md`](docs/assumptions.md).
* **Definition of done.** See Document 06, Section 11.
