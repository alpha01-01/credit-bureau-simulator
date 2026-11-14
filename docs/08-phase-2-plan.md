# CREDIT BUREAU SIMULATOR

## DOCUMENT 08 — PHASE 2 PLAN: THE FIRST PLAYABLE SLICE

**Document ID:** CBS-P2P-001
**Version:** 0.2
**Status:** Approved by owner (14 November 2026); the order of Section 4 may change after the playtest. Section 7, items 3–5 remain open
**Date:** 14 November 2026
**Working title:** SimB
**Depends on:** CBS-CGD-001 (07, the slice is defined in Section 13), CBS-DRTP-001 (06, Phase 2 is outlined in Section 7)

---

# 1. Purpose

Phase 1 proved the machine works end to end. Phase 2 turns it into a game: the **first playable slice** of Document 07, Section 13. It is complete, polished and balanced within a narrow scope, and a new player can learn the bureau business from it without outside help.

This document:

1. reviews Phase 1 honestly (Section 2);
2. sets out how Phase 2 starts: with the team playing what exists (Section 3);
3. breaks Phase 2 into increments with "done when" criteria, in order (Sections 4–5);
4. lists the reference material each increment needs (Section 6), the decisions needed from the owner (Section 7) and the risks (Section 8).

---

# 2. Phase 1 in Review

## 2.1 What exists

| Area | State at the end of Phase 1 |
| --- | --- |
| World | 40,000 people, 4,000 businesses, 12 lenders; 36 months of history; lives through each month of play; loan applications with declines |
| Providers | Five reporting providers; 14 kinds of data defect, each recorded with the correct value |
| Pipeline | Register, file checks, staging, cleansing, duplicates, validation, matching (with review of weak identifier matches), loading with full lineage |
| Work | Data Operations queue (match review, unloadable triage); a team of three with skill, fatigue and learning; player decisions |
| Commercial | Three subscribers; demand driven by price and perceived value; enquiries, reports, usage |
| Finance | Double-entry ledger; invoices, payments, payroll (PAYE, SSNIT), rent, taxes; statements from posted entries |
| Time | 15-minute ticks over Ghana working days and holidays; deterministic replay |
| UI | Browser game: briefing, dashboard with "Why?", submissions, work queue, customers, enquiries, finance |
| Quality | 123 backend tests, 7 frontend tests, a browser end-to-end test; import-linter truth boundary; all checks pass |

## 2.2 Measured on the default world

| Measure | Value |
| --- | --- |
| Established game creation (12 months of history) | 753 s |
| January hit rate (established bureau) | 85% (46% for a bureau with no history) |
| January enquiries | 1,502; GHS 22,530 of usage |
| One game month, played headless | about 2.5–3 minutes |
| Staff accuracy (January) | senior 86%, officer 81%, junior 70% |
| Backend test suite | about 2.5–4 minutes |

## 2.3 What went well

* **The truth boundary held.** The bureau never reads the world; the answer key comes from the simulation. Every increment's tests could judge the bureau against the truth.
* **Determinism paid for itself.** Replay tests caught two real bugs (world advancement and month-boundary events).
* **Deliberate breakage.** Each increment's key test was checked by breaking the code on purpose; none of those tests was vacuous.

## 2.4 What hurt

| Issue | Effect | Response in Phase 2 |
| --- | --- | --- |
| Bugs found only by playing | S8 surfaced six defects that 120 tests missed (CSRF behind the proxy, login state, revenue in the wrong month, weekend deadlines) | Play every increment in the browser before calling it done; one browser test per major screen |
| Speed | 12.5-minute game creation; 3-minute months; slow test suite | Increment P2.1 |
| Reference material | Every Ghana-specific rule is still a flagged placeholder (A-001 to A-035) | A running track (Section 6); rules already live in configuration |
| GitHub CI | Blocked at the account level; checks run only on the laptop | Owner to clear the account issue (Section 7) |
| Memory on the laptop | A check run failed when RAM was exhausted | Single-threaded maths in checks; watch memory in P2.1 |

## 2.5 Known gaps carried into Phase 2

* The clock runs in real time only with a separate `run_clock` process.
* Events happen silently: there is no event feed and no auto-pause.
* The bureau's mistakes have no consequences beyond the data (no disputes, no churn, no regulator).
* Lenders do not act on reports: a bureau report never changes a credit decision in the world.
* Provider data quality never changes, whatever the bureau does.
* Staff cannot be hired, trained or lost; no sales; no IT.
* There are no missions, debriefs or Handbook: the game does not yet teach.

---

# 3. How Phase 2 Starts: the Team Plays

Document 06 (Section 6) asks the team to play Phase 1 and record what is fun, tedious and confusing before Phase 2 is shaped. The increments in Section 4 are a proposal; the playtest may reorder them.

**Protocol (about two hours each, both of us separately):**

1. Start an Established game on the default world.
2. Play January to the start of February: read the briefing each morning, decide at least 20 work items yourself, follow at least five "Why?" links, close the month and read the statements.
3. Write notes in `docs/playtests/2026-11-phase-1-<name>.md` under four headings: *Fun*, *Tedious*, *Confusing*, *Wrong* (anything that does not match real bureau practice).

