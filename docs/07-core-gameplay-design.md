# CREDIT BUREAU SIMULATOR

## DOCUMENT 07 — CORE GAMEPLAY AND LEARNING DESIGN

**Document ID:** CBS-CGD-001
**Version:** 0.2
**Status:** Approved — decisions D1–D10 approved by owner; owner inputs recorded in Section 15
**Date:** 12 November 2026
**Working title:** SimB
**Depends on:** CBS-PRD-001 (01), CBS-TAD-001 (03), CBS-DBD-001 (04), CBS-GWSD-001 (05), CBS-DRTP-001 (06)

---

# 1. Purpose

Documents 01–06 define *what the bureau contains*: departments, data, systems, accounting, an office. This document defines *what the player does and why it is interesting*.

It answers seven questions the earlier documents leave open:

1. What is the core gameplay loop, minute to minute, day to day, month to month?
2. How does time map to real time?
3. Where does the synthetic data come from, and how is "right" and "wrong" defined?
4. How do the departments connect into one business engine rather than ten parallel modules?
5. How do real operations (the actual pipeline) and simulated work (employee skill, morale, workload) meet?
6. How can the player fail, and how do they recover?
7. How does a player learn how a real credit bureau works simply by playing well?

It ends with the exact contents of the **first playable slice**, and a decisions log recording where this document amends earlier ones.

Where this document conflicts with documents 01–06, this document takes precedence until those documents are revised.

---

# 2. Audience and Design Pillars

## 2.1 Audience

The primary audience is **players**: people who enjoy management and simulation games and are curious about how a credit bureau works.

A secondary audience is **learners**: students and early-career professionals who want to understand the credit bureau space. They are served by the same game. Learning comes from playing well, not from a separate curriculum. Classroom tooling (teacher dashboards, grading) is out of scope for Version 1.

Because a player can quit at any moment, the game must be engaging on its own terms. Realism matters because it is what makes the game *different*, not because it is required content.

## 2.2 Design pillars

Every feature should be checked against these five pillars. A feature that serves none of them is cut or deferred.

**P1 — Real work, real consequences.**
Operations are performed on real (synthetic) data by real code. A wrong decision produces a wrong record, and that record causes harm later through a traceable chain.

**P2 — One business engine.**
Every department pushes on a shared flywheel (Section 6). No department is a standalone mini-game.

**P3 — Truth versus the bureau's view.**
The simulated world has a hidden ground truth. The bureau only ever sees an imperfect reported version of it. The gap between the two *is* the data quality game.

**P4 — Every number can explain itself.**
Any figure on any screen can be drilled into, down to the records and decisions that produced it. Employees can explain why they did what they did.

**P5 — Pressure creates decisions.**
The player never has enough time, people or money to do everything well. Interesting play comes from choosing what to neglect.

---

# 3. The Player Fantasy

> "I run a credit bureau. Banks send me messy files; I turn them into trustworthy credit histories; lenders pay me to use them. If I get it right, the business grows. If I cut corners, real people get wrongly declined, regulators come knocking, and clients leave. I can step into any desk and do the work myself, but I can't do it all. I have to build a team I trust."

The player is simultaneously:

* **The CEO**, setting priorities, spending money and making strategic bets.
* **A hands-on specialist**, stepping into a role to make the judgement calls that matter most.
* **A manager**, deciding which work to delegate, to whom, and how much to trust them.

---

# 4. Core Loops

The game has four nested loops. Each outer loop is built from the inner ones.

## 4.1 The work loop (seconds to minutes of real time)

The atomic unit of play is a **work item**: a single judgement call on real data.

```text
Pick a work item from a queue
      ↓
Inspect the evidence (records, history, provider profile)
      ↓
Decide (e.g. merge / keep separate / return to provider / correct / reject)
      ↓
Immediate feedback (record state changes, queue shrinks)
      ↓
Delayed feedback (consequences surface days or months later)
```

Examples of work items:

