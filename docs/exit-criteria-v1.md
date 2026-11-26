# Version 1: exit criteria (PRD Section 25; Document 09, Section 6)

Where each criterion stands at the end of Phase 3 (P3.15, 26 November 2026), and the
evidence. As in Phase 2 (`exit-criteria.md`), a criterion is **met** when its evidence
is a passing test or a recorded result, at the depth Document 07, Section 9 sets for
Version 1; **open** when it needs people or the owner. Phase 3's exit is criteria 1 and
3-15: criterion 2 (the 3D office) belongs to Phase 4, with a first trial in P3.2, and
criterion 16 (multiplayer) to Version 2.

Every test named here passes in `scripts/check.py --full` on the commit that adds this
file (CI is blocked by the account's billing lock; the local full check is the gate).

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A player can establish or manage a functioning virtual credit bureau | Met | **Manage:** an Established game starts with its past loaded and settled and is useful from the first day (`test_history.py`); a scripted player completes the campaign M1-M8 from what the screens show (`test_learning.py`). **Establish:** a Startup reaches its first paid report from GHS 2,000,000 and nothing else (`test_scenarios.py::test_a_startup_reaches_its_first_paid_report_and_replays`); scripted Startups at Beginner and Expert ran six months to paying subscribers (`docs/balancing`, P3.15) |
| 2 | The player can navigate the 3D office and interact with departments | Phase 4 | A first trial of one floor (P3.2, `test_departments.py::test_the_office_shows_who_is_where_the_queue_and_the_systems`) |
| 3 | Synthetic institutions can submit credit data | Met | Providers' monthly files from the world, individual and business (`test_provider_files.py`, `test_events.py`); files arrive on their day (`test_clock.py::test_files_arrive_on_their_day_and_are_processed_overnight`); mobile loans in their own files (`test_mobile.py`); a Startup onboards its providers (`test_scenarios.py`) |
| 4 | The system can genuinely validate, clean and process submissions | Met | `test_pipeline.py` (validation, normalisation, drifted and repeated files, duplicates, reconciliation); player rules measured against the truth (`test_rules_feedback.py`); matching and its trade-off (`test_matching.py`); work items decided by staff or the player (`test_work_items.py`) |
| 5 | Accepted records can be loaded into the bureau database | Met | Every observation traces to its file and row, totals reconcile, reprocessing never duplicates (`test_pipeline.py`); every processing run reconciles after three months of play (`test_exit_criteria.py`) |
| 6 | Historical customer and account information can be maintained | Met | Months add observations to existing accounts (`test_pipeline.py`); disputes correct accounts with an audit trail (`test_disputes.py`); a retention period beyond the law is a breach the regulator records (`test_compliance_duties.py`) |
| 7 | Analytics can be performed on accumulated credit information | Met | Portfolio analytics agree with the records (`test_analytics.py`); the SQL console sees only its own game's bureau data and cannot write (`test_console.py`); mission W1 is answered from the analytics screen (`test_missions_v2.py`) |
| 8 | Credit scoring models can be developed and evaluated | Met | The workbench end to end, every statistic checked against its definition (`test_scorecards.py`, `test_scoremath.py`); scores evaluated against the world's true defaults; a careful scorecard predicts them (AUC 0.82) and sells, a careless one does not (`test_levers.py`, P3.15); a deployed scorecard drifts after a shock (`test_economy.py`) |
| 9 | Products can be sold and revenue recorded | Met | Consumer reports, the score, mobile-loan checks, business reports and batches billed and posted (`test_enquiries.py`, `test_score_product.py`, `test_business_and_batch.py`); a product is sold only once developed (`test_managed.py`); a subscriber passes through every department on its terms (`test_onboarding.py`); price moves volume and revenue (`test_levers.py`) |
| 10 | Financial statements can be generated from recorded transactions | Met | Only balanced entries post; statements come from posted entries and balance (`test_finance.py`); budgets agree with the ledger and every reconciliation difference has a cause (`test_finance_dept.py`); checked again after three months of play (`test_exit_criteria.py`) |
| 11 | Employees can perform simulated departmental tasks | Met | Staff work the queue and explain every decision, skill and fatigue measurably change accuracy (`test_work_items.py`); hiring, pay, morale and resignation (`test_departments.py`); Support and Product Development managed (`test_managed.py`) |
| 12 | Departments can exchange information through connected workflows | Met | A new subscriber passes through Sales, Compliance, Finance and Data Operations (`test_onboarding.py`); a false merge is followed from the report to the dispute and its correction (`test_disputes.py`); careful data makes lenders lend better and stay (`test_flywheel.py`); an outage brings Support tickets (`test_managed.py`) |
| 13 | The player can switch between CEO and departmental roles | Met | `test_roles.py`: the CEO keeps the company decisions; taking over a department takes half an hour, then its work is the player's; every action has an owner; role switches replay. The campaign and workspace missions are played in their roles (`test_learning.py`, `test_missions_v2.py`) |
| 14 | The player can choose different starting experiences and difficulty settings | Met | Established, Startup and Sandbox (`test_scenarios.py`); the same strategy fares better at Beginner than at Expert (`test_scenarios.py`), and in a Startup and a Sandbox too (`docs/balancing`, P3.15); every scenario replays exactly |
| 15 | The economic environment can progressively introduce more complex conditions | Met | Stages from costs and prices to inflation, cycles and shocks; a shock raises defaults and lenders using the bureau suffer less; costs rise with inflation (`test_economy.py`); the difficulty sets how soon and how hard (A-083) |
| 16 | The architecture can support the planned multiplayer expansion | Version 2 | Each game is its own organisation; other players cannot see your game (`test_ui_api.py`); the bureau never reads the world (import contracts, `scripts/check.py`) |

## Also needed for the release

These do not change a criterion's status above, but the release waits on them.

| Item | Who | Where it stands |
| --- | --- | --- |
| Team playthroughs of Startup and Sandbox at two difficulties (Document 09, P3.15) | Owner and team | Claude's scripted playthroughs are recorded (`docs/balancing`, P3.15); playthroughs by people remain, as do the Phase 2 criteria 1 and 8 (`exit-criteria.md`) |
| The owner's review of the regulatory content (D14) | Owner | 33 citations listed in `references/regulatory-review.md`; until then every one is marked TO_CONFIRM, as a test enforces (`test_missions_v2.py`) |
| Reference texts blocking accuracy (Document 09, Section 7) | Owner | R6, R7, R10, R11, R19 (Handbook v2, compliance rules); R9 (business report layout); R13, R14 (salaries and costs) |
| Balance findings 5, 9 and 10 (`balancing/README.md`) | Owner to choose | Strict quality against the starting policies on the default world; diligent compliance costs nothing; the score's payback |
| Month speed: 252 s against 3 minutes; analytics' first view 4 s (Performance, below) | Owner to schedule | An optimisation increment, starting with the applications |
| GitHub CI (Document 09, Section 8, decision 10) | Owner | Blocked by the account's billing lock |

## Performance (P3.15)

A full-size game with every system on (`manage.py perf`; results in
`balancing/perf-full.json`): the default world (40,000 people, seed 44) with mobile
loans and the standard economy, an Established bureau with 12 months of history, the
campaign on, the score developed and careful scorecards deployed, Compliance's consent
checks and access review kept up, two months of play.

| Measure | Result | Target |
| --- | --- | --- |
| A new game's 12 months of history | 1,000 s the first time in a world (the template is built); 240 s after (copied) | — |
| A month of play | 253 s and 252 s (the first run, straight after the world was built and before the query changes below, took 385 s and 312 s) | 3 minutes with mobile loans (Document 09, decision 8a): **over, open** |
| Every screen's API (44), median of three calls | All under 0.5 s but two: accounts 433 ms (slowest 568 ms) and analytics | 0.5 s (P2.13) |
| Analytics | 14.1 s before P3.15; 4.1 s now on the first view after new data, then 3 ms from the cache | **Over on the first view, open** |
| The scorecard workbench | 8.5 s before P3.15; 7 ms now | Met |

**What P3.15 changed.** The reporting dates the bureau holds (first, latest, each
lender's latest) now come from its submissions, not from every observation: an
observation's date is always its submission's month. The accounts reported by a date are
found by an index probe each. The analytics are kept, by bureau, date and data version,
until new data arrives (`apps/bureau/analytics/portfolio.py`; tested in
`test_analytics.py`).

**Where a month's time goes** (profiled, 286 s under the profiler): answering 3,215
lenders' applications, 125 s (building each report, 40 s; judging it against the truth
and tracing its consequences, 26 s); processing the providers' files, 52 s; the month's
review and data assets, 37 s; mission checks each tick, 15 s; rescoring everyone on
file, 13 s. Winning back a minute and a half is an increment of its own (the
applications first). At 1x a game month is about an hour of real time, so play never
waits on the engine; "Next event" across a month-end does.