**Then:** a short joint review turns the notes into changes to Section 4.

---

# 4. Phase 2 Increments

Each increment ends like a Phase 1 step: tests that judge it against the truth, played in the browser, all checks green, a pull request.

## P2.0 — Real templates and versioned rules (added 14 November 2026; D18–D20)

Done in three parts, each its own pull request:

* **a. Credit templates.** Replace placeholder SIMB-T0 with the industry-standard templates as simplified (consumer 74 columns, business 63; proposal section 11), with the standard's names, codes, file naming (SRN), pipe-delimited CSV, `YYYYMMDD` dates and whole-number amounts (`references/data-formats.md`). Rejection strictness becomes a bureau policy (standard or core fields). Follow real practice from the cleanser rules: cleanse first and reject only on the required fields; asset classification `A`–`E`; `NDIA`; no reporting-date column; `CorrectionIndicator` 0/1/2; a valid ID mandatory for records from 1 January 2020; the real duplicate rule; disbursement-date mismatch.
* **b. Versioned rules.** Templates, code lists, validation rules and prices carry a version and an effective date. Every submission, run, invoice and decision records the version it used, so a rule change never rewrites the past.
* **c. Dud cheques and judgements.** The world produces bounced cheques and court judgements; providers report them on their own templates; the bureau loads them and shows them on the credit report.

**Done when:** a game plays a month on the real templates with every existing guarantee intact (ledger of defects, lineage, reconciliation, replay); a template or price change made mid-game applies only from its effective date; dud cheques and judgements appear on reports.

## P2.1 — Speed and stability

* Game creation for an Established bureau under 2 minutes (a dedicated bulk path for history, generated world files reused across games).
* One game month under 60 seconds headless on the default world; pipeline load profiling.
* Backend test suite under 2 minutes (shared fixtures, fewer month-long tests).
* Month-end checkpoints (Document 07, Section 12.3).

**Done when:** the targets above are met on the dev laptop and recorded in `docs/progress.md`.

## P2.2 — Events, notifications and the live clock

* An event feed: what just happened, with severity and a "Why?" link (file arrived, file rejected, payment received, deadline approaching).
* Auto-pause on critical events and when a decision deadline is near, with player-set rules (Document 07, Section 5.2).
* The clock runs in real time from the browser without a separate process.

**Done when:** a player can leave the game running at 1x and be stopped for every critical event; nothing important happens silently.

## P2.3 — Data assets and the monthly Data Quality Review

* Data asset metrics (Document 07, Section 6.2): coverage, depth, freshness (visible); accuracy and identity integrity (estimated for the player, true values in the review).
* Consequence-chain recording: every wrong decision and its later effects are linked.
* The monthly **Data Quality Review**: the first debrief. It shows how many match decisions were right, which merges were false, and how many rejected records were genuine.

**Done when:** after one month the review reports figures that the tests confirm against the truth, and each one drills down to its records.

## P2.4 — Data Operations depth I: matching

* Fuzzy matching when no identifier matches (name, date of birth, phone), producing candidate matches and false-split detection.
* Near-duplicate records.
* Matching thresholds as player policy; tooling levels as an investment (Document 07, Section 8.2).

**Done when:** raising or lowering a threshold measurably trades false merges against false splits, shown in the Data Quality Review.

## P2.5 — Data Operations depth II: templates, rules and feedback

* Template-mapping work items when a provider's layout drifts (D17).
* A basic rule editor for cleansing and validation rules, with each rule's effect measured.
* Provider feedback reports: what was rejected and why.

**Done when:** a drifted file can be mapped and loaded by the player; a player-written cleansing rule changes the next run's results, measured against the truth.

## P2.6 — Providers respond

* Data Quality Profiles that change with feedback quality, training sessions and SLA penalties (Document 07, Section 6.5).
* Provider goodwill: pushing too hard slows cooperation.

**Done when:** a provider given good feedback and training sends measurably cleaner files over three months; one penalised repeatedly becomes slower to respond.

## P2.7 — Disputes and compliance

* Subjects dispute wrong reports (especially from false merges), with a probability.
* Dispute work items with statutory deadlines (L.I. 2394; reference R7), corrections through supersession records (Document 04, Section 19).
* The regulator escalation ladder: concern letter, directive, penalty, suspension (Document 07, Section 10.2).

**Done when:** a false merge can be followed from the decision to the dispute and its correction, and a missed deadline produces a regulator finding.

## P2.8 — The flywheel turns

* Reputation with subscribers, providers and the regulator, each from its own measured inputs (Document 07, Section 6.6).
* Subscriber contract renewal and churn.
* **Lenders act on reports:** a subscriber declines applicants whose report shows serious arrears, so data quality changes real lending outcomes in the world (Document 07, Section 7.2, property 3).

**Done when:** with the same seed, a high-quality bureau's subscribers end the year with measurably lower default rates and higher renewal than a careless bureau's.

## P2.9 — Managed departments: HR, Sales, IT

* HR: hire from a candidate pool, train, set salaries; morale and resignations.
* Sales: prospects among the seven non-subscribing lenders; proposals, pricing (reference R8), contracts.
* IT: processing capacity and incidents as events with response choices.