| Work item | Decision | Department |
| --- | --- | --- |
| Uncertain customer match | Same person, different person, or escalate | Data Operations |
| Unloadable record | Correct, return to provider, or reject | Data Operations |
| New template mapping | Map provider columns to the bureau standard | Data Operations |
| Consumer dispute | Uphold, reject, or request evidence from the provider | Compliance / Support |
| Report quality check | Release or hold a report with suspicious content | Data Operations |
| Invoice exception | Approve, adjust, or write off | Finance |
| Incident diagnosis | Choose the cause and remedy from evidence | IT |
| Sales proposal | Set price, terms and product bundle | Sales |

Work items are the heart of the "the player operates the bureau" promise in the PRD. They are deliberately **decisions, not data entry**. The game never asks the player to retype records.

## 4.2 The day loop (about 3 real minutes at 1x speed)

```text
Morning briefing
  - What arrived overnight (files, enquiries, tickets, incidents)
  - What is due today
  - What is at risk
      ↓
Set priorities
  - Reorder queues, assign people, choose which items to do personally
      ↓
Run the day (time advances)
  - AI employees work their queues
  - Interrupts arrive (incidents, escalations, calls); severe ones auto-pause
  - The player works items in any role
      ↓
End-of-day summary
  - Throughput, backlog, errors caught, money in and out
```

## 4.3 The month loop (about 60 real minutes at 1x, much less at higher speeds)

The month is the natural rhythm of a credit bureau because providers report monthly.

```text
Days 1–10   Submission window: provider files arrive (some late, some dirty)
Days 1–15   Processing: validate, cleanse, match, load
Ongoing     Subscribers make enquiries; reports are produced and billed
Day 20+     Month-end close:
              - Subscriber invoicing
              - Payroll and rent
              - Provider data quality scorecards issued
              - Reputation and KPIs updated
              - Board / CEO monthly report
              - Objective and mission check
```

## 4.4 The strategic loop (quarters and years)

* Hire, train and restructure.
* Invest in tooling and automation (Section 7.4).
* Onboard new providers; win new subscribers.
* Launch products (e.g. a credit score, portfolio monitoring).
* Respond to economic shifts and regulatory change.
* Quarterly board review (Established mode).

---

# 5. Time Model

Document 05 left the real-time mapping open. This document fixes the defaults. All values are configurable.

## 5.1 Clock

| Unit | Value |
| --- | --- |
| Simulation tick | 15 simulated minutes |
| Working day | 08:00–17:00 (36 ticks) |
| Real time per simulated hour at 1x | 20 seconds |
| Real time per working day at 1x | 3 minutes |
| Real time per month at 1x | about 60 minutes (about 20 working days) |
| Speeds | Paused, 1x, 2x, 4x, 8x, and "skip to next event" |

The calendar uses real dates and real weekdays. Nights, weekends and public holidays are skipped automatically. Overnight batch work (e.g. scheduled loading jobs) completes during the skip.

## 5.2 Auto-pause

The game pauses automatically when:

* A **critical** event occurs (outage, regulator notice, major client threatening to leave).
* A mission step requires player input.
* A decision deadline is about to pass with no owner assigned.

Players can configure which event severities auto-pause.

## 5.3 Deterministic stepping

The simulation advances in discrete ticks. Each tick:

1. Is identified by `(game_id, tick_number)`.
2. Runs in one database transaction.
3. Uses a random number generator seeded from `(world_seed, tick_number, stream_name)`.
4. Is idempotent: re-running a committed tick does nothing.

Consequences:

* Given the same seed and the same player actions, a game replays identically. This makes balancing, testing and bug reproduction practical.
* The simulation does not need a scheduler such as Celery Beat. The backend advances ticks when the player's clock is running. A tick loop runs in a dedicated worker process, or on demand in the request for "advance one hour/day".

---

# 6. The Business Engine (Flywheel)

## 6.1 The flywheel

```text
          ┌──────────────────────────────────────────────┐
          │                                              │
          ▼                                              │
   DATA ASSETS                                           │
   coverage · depth · accuracy · freshness               │
          │                                              │
          ▼                                              │
   REPORT VALUE                                          │
   hit rate · usefulness · trust                         │
          │                                              │
          ▼                                              │
   SUBSCRIBER DEMAND ──► REVENUE ──► INVESTMENT ─────────┤
   enquiries · contracts            people · tools ·     │
          │                         products             │
          ▼                                              │
   REPUTATION ──► leverage with providers ──► more and   │
                  better data ───────────────────────────┘
```

