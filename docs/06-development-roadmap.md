# CREDIT BUREAU SIMULATOR (SimB)

## DOCUMENT 06 — DEVELOPMENT ROADMAP, IMPLEMENTATION STRATEGY AND TESTING PLAN

**Document ID:** CBS-DRTP-001
**Version:** 0.2
**Status:** Approved
**Date:** 12 November 2026
**Supersedes:** Version 0.1 (see Git history)
**Depends on:** Documents 01, 03, 04, 05 and **07 (takes precedence)**
**Team:** Project owner and Claude

---

# 1. Purpose

This document turns the approved design into an ordered build plan. It defines:

* The phases, and the increments inside each phase.
* What "done" means for each increment.
* Which reference material each increment depends on.
* The technology stack as amended by Document 07.
* Repository layout, Git practice and the testing strategy.
* Risks, and the immediate next tasks.

Version 0.1 built the bureau module by module (organisation → providers → core DB → processing → … → simulation → UI → 3D). The game did not exist until Phase 8. Version 0.2 replaces that with a **walking skeleton**: a thin version of the whole loop, playable from the first weeks, which is then deepened.

---

# 2. Principles

**2.1 Playable early, deep later.**
Every increment leaves the game in a state that can be run and looked at. Depth is added to a working loop, never to an isolated module.

**2.2 Thin slices through every layer.**
An increment touches world, pipeline, simulation, finance and UI as needed to make one behaviour real end to end.

**2.3 Quality is not deferred.**
Each increment ships with its tests, its "Why?" drill-down and its audit trail. "Code exists" is not "done" (Section 11).

**2.4 Real rules, flagged assumptions.**
Real-world practice is mirrored exactly (Document 07, D11). Until reference material arrives, placeholders are written as configuration, marked `ASSUMPTION`, and listed in an assumptions register so they can be replaced without code changes.

**2.5 Determinism is a feature.**
Same seed plus same actions gives the same game. This is protected by tests from the first increment.

**2.6 The truth boundary is sacred.**
Bureau modules never read the world layer (Document 07, Section 7.1). This is enforced by automated checks from the first increment that creates both.

---

# 3. Technology Stack (as amended)

| Layer | Choice | Notes |
| --- | --- | --- |
| Language (backend) | Python 3.12+ | |
| Web framework | Django (current LTS) + Django REST Framework | |
| Database | **PostgreSQL** (current stable) via psycopg 3 | D1. Row-level security reserved for the Analytics SQL console |
| Data processing | pandas, NumPy | |
| Machine learning | scikit-learn | Phase 3 |
| Background work | Database-backed job table + worker management command | D2. Celery/Redis only if a measured workload needs them |
| Simulation | Dedicated simulation worker process; deterministic tick engine | Document 07, Section 5.3 |
| Frontend | React 19 + TypeScript, built with Vite | |
| Styling | Tailwind CSS | |
| Server state | TanStack Query (or equivalent) | Server is authoritative |
| Charts | A single charting library chosen in Phase 0 | |
| 3D (Phase 4) | Three.js via React Three Fiber, Drei | |
| Testing | pytest, pytest-django, Hypothesis (property tests), Vitest, Playwright (added with S8) | |
| Quality | ruff (lint + format), mypy (strict), oxlint, Prettier, import-linter | import-linter enforces module boundaries; oxlint replaced ESLint (Vite default, faster) |
| Local environment | PostgreSQL in Docker Desktop (WSL2) or native Windows installer; Django and Vite run natively | Either PostgreSQL option is supported |
| Version control | Git; GitHub remote when the owner chooses | |

Exact versions are pinned during Phase 0 and recorded in the repository.

---

# 4. Phase Overview

| Phase | Name | Outcome | Estimate |
| --- | --- | --- | --- |
| 0 | Foundations | Repository, tooling, empty app running end to end, CI-style checks locally | 1–2 weeks |
| 1 | Walking skeleton | One full game month playable end to end through a basic UI | 6–8 weeks |
| 2 | First playable slice | Document 07, Section 13: polished, balanced, missions M1–M6 | about 8–10 weeks |
| 3 | Version 1 breadth | Analytics, scenarios, difficulty, economy, more playable roles, M7–M8 | 4–6 months |
| 4 | The office | 3D isometric office tied to live simulation state | 2–3 months |
| 5 | Release preparation | Hardening, external playtesting, packaging | 1 month |