**Done when:** hiring a senior officer, signing a new subscriber and suffering an outage each show up in the queue, revenue and freshness metrics as expected.

## P2.10 — Pressure and failure

* Cash warnings, an overdraft facility and the insolvency path.
* Quarterly board reviews and board confidence (Established mode).
* A Bureau Health summary (Document 07, Section 10.3).

**Done when:** each hard failure can be reached deliberately, is preceded by its warnings, and shows the path back.

## P2.11 — Learning: missions, debriefs, the Handbook

* A mission framework (objectives, progress, completion) with missions M1–M6.
* A debrief at the end of each mission.
* Bureau Handbook v1 with explicit citations of Act 726, L.I. 2394 and Act 843 (references R6, R7, R10), **reviewed by the owner** (D14).
* Assistance toggles (Document 07, Section 12.2).

**Done when:** a new player completes M1–M6 without outside help in about two hours (Document 07, Section 13.2, criterion 1).

## P2.12 — Balancing

* Headless runs with scripted strategies ("strict quality", "fast coverage", "cheap staffing") across many seeds.
* Tuning of the economy, demand, staff and penalties.

**Done when:** two clearly different strategies lead to measurably different outcomes and neither dominates (criterion 3).

## P2.13 — Polish and exit

* Onboarding, empty and error states, accessibility basics, performance.
* Three full team playthroughs with different strategies, recorded (criterion 8).

**Done when:** every exit criterion in Document 07, Section 13.2 is met and recorded.

---

# 5. Order and Milestones

| Milestone | Increments | What the player gets |
| --- | --- | --- |
| **A: a game that responds** | Playtest, P2.0, P2.1, P2.2, P2.3 | Fast to start, never silent, and it tells you how good your data really is |
| **B: Data Operations in depth** | P2.4, P2.5, P2.6 | Real matching decisions, rules you write, providers that change |
| **C: consequences** | P2.7, P2.8 | Mistakes reach people, lenders and the regulator |
| **D: running the company** | P2.9, P2.10 | Staff, sales, IT, money and the board |
| **E: a game that teaches** | P2.11, P2.12, P2.13 | Missions, debriefs, Handbook, balance and polish |

Milestone A comes first because every later increment needs speed, visible events and the truth-revealing review to be judged and played.

**Estimate:** Document 06 allowed 8–10 weeks. Phase 1's pace suggests the engineering fits, but Phase 2 depends far more on reference material, playtesting and balancing, which take calendar time. A realistic plan is **10–14 weeks**, with milestones A and B within the first half.

---

# 6. Reference Material by Increment

Rules already live in configuration, so placeholders never block building. They block **accuracy**. Increments that would teach something wrong without the real material are marked *blocking for release*.

| Increment | Needs | Blocking for release? |
| --- | --- | --- |
| P2.4, P2.5 | R1 templates, R2 code lists, R3 validation and error codes, R4 matching practice | Yes |
| P2.6 | R5 SLAs | Yes |
| P2.7 | R7 L.I. 2394 (dispute deadlines), R6 Act 726, R10 Act 843 | Yes |
| P2.8 | R15 Bank of Ghana statistics (calibration) | No (tuning) |
| P2.9 | R8 pricing, R13 salaries, R14 operating costs | Yes for pricing |
| P2.10 | R11 Bank of Ghana directives (regulator actions) | Yes |
| P2.11 | R6, R7, R9, R10, R12 | Yes (Handbook citations) |
| Throughout | R17 holidays, R18 taxes | Yes |

---

# 7. Decisions for the Owner

1. **Approve this plan**, or reorder it after the playtest (Section 3).
2. **Playtest first?** The proposal is a short team playtest before P2.1.
3. **GitHub CI:** clear the account-level Actions issue (or make the repository public) so checks run on every pull request.
4. **Lenders act on reports (P2.8):** confirm that subscribers should decline applicants on bad reports. It makes data quality matter in the world, and it changes world outcomes per game (worlds stay deterministic per game, not shared across games from that point).
5. **Reference material:** which of R1–R18 can arrive during milestones A–B, so P2.4–P2.7 can use real rules.

---

# 8. Risks

| Risk | Mitigation |
| --- | --- |
| The slice is accurate but not fun | Playtest before and during; balancing increment; scripted-strategy runs |
| Reference material arrives late | Configuration-driven rules; release-blocking items tracked separately from building |
| Shared worlds diverge once lenders act on reports (P2.8) | Decide in Section 7, item 4; the world may need a per-game layer for decisions |
| Performance regresses as systems are added | P2.1 targets become checks; measure each increment |
| Learning content is inaccurate | Owner review of all regulatory content (D14); citations with source versions |

---

## DOCUMENT CONTROL

| Field | Value |
| --- | --- |
| Document ID | CBS-P2P-001 |
| Version | 0.2 |
| Status | Approved |
| Change history | 0.1 first draft after Phase 1; 0.2 owner approved the plan and the playtest-first start |
| Next step | Team playtest; reorder Section 4 if needed; owner decisions on Section 7, items 3–5 |