Each link is a defined formula over stored records, never an arbitrary number (Document 05, Section 15).

## 6.2 Data assets

| Asset | Definition | Measured against |
| --- | --- | --- |
| **Coverage** | Share of the world's active borrowers that the bureau holds at least one account for | World truth |
| **Depth** | Months of history held per account | Bureau database |
| **Accuracy** | Share of loaded facts that match the truth (balances, statuses, identity links) | World truth |
| **Freshness** | Age of the latest observation per active account | Bureau database and clock |
| **Identity integrity** | Rate of false merges (two people as one) and false splits (one person as two) | World truth |

The player sees coverage, depth and freshness directly. Accuracy and identity integrity are **estimated** for the player (through sampling audits, disputes and complaints), because a real bureau never knows its true error rate. Their true values are revealed in debriefs (Section 11.2).

## 6.3 Report value and hit rate

When a subscriber enquires about an applicant:

* **Hit:** the bureau finds the applicant. P(hit) depends on coverage of that applicant's segment.
* **Useful hit:** the report contains enough history to inform a decision. This depends on depth and freshness.
* **Correct hit:** the report is accurate. This depends on accuracy and identity integrity.

A subscriber's perceived value of the bureau is a rolling average of these outcomes, weighted towards recent experience. Wrong reports weigh most heavily, because a wrong report harms a real (simulated) person and the lender's decision.

## 6.4 Subscriber demand

Each subscriber is a world lender with a real origination pipeline driven by the economy. For each loan application in the world:

```text
P(lender checks our bureau) = f(perceived value, price, service reliability,
                                relationship, contract terms)
```

Enquiries become billable usage. Contract type (pay-per-report, monthly bundle, annual subscription) determines invoicing. Usage, complaints and service level determine renewal probability.

In Version 1 the alternative is "no bureau check / manual check". Rival bureaus are deferred (Document 05, Section 14.2), but the demand formula already includes an "outside option" term so competitors can be added later without redesign.

## 6.5 Provider relationships

In the game world, regulation obliges lenders to report credit data. The challenge is therefore not persuading lenders to report but:

* **How fast** the bureau can onboard them (template mapping, testing, IT integration).
* **How good** their data becomes, which depends on feedback, training and SLA enforcement.
* **How willing** they are to cooperate. A provider pushed too hard on quality may become slow or uncooperative. A provider never challenged stays dirty.

Each provider has a **Data Quality Profile** (Section 7.2) that changes in response to the bureau's actions. This gives the player a real lever and a real tension.

## 6.6 Reputation

Reputation is tracked separately for three audiences, each from its own measured inputs:

| Audience | Driven by |
| --- | --- |
| Subscribers | Hit rate, report accuracy, turnaround, uptime, support resolution, dispute outcomes |
| Providers | Feedback quality, onboarding speed, fairness of SLA enforcement, relationship meetings |
| Regulator | Dispute handling within deadlines, access control, audit findings, timely reporting, incidents |

## 6.7 How each department pushes the flywheel

| Department | Primary lever |
| --- | --- |
| Data Operations | Accuracy, freshness, identity integrity |
| Sales & Business Development | Subscribers, contracts, provider onboarding pipeline |
| Data Analytics | Report value (scores, insights), new products |
| IT & Infrastructure | Reliability, capacity, processing speed |
| Customer Support | Subscriber satisfaction; first line for disputes |
| Risk & Compliance | Regulator reputation; dispute resolution; access control |
| Finance | Cash runway; billing accuracy; ability to invest |
| HR & Administration | Capacity, skill, morale, retention |
| Product Development | New revenue streams; product quality |
| Executive Management | Priorities, budget, strategy |

---

# 7. The World Model

This is the most important technical idea in this document.

## 7.1 Three layers