**Total to Version 1: about 11–15 months.** The first playable slice lands at about month 4–5.

Estimates assume steady weekly progress and timely reference material. The real constraint is review and play-testing time, not code volume. Estimates are revisited at the end of each phase.

---

# 5. Phase 0 — Foundations (1–2 weeks)

**Objective:** a clean, reproducible project in which every later increment can be built and tested.

| # | Task |
| --- | --- |
| 0.1 | Repository layout (Section 10); README with setup steps for Windows |
| 0.2 | PostgreSQL running locally; `.env.example`; settings split (base / dev / test) |
| 0.3 | Django project with DRF; custom user model **before** the first migration |
| 0.4 | Module skeletons: `world`, `simulation`, `bureau` sub-apps, `finance`, `org`, `audit`, `workitems` (Section 10) |
| 0.5 | import-linter contract: no bureau module may import `world` |
| 0.6 | React + TypeScript + Vite + Tailwind shell; API client; health-check page |
| 0.7 | Test runners (pytest, Vitest), linters, formatters; a single `check` script that runs them all |
| 0.8 | Pre-commit hook running the fast checks |
| 0.9 | Assumptions register (`docs/assumptions.md`) |
| 0.10 | Choose and pin all versions |

**Exit criteria**

* A fresh clone runs on Windows by following the README.
* `check` passes: lint, type check, boundary contract, backend and frontend tests.
* The frontend displays data fetched from the backend, read from PostgreSQL.

---

# 6. Phase 1 — Walking Skeleton (6–8 weeks)

**Objective:** one complete game month, end to end, through a basic UI. Everything is thin; nothing is fake.

Each increment is demoable on its own.

## S1 — World generator v0

* Seeded generation of individuals, businesses, lenders and loans (Document 07, Section 7).
* Monthly loan evolution using the missed-payment hazard model; arrears, days past due, write-off.
* Generation of 36 months of history for the Established scenario.
* Command-line tool: `generate_world --seed N --scale default`.

**Done when:** two runs with the same seed produce identical worlds; default rates over time sit in a plausible configured band; generation at default scale completes in a reasonable time on a laptop (target set in Phase 0).

## S2 — Provider files

* Data Quality Profile per provider (Document 07, Section 7.3), as configuration.
* File writer: each provider's true book → noisy CSV/XLSX in the provider's template.
* A defect ledger in the world layer recording every injected defect and the correct value.

**Depends on:** R1, R2 (templates, code lists). Until available, a placeholder template marked `ASSUMPTION`.

**Done when:** every defect in a file is recorded in the defect ledger, and a clean profile produces a file that matches the truth exactly.

## S3 — Pipeline v0

* Submission register, raw file storage with checksum, staging.
* Template validation, mandatory-field validation, one cleansing rule (phone normalisation), exact duplicate detection.
* Exact-identifier customer referencing (using `provider_customer_link`) and account referencing (unique institution + account number).
* Accepted records loaded to `core.*`; unloadables recorded with reasons; processing run summary.

**Depends on:** R1–R3 for real rules; placeholders until then.

**Done when:** month 1 loads; month 2 for the same provider creates new observations on existing accounts, not new accounts; every loaded observation traces to its source file and row; processing totals reconcile (received = accepted + unloadable + duplicate).

## S4 — Clock and tick engine

* Game record; 15-minute ticks; working-day calendar; skip nights, weekends and holidays.
* Seeded RNG streams per `(world_seed, tick, stream)`.
* Idempotent ticks; scheduled events (provider file arrival on its submission day, late arrival per profile).
* API: state, pause/resume, speed, advance one hour / one day / to next event.

**Done when:** a replay test runs a month twice from the same seed and action log and produces identical database state (compared by checksums of ordered table contents).

## S5 — Work items and employees v0

* Generic work-item framework: type, evidence, allowed decisions, correct answer (from the world, never shown to the bureau), assignee, outcome.
* Two work-item types: **uncertain match review** and **unloadable record triage**.
* Employees with skill per work-item type, morale, workload; AI resolution model (Document 07, Section 8.3).
* Player can resolve the same items.
* Decisions are applied to the bureau database; every AI decision stores its explanation.

