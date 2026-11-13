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

## Generating a world

The simulated economy (people, businesses, lenders, loans and 36 months of repayment history) is generated from a seed:

```bash
backend/.venv/Scripts/python backend/manage.py generate_world --seed 42 --scale default
```

`--scale small` or `tiny` makes a quick world for experiments; `--dry-run` prints calibration statistics without saving. The same seed always produces the same world.

## Generating provider files

Each month the reporting providers send their books to the bureau, with the errors real lenders make. To produce those files for a stored world:

```bash
backend/.venv/Scripts/python backend/manage.py generate_provider_files --world 1
```

By default this writes the five reporting providers' files for the world's last month to `storage/provider_files/`. `--period 2026-11` and `--lender HZF` pick months and lenders (both repeatable), `--all-periods` does the whole history, `--profile CLEAN` switches off every defect, and `--replace` regenerates. Every injected defect, with the correct value, is recorded in the defect ledger (`world_filedefect`), which only the game uses to score decisions; the bureau sees only the files.

## Running a month through the bureau

The bureau receives each provider's files and processes them: template and file checks, staging, cleansing, duplicate detection, validation, customer and account matching, and loading:

```bash
backend/.venv/Scripts/python backend/manage.py process_month --world 1 --period 2026-11
```

The first run creates a game (a bureau organisation) for the world and onboards the five reporting providers. Provider files are generated if needed. Each provider's line shows records received, accepted, unloadable and duplicate, and the issues found.

## Playing time forward

A game is a bureau running in a world. The clock advances in 15-minute ticks over Ghana working days (08:00–17:00; nights, weekends and public holidays are skipped). Provider files arrive on their scheduled days and are processed in the overnight batch. At the start of each month the world lives through the month that has just ended, so providers always have a new month to report.

```bash
backend/.venv/Scripts/python backend/manage.py run_clock
```

`run_clock` advances running games in real time (at 1x a game hour takes 20 seconds). The API at `/api/v1/games/<id>/clock/` reports the clock and accepts `pause/`, `resume/`, `speed/` and `advance/` (by hour, day or to the next event). `delete_game --game N` removes a game and its bureau; `delete_game --world N` removes a world with all its games.

## The work queue

Records the pipeline cannot settle on its own become work items: uncertain customer matches (an identifier matches but the name or date of birth does not) and unloadable records with a plausible correction. The Data Operations team works through them while the clock runs; you can decide items yourself through `/api/v1/games/<id>/work-items/`. Every decision is applied to the bureau as given, right or wrong.

## Enquiries

Each month the world's borrowers apply for credit. When the lender subscribes to the bureau it decides, application by application, whether to check the bureau first, depending on price and on how useful the bureau has been to it so far. Each enquiry is logged with its purpose and consent reference, billed as usage, and answered with a credit report when the subject is found. `/api/v1/games/<id>/enquiries/` lists them.

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