```text
┌───────────────────────────────────────────────┐
│ 1. WORLD (ground truth) — hidden               │
│    Real borrowers, real identities, real loans,│
│    real repayment behaviour, the economy       │
└───────────────────────┬───────────────────────┘
                        │ each provider reports its own book
                        │ through its Data Quality Profile (noise)
                        ▼
┌───────────────────────────────────────────────┐
│ 2. SUBMISSIONS — what providers send           │
│    Monthly files: late, incomplete, inconsistent│
└───────────────────────┬───────────────────────┘
                        │ the bureau's pipeline + people's decisions
                        ▼
┌───────────────────────────────────────────────┐
│ 3. BUREAU VIEW — what the bureau believes      │
│    core.* tables from Document 04              │
└───────────────────────────────────────────────┘
```

* The **world** is generated from a seed and evolves every month.
* **Submissions** are files produced by passing each provider's true book through that provider's noise model.
* The **bureau view** is the existing bureau database design (Document 04).

The bureau code (pipeline, reports, analytics) must **never read the world layer**. Only the simulation engine, the scoring of player decisions, and debriefs may read it. This is enforced by module boundaries and tested.

## 7.2 Borrowers and loans

Each world borrower has:

* **True identity:** name, date of birth, synthetic Ghana Card number, phone numbers, address, region.
* **Latent attributes (never shown):** risk propensity, income level and stability, financial literacy, sector of work.
* **Relationships:** a borrower may hold loans with several lenders, which is what makes the bureau valuable.

Businesses have equivalent attributes: registration, TIN, sector, size, and latent financial health.

Each month, every active loan evolves:

```text
P(missed payment this month) = logistic( β0
                                       + β1 · latent_risk
                                       + β2 · debt_burden
                                       + β3 · macro_stress(sector, region)
                                       + β4 · recent_missed_payments )
```

Days past due, arrears, restructuring and write-offs follow from missed payments under each lender's policy.

This gives the game three essential properties:

1. **Credit scoring is meaningful.** Defaults are genuinely predictable from bureau-visible history, so a good scorecard really performs better than a bad one.
2. **The economy has a mechanism.** Recessions raise `macro_stress` and therefore real defaults, which the player sees in the data months later.
3. **Data value is real.** Lenders who check the bureau and decline risky applicants really do have fewer defaults in their simulated books.

## 7.3 Provider Data Quality Profiles

Each provider has a profile of how its files deviate from the truth:

| Defect | Example |
| --- | --- |
| Missing mandatory fields | Blank Ghana Card number |
| Format inconsistency | Phone as `0244123456`, `+233244123456`, `244-123-456` |
| Typos in identity | `Kwame Mensah` vs `Kwame Mensa` |
| Wrong identifier | Another customer's ID pasted in |
| Duplicate rows | Same account twice in one file |
| Stale values | Balance not updated from last month |
| Inconsistent status | Status "closed" with a positive balance |
| Date problems | `DD/MM/YYYY` vs `MM/DD/YYYY`; future disbursement dates |
| Template drift | Columns renamed or reordered without notice |
| Late submission | File arrives after the deadline |
| Missing accounts | Some accounts silently omitted |

Each defect has a rate. Rates change in response to:

* Feedback reports the bureau sends (better feedback means faster improvement).
* Training sessions the bureau runs for the provider.
* SLA penalties (which improve quality but cost relationship goodwill).
* The provider's own technology investment, which depends on its world finances.

Because defects are injected deliberately, the game always knows the correct answer for every record. That is what makes Section 8 possible.

## 7.4 World scale

Defaults for the Established scenario, tuned so a monthly file processes in seconds on ordinary hardware:

| Item | Default |
| --- | --- |
| Individual borrowers | 40,000 |
| Business borrowers | 4,000 |
| Lenders in the world | 12 (5 reporting as providers, 3 of which also subscribe; 7 not yet signed) |
| Active credit facilities | about 70,000 |
| Monthly file size per provider | 2,000 – 25,000 rows |
| Pre-generated history (Established) | 36 months |

The 36 months of pre-generated history matter because a meaningful default definition (e.g. 90+ days past due within 12 months) needs at least 24 months of data to train and validate a model.

---

# 8. The Work Model — Where Real and Simulated Work Meet