**Done when:** a highly skilled employee is measurably more accurate than a junior one over a large sample; wrong decisions really produce false merges or wrongly rejected records in the bureau view.

## S6 — Enquiries and demand v0

* World lenders generate loan applications from their origination volume.
* Subscribers decide whether to enquire (Document 07, Section 6.4, simplified).
* Enquiry → bureau search → hit / useful / correct outcome, measured against the truth.
* Basic individual credit report (structure per R9 when available).
* Usage records for billing.

**Done when:** enquiry volume responds to coverage and price in the expected direction; every enquiry is logged with its purpose.

## S7 — Finance v0

* Chart of accounts; journal posting service enforcing balance inside a transaction; reversal instead of editing.
* Automatic posting from business events: usage invoices at month-end, payroll, rent, customer payments.
* Trial balance, income statement, balance sheet, cash position.

**Done when:** every posted journal balances; statements derive only from posted entries; a full month's events produce the expected ledger.

## S8 — Thin UI

* Time controls, morning briefing and inbox.
* CEO dashboard (revenue, cash, backlog, coverage, hit rate).
* Submissions register and processing run detail.
* Work queues with match review and unloadable triage screens.
* Customer and account lookup (the bureau view).
* Ledger and statements.
* "Why?" drill-down on every figure shown.

**Phase 1 exit criteria**

1. A player can start an Established game and play one full month through the UI.
2. Five providers submit; files are processed; work items are resolved by employees and by the player.
3. Subscribers make enquiries; usage is billed; payroll and rent are posted; statements are correct.
4. The month replays identically from seed plus action log.
5. The truth-boundary contract has never been violated.
6. All checks pass.

At the end of Phase 1 the team plays it and writes down what is fun, what is tedious and what is confusing. That list shapes Phase 2.

---

# 7. Phase 2 — First Playable Slice (about 8–10 weeks)

**Objective:** Document 07, Section 13. A complete, polished and balanced experience within a narrow scope.

| Area | Work |
| --- | --- |
| Real-world fidelity | Replace placeholders with real templates, code lists, validation and error codes, matching practice and SLAs (R1–R5). Assumptions register shrinks. |
| Data Operations depth | Fuzzy matching; near-duplicates; template-mapping work items; basic rule editor; matching thresholds; tooling levels (Document 07, Section 8.2) |
| Consequences | Disputes from wrong reports; dispute work items with deadlines (L.I. 2394, R7); consequence-chain recording |
| Flywheel | Data asset metrics (coverage, depth, accuracy estimate, freshness, identity integrity); three-audience reputation; subscriber renewal and churn |
| Providers | Feedback reports, provider training, SLA penalties; Data Quality Profiles that respond to them |
| Managed systems | Sales (pipeline, pricing per R8, proposals); HR (hire, train, assign); IT (capacity, incident events with responses) |
| Pressure and failure | Cash warnings and overdraft; regulator escalation ladder; board confidence |
| Learning | Missions M1–M6; mission debriefs; monthly Data Quality Review; Bureau Handbook v1 with explicit citations (R6, R7), reviewed by the owner |
| Balancing tools | Headless simulation runs with scripted strategies ("strict quality", "fast coverage", "cheap staffing") to compare outcomes across many seeds |
| Polish | Onboarding flow, empty states, error states, performance, accessibility basics |

**Exit criteria:** Document 07, Section 13.2, in full.

---

# 8. Phase 3 — Version 1 Breadth (4–6 months)

Ordered by value; the order may change after Phase 2 playtesting.

1. **Analytics (Playable):** portfolio analytics; scorecard workbench (dataset selection, feature engineering, logistic regression, scorecard scaling, validation with AUC/Gini/KS, deployment, monitoring) using the confirmed 90+ DPD in 12 months definition (D13); read-only SQL console isolated per game with PostgreSQL row-level security; fairness checks on restricted attributes.
2. **Credit score product:** scores in reports; pricing; demand effect.
3. **Scenarios and difficulty:** Sandbox, Startup Bureau, difficulty parameter sets, assistance toggles.
4. **Economy:** progressive variables (Document 05, Section 13) driving `macro_stress` and lending volume.
5. **Compliance (Playable):** access reviews, audit findings, consent and permissible-purpose checks (R12), retention rules (R11).
6. **Finance (Playable):** reconciliation, payables, budgets versus actuals.
7. **Sales (Playable):** prospecting, negotiation, contract terms.
8. **Customer Support and Product Development (Managed).**
9. **Missions M7–M8; Handbook v2.**
10. **Business credit reports and batch enquiries.**