## 8.1 Principle

> **Pipelines are deterministic code. Judgement is a work item. Skill is the probability of judging correctly.**

## 8.2 Automated stages versus work items

Every processing stage in Documents 03–04 is real code. Each stage produces either **automatic outcomes** (clear-cut) or **work items** (needs judgement):

| Stage | Automatic outcome | Becomes a work item when… |
| --- | --- | --- |
| Template validation | File accepted or rejected | Columns do not match but are plausibly mappable |
| Field validation | Field valid or invalid | Invalid but correctable (e.g. ambiguous date) |
| Cleansing | Rule applied | No rule covers the case |
| Duplicate detection | Exact duplicate removed | Near-duplicate |
| Customer referencing | Exact identifier match linked | Partial or conflicting match |
| Account referencing | Known account gets a new observation | Account number changed or reused |
| Loading | Accepted records loaded | Load conflicts with existing observation |

The bureau's **tooling level** (an investable upgrade) determines how much is automatic. Early tooling produces many work items. Better tooling (stronger matching, more cleansing rules, automated feedback) produces fewer, but costs money and IT capacity, and over-aggressive automation can make confident mistakes.

## 8.3 How AI employees resolve work items

Because the world truth is known (Section 7.3), every work item has a correct answer. An employee resolving an item:

```text
time_to_resolve = base_time(item_type, difficulty)
                  / (skill_factor · morale_factor · tooling_factor)
                  · fatigue_factor(workload)

P(correct)      = f(skill in item_type, item difficulty,
                    fatigue, training received)
```

The outcome is drawn from the seeded RNG. A wrong decision is applied to the bureau database exactly as a right one would be. A false merge really links two people's records.

So employee attributes affect outcomes "in predictable and testable ways" (Document 05, Section 8.1):

* **Skill** sets accuracy.
* **Experience** grows skill per item type with repetition.
* **Morale and workload** affect speed and accuracy.
* **Training** raises skill in a specific item type, at a cost of money and time away from work.

Every AI decision is logged with its inputs ("matched on phone + DOB; names differ by one character; confidence 0.71"), satisfying the explainability requirement in Document 05.

## 8.4 How the player resolves work items

The player resolves the same work items through the same screens. The differences:

* The player's accuracy is their own judgement. The game does not roll dice for the player.
* The player's throughput is limited by **their real time**. While the clock runs, AI employees keep working; the player cannot clear every queue alone.
* The player can **set policy instead of deciding items**: write or adjust validation and cleansing rules, set matching thresholds, decide what gets escalated. Policies resolve whole classes of items automatically, and their accuracy is measured against the truth like anyone else's.

This creates the central management tension: **do it yourself (accurate but slow), delegate (fast but only as good as the team), or automate (fastest, but mistakes happen at scale)**.

## 8.5 Consequence chains

Mistakes are not punished instantly. They travel through the system and surface later, which is both more realistic and more instructive.

**Example 1: a false merge**

```text
Data officer merges Ama Owusu (b. 1990) with Ama Owusu (b. 1992)
      ↓ weeks later
A lender enquires about the 1992 Ama; the report shows the 1990 Ama's default
      ↓
The lender declines her application
      ↓
She files a dispute (world borrowers dispute errors with a probability)
      ↓
Compliance has a deadline to investigate and correct
      ↓ if missed
Regulator finding → regulator reputation falls → possible penalty
      ↓ always
Subscriber trust falls slightly (a wrong report was delivered)
```

**Example 2: rejecting too aggressively**

```text
Strict rules reject every record with a non-standard phone format
      ↓
Unloadable rate rises; coverage and freshness fall
      ↓
Hit rate falls; subscribers notice "no record found"
      ↓
Provider receives a huge rejection report and grows frustrated
```

**Example 3: under-investing in infrastructure**

```text
Storage passes 85% utilisation
      ↓
Probability of a processing slowdown rises each day
      ↓
Backlog grows; month-end files miss the processing SLA
      ↓
Freshness drops and reports are stale
```

Every consequence chain is recorded so the debrief (Section 11.2) can replay it for the player.

---