**Exit criteria:** PRD (Document 01) Section 25 success criteria 1, 3–15, with the department depth tiers of Document 07, Section 9.

---

# 9. Phases 4 and 5

## Phase 4 — The Office (2–3 months)

* Isometric three-floor office in React Three Fiber with a simple, consistent low-poly art style.
* Employees shown at desks, in meetings and moving, driven only by simulation state.
* Selecting desks, rooms, server racks and people opens the relevant application panel.
* Performance budget for ordinary laptops; the 2D interface remains fully playable without the office.

## Phase 5 — Release Preparation (about 1 month)

* External playtesting (D16) and fixes.
* Security review, backup and restore test, error handling review.
* Packaging and deployment to a controlled environment.
* Final title (D15) and trademark check.
* Player-facing documentation.

---

# 10. Repository Structure

```text
Bureau_Sim/
├── backend/
│   ├── config/                 settings (base, dev, test), urls
│   ├── apps/
│   │   ├── accounts/           users, roles, membership
│   │   ├── org/                organisation, departments, employees
│   │   ├── world/              GROUND TRUTH — borrowers, loans, economy,
│   │   │                       provider data-quality profiles, defect ledger
│   │   ├── simulation/         game, clock, ticks, events, scenarios, missions
│   │   ├── workitems/          work-item framework, AI resolution
│   │   ├── bureau/             the bureau's own systems:
│   │   │   ├── providers/      institutions, branches, templates
│   │   │   ├── submissions/    register, files, processing runs
│   │   │   ├── quality/        validation, cleansing, unloadables
│   │   │   ├── referencing/    customer and account matching
│   │   │   ├── core/           customers, accounts, observations, enquiries
│   │   │   └── reports/        credit reports
│   │   ├── commercial/         subscribers, products, prices, contracts, usage
│   │   ├── finance/            ledger, invoices, payments, statements
│   │   ├── analytics/          (Phase 3) datasets, models, scores
│   │   └── audit/              audit events
│   ├── tests/
│   └── manage.py
├── frontend/
│   └── src/
│       ├── app/                shell, routing, time controls
│       ├── features/           one folder per area (dataops, finance, …)
│       ├── components/         shared UI
│       ├── api/                typed API client
│       └── office3d/           (Phase 4)
├── docs/
│   ├── 01 … 07                 design documents
│   ├── assumptions.md          assumptions register
│   └── references/             source material (private/ is ignored)
├── scripts/                    check, setup and utility scripts
├── docker-compose.yml          PostgreSQL (optional)
├── .env.example
└── README.md
```

**Boundary rules (enforced by import-linter):**

* No module under `bureau/`, `commercial/`, `finance/` or `analytics/` may import `world`.
* Only `simulation` and `workitems` may read `world`, and only to drive the world and to score decisions.
* Modules talk to each other through service functions, not each other's models.

---

# 11. Definition of Done

An increment is done only when all of the following hold:

1. Its stated "done when" conditions are demonstrated.
2. Unit and integration tests cover its rules, including failure paths.
3. Every figure it adds to the UI has a working "Why?" drill-down.
4. Significant actions write audit events.
5. Any new `ASSUMPTION` is listed in the assumptions register.
6. Determinism and boundary checks still pass.
7. The `check` script passes.
8. It has been played or exercised by the team, not only tested.
9. It is committed with a clear message.

---

# 12. Testing Strategy

| Level | What it covers | Examples |
| --- | --- | --- |
| Unit | Single rules and functions | Phone normalisation, date parsing, journal balancing, P(correct) formula |
| Property | Rules that must hold for any input | Cleansing never changes a valid value; processing totals always reconcile |
| Integration | Module interactions | File → pipeline → `core.*`; month-end → invoices → ledger |
| API | Contracts, permissions, organisation isolation | A player cannot read another game's records |
| Simulation | Whole-system behaviour over time | Replay determinism; invariants checked after every tick; golden-month snapshot |
| Truth scoring | Bureau accuracy against the world | False-merge and false-split rates computed correctly |
| Balance | Game design, not correctness | Headless strategy runs across many seeds; no single dominant strategy |
| Frontend | Components and flows | Vitest for logic; Playwright for key journeys |
| End to end | Complete journeys | Start game → process month → resolve items → close month |