# 9. Departments in Version 1: Depth Tiers

Not every department needs to be fully playable in Version 1. Each department is given a depth tier.

| Tier | Meaning |
| --- | --- |
| **Playable** | The player can take the role and resolve work items in a dedicated workspace |
| **Managed** | Runs as a simulated system; the player makes decisions through menus, events and approvals but has no workbench |
| **Abstracted** | Represented as costs, capacity and modifiers only |

| Department | First playable slice | Version 1 |
| --- | --- | --- |
| Executive Management | Playable | Playable |
| Data Operations | **Playable (deepest)** | Playable |
| Finance & Accounting | Managed (auto-posting, review and approve) | Playable |
| Sales & Business Development | Managed (pipeline, pricing, proposals) | Playable |
| Risk & Compliance | Managed (disputes as work items, findings as events) | Playable |
| IT & Infrastructure | Managed (capacity, incidents as events) | Managed |
| HR & Administration | Managed (hire, train, assign from menus) | Managed |
| Customer Support | Abstracted (ticket volume affects satisfaction) | Managed |
| Data Analytics | Abstracted (portfolio dashboards only) | Playable (scorecard workbench, SQL console) |
| Product Development | Abstracted | Managed |

Later versions can promote any department to Playable without redesign, because work items, tasks and employees are shared infrastructure.

---

# 10. Pressure, Failure and Recovery

## 10.1 Pressure

The player is under constant, legible pressure from:

* **Queues** that grow faster than the team can clear them.
* **Deadlines:** submission SLAs, dispute deadlines, month-end close, regulatory returns.
* **Cash:** payroll and rent are due whether or not subscribers have paid.
* **Trade-offs:** speed versus accuracy, strictness versus coverage, growth versus control.

## 10.2 Failure states

Soft failures (always recoverable): lost subscribers, falling reputation, staff resignations, provider non-cooperation.

Hard failures (game over), each preceded by explicit warnings and a recovery window:

| Failure | Warning path |
| --- | --- |
| **Insolvency** | Cash below one month's costs → overdraft facility used → creditors' notice → insolvency |
| **Licence revoked** | Regulator concern letter → formal directive → financial penalty → licence suspension → revocation |
| **Removed by the board** (Established mode only) | Board confidence falls below a threshold for two consecutive quarterly reviews |

The game should always make the path to recovery visible. A player should never lose without having understood why.

## 10.3 Success

Following Document 05 (Section 16.4), success is multi-dimensional. A **Bureau Health** summary combines financial health, data quality, reputation (three audiences), compliance standing and team health. Objectives and achievements reward several playstyles: operational excellence, commercial growth, technology leadership, analytics innovation and financial sustainability.

---

# 11. Learning Built Into Play

## 11.1 Guided missions

The Established mode opens with an optional campaign of short missions. Each mission teaches one real concept by having the player do it.

| # | Mission | Real concept taught |
| --- | --- | --- |
| M1 | **First file** | Submission registration, template validation, processing summary |
| M2 | **Dirty data** | Field validation, cleansing, the unloadable record, provider feedback |
| M3 | **Is this the same person?** | Identity resolution, false merges versus false splits |
| M4 | **Month two** | Monthly observations versus new accounts; history and lineage |
| M5 | **The first report** | Enquiries, consent and permissible purpose, hit rates |
| M6 | **Closing the month** | Usage billing, invoices, double-entry posting, the P&L |
| M7 | **The dispute** | Consumer rights, correction workflows, regulator deadlines |
| M8 | **Hire or automate?** | Capacity, skill, tooling and the cost of quality |

Missions sit on top of the normal simulation. They do not use special scripted data, but they choose seeds and events that produce the situation they teach.

## 11.2 Debriefs

At the end of each mission, and in a monthly "Data Quality Review", the game reveals a slice of the hidden truth:

* "Your team resolved 214 match reviews. 197 were correct. 11 were false merges and 6 were false splits."
* "This false merge led to this declined application and this dispute." (replays the consequence chain)
* "Your strict phone rule rejected 1,840 records. 1,792 of them were genuine customers."

Debriefs are the main teaching instrument. They turn invisible errors into a story the player can follow.