**Invariants checked after every tick in test runs:**

* Every observation has source lineage.
* At most one current observation per account and reporting date.
* Every posted journal balances; the trial balance balances.
* No bureau table references a world identifier.
* Task and work-item states are valid.

**Determinism rules for all code:**

* All randomness comes from the seeded streams; never the global random module, `uuid4` for logic, or wall-clock time.
* Every query whose order affects results has an explicit `ORDER BY`.
* Money uses `Decimal`; never floating point.

---

# 13. Reference Material Dependencies

Work does not stop for missing material; placeholders are used and flagged. But real rules must arrive before each phase exits.

| Material (see `docs/references/`) | Needed by | Blocks exit of |
| --- | --- | --- |
| R1 Templates, R2 Code lists | S2, S3 | Phase 2 |
| R3 Validation and error codes | S3 | Phase 2 |
| R4 Matching practice | S5 | Phase 2 |
| R5 Submission calendar and SLAs | S4 | Phase 2 |
| R6 Act 726, R7 L.I. 2394 | Disputes, Handbook | Phase 2 |
| R8 Pricing and contracts | S6, S7 | Phase 2 |
| R9 Report layouts | S6 | Phase 3 |
| R10–R16 | Phase 3 features | Phase 3 / Phase 5 |

---

# 14. Git Practice

* **Branches:** `main` is always working. Short-lived branches per increment (`feat/s3-pipeline`, `fix/…`, `docs/…`), merged when the Definition of Done is met. No `develop` branch for a two-person team.
* **Commits:** small and descriptive, using prefixes `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.
* **Tags:** each increment and phase is tagged when done (`s1`, `s2`, …, `phase-1`, `slice-1`).
* **Never commit:** `.env` files, credentials, real customer data, database dumps, or anything in `docs/references/private/`.
* **Remote:** a GitHub repository is added when the owner decides; until then the local repository is the source of truth and should be backed up.

---

# 15. Progress Tracking

Progress is tracked in `docs/progress.md`, one line per increment:

| Increment | Status | Started | Done | Notes |
| --- | --- | --- | --- | --- |

Status values: Not started, In progress, In review, Blocked, Done.

At the end of each phase, a short review records: what was built, what playing it revealed, estimate accuracy, and changes to the plan.

---

# 16. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Reference material arrives late | Placeholder rules persist; rework | Rules as configuration; assumptions register; prioritised request list |
| World model feels unrealistic | Data and scoring lose credibility | Calibrate against Bank of Ghana statistics (R15) and owner experience; tune in Phase 2 |
| The game is accurate but not fun | Players leave | Walking skeleton first; team play sessions every increment; balance tooling |
| Scope creep | Version 1 slips | Department depth tiers; Document 07 is the gate for new features |
| Determinism silently broken | Replays and tests become unreliable | Replay test from S4 onwards; determinism rules (Section 12) |
| Truth leaks into bureau code | Game becomes meaningless | import-linter contract from Phase 0; invariant check |
| Matching logic wrong | Corrupted bureau data | Truth scoring measures it directly; review queues |
| Financial inconsistencies | Wrong statements | Posting service as the only write path; balance invariants |
| Windows environment friction | Lost time | Native Django and Vite; PostgreSQL via Docker or native installer; README tested on a clean setup |
| 3D overinvestment | Delays core gameplay | 3D is Phase 4; 2D is always fully playable |
| Regulatory content inaccurate | Misleads learners | Explicit citations with source versions; owner review (D14) |

---

# 17. Immediate Next Tasks

1. Owner reviews this document.
2. Phase 0 begins: repository layout, PostgreSQL, Django, React shell, checks.
3. In parallel, the owner starts collecting Priority 1 reference material (R1–R8).
4. S1 (world generator) begins as soon as Phase 0 exits.

---

## DOCUMENT CONTROL

| Field | Value |
| --- | --- |
| Document ID | CBS-DRTP-001 |
| Version | 0.2 |
| Status | Approved |
| Change history | 0.1 module-by-module roadmap; 0.2 rewritten around the walking skeleton and first playable slice per Document 07 |
| Next step | Phase 0 in progress |