## 11.3 "Why?" everywhere

Every metric, every employee decision and every event offers a **Why?** link that drills down to the underlying records (Pillar P4). This is the same mechanism that serves debugging and testing.

## 11.4 The Bureau Handbook

An in-game reference that explains each concept the player encounters (e.g. "days past due", "permissible purpose", "unloadable record", "double-entry"), with an "In practice" note on how it works in the real Ghanaian market.

Regulatory content is **explicit**: the Handbook and in-game rules cite the relevant provisions of the Credit Reporting Act, 2007 (Act 726), the Credit Reporting Regulations, 2020 (L.I. 2394), the Data Protection Act, 2012 (Act 843) and Bank of Ghana directives by name and section. The project owner reviews all regulatory content before release. Each citation records the source document and version it was taken from, so it can be updated when the law changes.

The Handbook still carries a disclaimer that it is educational and not legal advice.

---

# 12. Scenarios, Difficulty and Saves

## 12.1 Scenarios

A scenario is a configuration: world seed, world size, starting organization, starting finances, provider and subscriber set, active missions and event set.

| Scenario | When |
| --- | --- |
| **Established Bureau** (with campaign) | First playable slice |
| **Sandbox** (free play, adjustable parameters) | Version 1 |
| **Startup Bureau** | Version 1 |

## 12.2 Difficulty

Difficulty is a named parameter set (Document 05, Section 4) plus **assistance toggles** that are independent of difficulty:

* Show estimated accuracy on work items.
* Show recommended decisions.
* Auto-pause on all events.
* Extended deadlines.

This lets a learner keep realistic economics while still receiving guidance.

## 12.3 Saves

* One game corresponds to one `organization` plus one world.
* The game autosaves at every committed tick (it is a live database).
* Named checkpoints are taken automatically at each month-end and on demand.
* Because the simulation is deterministic (Section 5.3), a checkpoint plus the player action log can reproduce any later state. This is used for testing and bug reports, not player-facing time travel.

---

# 13. First Playable Slice

The first playable slice is the target for roughly the first four months of development. It is complete, polished and fun within a narrow scope. It is not a prototype.

## 13.1 Contents

**Scenario:** Established Bureau, one world size, Normal difficulty with assistance toggles.

**World:** 40,000 individuals, 4,000 businesses, 12 lenders (5 providers, 3 of which also subscribe; 7 prospects), 36 months of history.

**Playable roles:** CEO; Data Operations Officer; Data Operations Head (assigns and sets policy).

**Managed systems:** Sales (pipeline, pricing, proposals to prospects); Finance (automatic posting from business events; invoice approval; P&L, balance sheet, cash view); Compliance (disputes as work items); IT (capacity and incident events); HR (hire, train, assign).

**Missions:** M1–M6.

**Screens (2D, no 3D office yet):**

* Morning briefing and inbox
* Time controls
* CEO dashboard with drill-down
* Data Operations: submissions register, processing run detail, work queues, match review, unloadable triage, template mapping, basic rule editor
* Customer and account lookup (the bureau view)
* Sales pipeline and contract terms
* Finance: ledger, invoices, statements
* People: roster, assignments, skills, training, hiring
* Debrief and monthly Data Quality Review
* Bureau Handbook

## 13.2 Exit criteria

The slice is complete when:

1. A new player can complete M1–M6 without outside help in about two hours.
2. Three months of play run without errors or inconsistencies.
3. Two clearly different strategies (e.g. "strict quality" and "fast coverage") lead to measurably different outcomes, and neither dominates.
4. Every dashboard figure drills down to underlying records.
5. A replay test reproduces a full game month exactly from seed plus action log.
6. Every posted journal balances; financial statements derive only from posted entries.
7. The bureau modules never read the world layer (enforced by tests).
8. The project team has played it end to end at least three times with different strategies and recorded its findings. (External playtesters join after the slice; see Section 15.)

---

# 14. Decisions Log (Amendments to Documents 01–06)

| # | Decision | Amends |
| --- | --- | --- |
| D1 | **PostgreSQL replaces Microsoft SQL Server** as the primary database. Reasons: free at any scale, first-class Django support, simpler hosting and local setup, row-level security for future player SQL consoles. | 01 §21, 03 §3, 04 throughout, 06 |
| D2 | **Celery and Redis are deferred.** The first slice uses one Django process plus a simple database-backed job runner and a simulation worker. Celery is introduced only if a measured workload requires it. | 03 §9, 05 §20.3 |
| D3 | **A `world` module and schema** hold ground truth. Bureau modules may not read it. | 03 §6, 04 §2.2 |
| D4 | **Database amendments:** add `core.provider_customer_link` (institution, provider customer ID → bureau customer); make `(institution_id, facility_account_number)` a UNIQUE constraint on `core.credit_account`; design `core.enquiry`; replace `UQ_account_reporting_date` with a partial unique index on current observations (`WHERE is_current`), supporting the correction workflow. | 04 §7, §16 |
| D5 | **Time model** as in Section 5 (15-minute ticks, deterministic stepping, auto-pause). | 01 §14, 05 §10 |
| D6 | **Department depth tiers** as in Section 9 replace "ten fully functional departments" for the first slice. | 01 §23, 05 §23 |
| D7 | **Roadmap reordered** around a walking skeleton: world generator → provider file → pipeline → bureau DB → enquiry → invoice → ledger → clock, thin and end to end, before any module is deepened. The 3D office remains last. | 06 §3–§10 |
| D8 | **Identifier hashing and encryption** are deferred for synthetic data. Identifiers are stored in plain form, with access control. | 04 §6.4 |
| D9 | **Audience:** a game first; learning is built into play; classroom tooling is out of Version 1 scope. | 01 §2 |
| D10 | Document 01 v0.1 is archived; the Functional Specification (CBS-FS-001) will not be written as a separate document. Its role is covered by Documents 01, 05 and 07 together. | All |

---

# 15. Owner Inputs (Resolved)

| # | Topic | Decision |
| --- | --- | --- |
| D11 | **Domain fidelity** | The game mirrors real-world practice in every area: submission templates and field lists, status and error codes, validation rules, matching practice, dispute timelines, report layouts, consent and permissible purpose, retention, pricing and contracts. Simplification is allowed only in pacing and scale, never in what the rules are. Source material is collected in [`docs/references/`](references/README.md). Where no source is available, the item is marked `ASSUMPTION` in code and documents until verified. |
| D12 | **Pricing** | Realistic GHS prices and contract structures, taken from reference material provided by the owner. Placeholder values are flagged `ASSUMPTION` until then. |
| D13 | **Default definition** | Confirmed: **90+ days past due within a 12-month performance window.** |
| D14 | **Regulatory content** | Explicit, cited by Act and section (Section 11.4). The owner reviews all regulatory content. |
| D15 | **Title** | Working title **SimB**. A final title will be chosen before any public release. |
| D16 | **Playtesting** | The project team are the playtesters for the first slice. External players join afterwards. |

## 15.1 Market context to reflect

The real Ghanaian market informs the simulated one:

* The Bank of Ghana licenses and supervises credit bureaus; in recent years the market has been dominated by one bureau by enquiry volume, with a small number of competitors. Rival bureaus remain deferred (Document 05, Section 14.2), but the demand model's "outside option" (Section 6.4) should be calibrated with this in mind.
* The set of institutions that participate in credit reporting has been widening beyond banks and savings and loans (e.g. microfinance, fintechs, and more recently telcos and retailers). Provider types in the world model should support this range, even if the first slice uses only banks, savings and loans, and microfinance lenders.
* Real bureau names and brands are **not** used in the game. All bureaus, lenders and people are fictional.

These points must be checked against the reference material in `docs/references/` before they become game rules.

---

## DOCUMENT CONTROL

| Field | Value |
| --- | --- |
| Document ID | CBS-CGD-001 |
| Version | 0.2 |
| Status | Approved |
| Change history | 0.1 draft; 0.2 owner approved D1–D10 and resolved open questions (D11–D16) |
| Next step | Collect reference material; revise Document 06 (roadmap) to reflect Sections 13–15 |
