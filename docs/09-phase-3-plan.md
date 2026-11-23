# CREDIT BUREAU SIMULATOR

## DOCUMENT 09 — PHASE 3 PLAN: VERSION 1 BREADTH

**Document ID:** CBS-P3P-001
**Version:** 0.2
**Status:** Approved by owner (23 November 2026), with the decisions in Section 8
**Date:** 23 November 2026
**Working title:** SimB
**Depends on:** CBS-DRTP-001 (06, Phase 3 is outlined in Section 8), CBS-CGD-001 (07, depth tiers in Section 9, missions in Section 11.1, scenarios and difficulty in Section 12), the PRD (01, success criteria in Section 25), CBS-P2P-001 (08, Phase 2)

---

# 1. Purpose

Phase 2 made a narrow game: Data Operations played in depth, with the rest of the company managed through menus. Phase 3 widens it to Version 1. It adds:

* analytics and a credit score;
* more departments the player can work in;
* other ways to start a game, and difficulty settings;
* an economy that changes over time.

Every Phase 2 guarantee carries forward: the bureau never reads the world, every figure drills down to its records, the books balance, and a game replays exactly.

This document:

1. reviews Phase 2 (Section 2);
2. sets out how Phase 3 starts: by closing Phase 2 (Section 3);
3. breaks Phase 3 into increments with "done when" criteria, in order (Sections 4–5);
4. maps the Version 1 success criteria to those increments (Section 6);
5. lists the reference material each increment needs (Section 7), the decisions needed from the owner (Section 8) and the risks (Section 9).

The full 3D office stays in Phase 4 (Document 06, Section 9). A short 3D trial runs early in Phase 3 (P3.2, decided in Section 8).

---

# 2. Phase 2 in Review

## 2.1 What exists

| Area | State at the end of Phase 2 |
| --- | --- |
| Data | The industry's templates, simplified (D18): consumer and business credit, dud cheques, judgements. Versioned rules with effective dates (D19) |
| Data Operations | Fuzzy matching with player thresholds and tooling; template mapping; a rule editor; provider feedback; providers that improve or sour |
| Consequences | Disputes with statutory deadlines; the regulator's ladder; reputation with three audiences; lenders that decline on bad reports; contract renewal and churn |
| Company | Hiring, training and pay; sales proposals; IT capacity and outages; overdraft, shareholder funding, board reviews; Bureau Health |
| Learning | Missions M1–M6 with debriefs; the monthly Data Quality Review; a Handbook of 23 entries (owner review pending); assistance toggles |
| Tooling | Headless strategy runs (`manage.py balance`); month-end checkpoints; a fingerprint per section for replay checks |
| Quality | All 10 checks pass; exit criteria recorded in `docs/exit-criteria.md` |

## 2.2 What went well

* **The truth boundary scaled.** Thirteen increments added systems, and none needed the bureau to read the world.
* **Replays caught real problems.** Every new player action got its replay case, and the replay tests found order-dependence early.
* **Playing in the browser kept finding bugs.** P2.13's playthrough found four problems that the tests had missed.
* **Strategy runs made balance measurable.** "Is it balanced?" became a table of numbers rather than an opinion.

## 2.3 What hurt

| Issue | Effect | Response in Phase 3 |
| --- | --- | --- |
| Backend test suite at 22–25 minutes | Each full check takes half an hour; every increment waits on it | P3.0: a fast suite for every change (target 8 minutes), with the month-long tests in a separate full run before merging |
| A month takes about 4.5 minutes to compute (P2.1 reached 95–128 s; systems added since) | "Next event" across a month-end is slow; strategy runs take hours | P3.0: profile and bring a default month back under 2 minutes |
| Intermittent replay mismatch | About one full-suite run in ten fails; the cause is unknown | P3.0: run the suite repeatedly until the per-section fingerprint catches it; fix it |
| Reference material | Pricing, salaries, costs and most regulatory texts are still placeholders | Section 7 |
| No people have played it yet | Exit criteria 1 and 8 are open | Section 3 |
| GitHub CI | Still blocked at the account level | Section 8, item 8 |

## 2.4 Known gaps carried into Phase 3

* Account lists show codes ("122", "A") rather than words.
* Mission M2 can wait days for unloadable records in a small world.
* In six-month runs, keeping the starting policies beats strict quality (`docs/balancing/README.md`).
* Only one role: the player is everyone at once. There are no workspaces by department and no permissions.
* No credit score, no analytics beyond the dashboard, no business reports, no batch enquiries.
* The economy is fixed: no inflation, interest rates or shocks.
* Only the Established scenario, at one difficulty.
* No mobile loans in the world, although they are a large and growing share of real Ghanaian lending.

---

# 3. How Phase 3 Starts: Closing Phase 2

Document 06 says Phase 3's order "may change after Phase 2 playtesting". Two Phase 2 exit criteria need people, so Phase 3 starts with them.

1. **Playtest (exit criterion 1).** The owner plays a new Established game from the Briefing through M1–M6 without help and notes the time taken. Use the Phase 1 playtest protocol (branch `docs/phase-1-playtest`, PR #12), with notes in `docs/playtests/` under *Fun*, *Tedious*, *Confusing* and *Wrong*.
2. **Three playthroughs (exit criterion 8).** Three games, each with a different strategy, at least two months each. Claude plays one in the browser and records it the same way.
3. **Joint review.** The notes become fixes (added to P3.0) and may reorder Section 4.

P3.0 can be built while the playtests happen. P3.1 waits for the joint review.

---

# 4. Phase 3 Increments

Each increment ends as in Phase 2: tests that judge it against the truth, a playthrough in the browser, all checks green, notes in `docs/progress.md` and `docs/assumptions.md`, and a pull request.

## P3.0 — Close-out and foundations

* **Test speed.** A fast suite (target 8 minutes) runs on every change, using small worlds and shared fixtures. The month-long tests move to a full run, required before merging.
* **Month speed.** Profile a default month and bring it back under 2 minutes.
* **The replay mismatch.** Run the full suite repeatedly until the per-section fingerprint catches it; find and fix the cause.
* **Codes as words.** Facility types, statuses and other codes shown with their meaning everywhere.
* **Fixes from the playtests,** M2's wait, and the owner's choice on the balancing finding.

**Done when:** the fast suite runs under 8 minutes; a default month computes under 2 minutes; 20 full-suite runs in a row pass; the playtest fixes are in.

## P3.1 — Roles and workspaces

* The player chooses a **role**: CEO, or the head of a department (Document 05, Section 6.2). Each role has its own workspace (home screen, queue and menus) and its own permissions. The CEO sees everything but works through approvals.
* Work a department head does not do falls to that department's AI staff, as in the Managed tier.
* A role switch is a recorded, replayable action. Switching is not free: a short changeover, so being everywhere at once has a cost (ASSUMPTION).
* This is the shared frame every later Playable department uses (Document 07, Section 9: "work items, tasks and employees are shared infrastructure").

**Done when:** the player can switch between CEO and Data Operations; each role sees only its own workspace and actions; the API refuses an action outside the current role; a switch replays exactly (PRD criterion 13).

## P3.2 — A short 3D trial (owner's decision, 23 November 2026)

* One floor of the office in React Three Fiber, in a simple low-poly style: Data Operations desks, a meeting room and the server rack.
* Driven only by live game state: staff at their desks, away training or gone; the queue's size shown on the desks; the server rack's lights during an outage.
* Clicking a desk, the rack or a person opens the matching 2D screen. The 2D game stays complete without it.
* A performance budget measured on the dev laptop: frame rate, load time and memory.

**Done when:** the floor shows the game as it changes (a hire appears, an outage lights the rack) without a page reload; it holds the frame-rate budget on the dev laptop; the art style and the budget are written up as the brief for Phase 4.

## P3.3 — Mobile loans in the world

Banks, savings and loans companies, microfinance lenders and fintechs grant small loans through mobile money: **GHS 10 to GHS 20,000, for one week to three months.** They are the most numerous loans in the market, and the Bank of Ghana widened credit reporting to telcos and fintechs in 2026.

* **The world:** a mobile-loan product at some lenders (and one or two digital lenders), with terms in days. Borrowers take repeated small loans, sometimes from several lenders at once ("stacking"); repayment follows the same hidden risk as their other borrowing, plus a mobile-specific behaviour (ASSUMPTION).
* **Time:** a one-week loan begins and ends inside a month, so the world records each loan's daily schedule and its month-end state. A month-end file shows the loan as closed, current or overdue.
* **Reporting** (owner, 23 November 2026): mobile loans use the same template as individual loans (CONC). What sets them apart is the file name, which has "mobile" appended, so a provider sends its mobile loans in a separate file. The file identifier becomes `CONCMOBILE`, e.g. `10118-20261130-20261201-1.1-CONCMOBILE-12.csv`. The records mostly carry facility type `122` (personal loan). The bureau registers and tracks mobile files separately, and checks that a mobile file holds only short-term loans.
* **Scale:** mobile loans can outnumber all other loans many times over. The world size and the pipeline are measured before and after; the P3.0 targets still hold.
* **Reports:** mobile loans appear on credit reports, and a short **mobile loan report** is sold for small, fast decisions (R8 placeholder).

**Done when:**
* the world produces mobile loans whose amounts, terms, repeat borrowing and default rates are recorded in `docs/assumptions.md` and checked by tests;
* they flow through the pipeline into the bureau with lineage, and the month's replay still matches;
* a default month still computes inside the P3.0 target.

## P3.4 — Analytics I: portfolio analytics and the SQL console

* Portfolio analytics: the bureau's own data by lender, product, region and vintage. Covers arrears rates, roll rates and the age of accounts at default, using the default definition of 90+ days past due within 12 months (D13).
* A read-only **SQL console** that sees only the player's own game: the bureau's tables, the ledger and the work items (owner's decision, 23 November 2026). It uses a dedicated database role with row-level security, a statement timeout and a row limit. It can never see the world layer or another game.
* Data Analytics becomes a Playable department with this workspace.

**Done when:**
* the analytics figures agree with independent queries over the same records;
* tests show the console cannot read the world, another game, or anything writeable;
* a heavy query is stopped by the timeout.

## P3.5 — Analytics II: the scorecard workbench

**Three scorecards and a composite** (owner's decision, 23 November 2026). Loans of different lengths behave differently, so each term has its own scorecard:

| Scorecard | Loans it is built on | Population |
| --- | --- | --- |
| **Short term** | Up to 3 months: mostly mobile loans (P3.3) | Many thin files; frequent, recent behaviour |
| **Mid term** | Over 3 months, up to a year | Personal and salary loans, overdrafts, hire purchase |
| **Long term** | Over a year | Term, auto, housing and mortgage loans |
| **Composite** | Everyone with a file | Combines the three |

The workbench builds each scorecard on the bureau's own data, in steps:

* choose a dataset: an observation date and an outcome window. The default for every scorecard is 90+ days past due within 12 months (D13); the short-term scorecard may also be tried on a shorter window as an option;
* engineer features (recommended starting sets below);
* bin the features and compute weight of evidence and information value;
* fit a logistic regression;
* scale the score;
* validate with AUC, Gini and KS on a held-out sample;
* deploy the model, then monitor it in later months (population stability).

**Recommended starting variables** (to adjust as play and R16 show):

| Short term | Mid term | Long term |
| --- | --- | --- |
| Mobile loans taken in the last 3 and 6 months | Worst days past due in 12 months | Worst days past due in 24 months |
| Share repaid on time | Months since the last delinquency | Months since the last delinquency |
| Worst days past due in 6 months | Utilisation of overdrafts and cards | Age of the oldest account |
| Loans open at once across lenders (stacking) | Number of open accounts | Secured share of borrowing |
| Enquiries in the last 30 days | Enquiries in the last 6 months | Instalments against total balances |
| Months since the first mobile loan | Age of the file | Dud cheques and judgements |
| Trend in loan size | Mobile-loan history as a feature | Number of facilities ever |

**Score scale and risk bands** (recommendation; adjust as needed):

* Each score runs from **300 to 850**: 600 points at odds of 30 good to 1 bad, and 20 points to double the odds.
* **The composite score** is a weighted blend of the scorecards that apply to the borrower. Each weight is the share of the borrower's recent borrowing (by balance and count) in that term, with a minimum for any term the borrower has. A borrower with only mobile loans gets the short-term score. The blend's weights are themselves fitted and validated like a scorecard.
* **Five risk bands:**

| Band | Score | Risk |
| --- | --- | --- |
| A | 750–850 | Very low |
| B | 680–749 | Low |
| C | 600–679 | Medium |
| D | 520–599 | High |
| E | 300–519 | Very high |

* **Thin files:** with no usable history, the score is "no score" (not 300), with the reason given.
* **Reason codes:** the four variables that cost the borrower most points, in plain words.

**Fairness** (owner's decision, 23 November 2026): a player may build a model on restricted attributes (such as gender). The workbench flags it, and so do proxies it detects; the outcome gaps between groups are shown. If the model is deployed, Compliance raises a finding (P3.7). Fairness checks always run against the bureau's own data.

**The truth behind it:** the world knows each borrower's true risk. The debrief shows how close each scorecard came, and what the bureau's data errors cost in score quality.

**Done when:**
* a scorecard built from clean data ranks the world's true risk measurably better than one built from data loaded under careless policies;
* each term's scorecard beats a single scorecard on its own loans, and the composite beats each on the whole population;
* the AUC, Gini and KS figures agree with an independent calculation;
* a model built on a restricted attribute is flagged, and once deployed produces a Compliance finding;
* a deployed model's monitoring flags drift when the economy changes (with P3.12).

## P3.6 — The credit score product

* Deployed scores appear on reports: the composite score with its band and reason codes, and the three term scores beneath it.
* The score is priced separately (R8); lenders' demand responds to how well the score predicts.
* Lenders use the score when deciding. The P2.8 decline rule becomes "the report and the score".

**Done when:**
* a good score lowers subscribers' default rates more than reports alone, on the same seed;
* a poor score loses them business;
* score revenue posts to the ledger.

## P3.7 — Compliance (Playable)

* **Consent and permissible purpose** (R12): the borrower gives consent on the lender's application form, and the lender keeps it. Each enquiry carries a reference to that evidence. Besides new credit, the permitted purposes are account review, employment and tenancy screening, and debt collection, all covered by the consent on the original form. The compliance officer samples enquiries, asks lenders for the forms, finds the ones without proper grounds, and acts on the subscriber.
* **Fairness findings:** a deployed scorecard that uses a restricted attribute becomes a finding (P3.5).
* **Access reviews:** who in the bureau can see what, reviewed periodically. Excess access becomes a finding.
* **Retention** (R7, R11): records past their retention period must be dropped from reports. Missing this is a finding.
* **Audit findings,** each with a deadline and a remedy.
* **Regulatory returns** to the Bank of Ghana on a calendar (ASSUMPTION until R11).

**Done when:**
* an enquiry without consent can be found by sampling, and tracked to a sanction against the subscriber;
* a missed return or a retention breach climbs the regulator's ladder;
* each rule cites its source (Act 726, L.I. 2394, Act 843 or a directive).

## P3.8 — Finance (Playable)

* Bank reconciliation: statement lines matched to ledger entries, with differences investigated.
* Payables: supplier bills approved and paid on terms.
* Budgets against actuals, by month and cost centre.
* Month-end close as a checklist the player works through.

**Done when:**
* every reconciliation difference traces to a real cause (timing, an error, a missing entry);
* the budget report agrees with the ledger;
* a late supplier payment has a consequence (a penalty, or a supplier holding back service).

## P3.9 — Sales (Playable) and cross-department workflows

* Prospecting with research on each lender's needs; meetings; negotiation over price, volume, term and service levels; contract terms (R8).
* The PRD's cross-department workflow (Section 16) runs end to end: Sales signs, Compliance checks the subscriber, IT connects it, Finance bills it, and Support answers its questions. Each step is a work item in its department.

**Done when:** a new subscriber passes through every department's step with a hand-off at each; a step left undone holds up the next, visibly; terms negotiated in the deal show up in billing.

## P3.10 — Customer Support and Product Development (Managed)

* **Support:** tickets from subscribers and data subjects. Volume rises with errors, outages and disputes. Staffing and response times move satisfaction.
* **Product Development:** a menu of products to develop, at a cost and over time. The score (P3.6), business reports (P3.11) and batch enquiries (P3.11) are developed here before they can be sold.

**Done when:** an outage produces a measurable wave of tickets; a product becomes saleable only once it has been developed.

## P3.11 — Business credit reports and batch enquiries

* Business reports from the business credit, dud cheque and judgement data already loaded. Business entities are matched by registration number.
* Batch enquiries: a lender sends a file of applicants and gets back a file of reports, priced per record (R8).

**Done when:**
* a business report shows exactly the business's facilities, cheques and judgements as loaded;
* a batch file is answered record by record, with hits and misses that agree with single enquiries;
* both are billed correctly.

## P3.12 — Economy

The economy moves through progressive stages (PRD, Section 15). Each stage's variables are set by defined rules from the seed:

* **Initial:** costs and prices.
* **Intermediate:** inflation, interest rates, wage pressure.
* **Advanced:** cycles, shocks, regulatory changes.

How the economy reaches the game:

* it drives the world's `macro_stress` and lending volume, so defaults and demand respond;
* salaries, rents and supplier costs follow inflation;
* an indicators page shows what is happening, with "Why?" links to the rules.

The bureau reads only published indicators, never the world's state.

**Done when:**
* a shock raises defaults in the world, and lenders that use the bureau well suffer less;
* costs rise with inflation;
* a scorecard deployed before a shock shows drift in its monitoring.

## P3.13 — Scenarios and difficulty

* **Sandbox:** free play with adjustable parameters (world size, starting cash, provider quality, economy stage).
* **Startup Bureau:** start with capital and nothing else. Rent an office, buy IT, hire the first team, sign the first providers and subscribers, and build the database from the first file (PRD, Section 4.2).
* **Difficulty:** Beginner, Intermediate and Expert as named parameter sets (PRD, Section 18). They change resources, costs, deadlines, the economy's stage and the severity of consequences, never the rules. Assistance toggles stay separate.

**Done when:**
* a Startup game can reach its first paid report;
* the same strategy measurably fares better at Beginner than at Expert;
* every scenario replays exactly.

## P3.14 — Missions M7–M8 and Handbook v2

* **M7, The dispute:** consumer rights, correction workflows, regulator deadlines.
* **M8, Hire or automate?** Capacity, skill, tooling and the cost of quality.
* Short missions for the new workspaces: analytics, scorecard, compliance, finance and sales.
* **Handbook v2:** entries for every new concept, with citations, reviewed by the owner (D14).

**Done when:** a scripted player completes M7, M8 and each new mission from what the screens show; every regulatory citation is either confirmed by the owner or marked TO_CONFIRM.

## P3.15 — Balancing and exit

* Strategy runs widened to the new levers: score quality, compliance effort, pricing, scenario and difficulty.
* Team playthroughs of Startup and Sandbox at two difficulties.
* Performance on a full-size game with every system on.

**Done when:** every PRD criterion in Section 6 is met and recorded in `docs/exit-criteria-v1.md`.

---

# 5. Order and Milestones

| Milestone | Increments | What the player gets |
| --- | --- | --- |
| **A: ready to widen** | Playtests, P3.0, P3.1, P3.2 | A faster, trusted base; real roles and workspaces; a first look at the office in 3D |
| **B: the data pays** | P3.3, P3.4, P3.5, P3.6 | Mobile loans; analytics, three scorecards and a composite score that sells, all judged against the truth |
| **C: a whole company** | P3.7, P3.8, P3.9, P3.10, P3.11 | Compliance, Finance and Sales to play; Support and Product to manage; business and batch products |
| **D: a changing world** | P3.12, P3.13 | An economy with stages and shocks; Sandbox, Startup and difficulty |
| **E: teach and finish** | P3.14, P3.15 | New missions, Handbook v2, balance, exit |

Milestone B comes before C because analytics and the score are the payoff of good data, the core of the game. It is also the biggest step in what the game teaches.

The economy (P3.12) could move into milestone B, since the scorecard's monitoring is most interesting once the economy moves. It sits in D so that B does not wait on it.

**Estimate:** Document 06 allows 4–6 months. Phase 2's engineering went much faster than its estimate, but Phase 3 depends more on reference material (R8, R12, R16), owner review and playtesting. A realistic plan is **3–5 months**, set mostly by those inputs.

---

# 6. Version 1 Success Criteria (PRD, Section 25)

Phase 3's exit is PRD criteria 1 and 3–15, at the depth tiers of Document 07, Section 9. Criterion 2 (the 3D office) belongs to Phase 4, with a first trial in P3.2; criterion 16 (multiplayer) to Version 2.

| # | Criterion | Where it stands | Phase 3 work |
| --- | --- | --- | --- |
| 1 | Establish or manage a functioning bureau | Manage: yes | Establish: P3.13 (Startup) |
| 3 | Synthetic institutions submit credit data | Yes | Mobile loans in P3.3; business data used fully in P3.11 |
| 4 | Submissions validated, cleaned, processed | Yes | — |
| 5 | Accepted records loaded | Yes | — |
| 6 | Customer and account history maintained | Yes | Retention in P3.7 |
| 7 | Analytics on accumulated data | Dashboard only | P3.4 |
| 8 | Credit scoring models developed and evaluated | No | P3.5 |
| 9 | Products sold, revenue recorded | Individual reports | P3.6, P3.11 |
| 10 | Statements from recorded transactions | Yes | Reconciliation and budgets in P3.8 |
| 11 | Employees perform departmental tasks | Data Operations; managed elsewhere | P3.7–P3.10 |
| 12 | Departments exchange information through connected workflows | Partly | P3.9 |
| 13 | Switch between CEO and departmental roles | No | P3.1 |
| 14 | Different starting experiences and difficulty | Established only | P3.13 |
| 15 | Economy introduces complexity progressively | Fixed economy | P3.12 |

Department tiers at the end of Phase 3 (Document 07, Section 9):

* **Playable:** Executive, Data Operations, Finance, Sales, Compliance, Data Analytics.
* **Managed:** IT, HR, Customer Support, Product Development.

---

# 7. Reference Material by Increment

As in Phase 2, rules live in configuration, so placeholders never stop building; they stop **accuracy**. "Blocking" means the game would teach something wrong without the real material.

| Increment | Needs | Blocking for release? |
| --- | --- | --- |
| P3.3 | Mobile loans: same template as individual loans, file name appended with "mobile" (owner, 23 November 2026). File identifier `CONCMOBILE`; facility type mostly `122` (owner, 23 November 2026). Typical amounts, terms, fees and default rates from BoG reports (R15) | No (tuning) |
| P3.5, P3.6 | R16 scorecard practice. **Owner's direction (23 November 2026):** short-, mid- and long-term scorecards and a composite; Claude's recommended variables, scale and bands (P3.5), adjusted as play shows | No (owner's direction stands) |
| P3.3, P3.6, P3.9, P3.11 | R8 pricing. **No published prices found;** placeholders in `references/pricing-placeholders.md`, adjusted as needed (owner, 23 November 2026) | No (placeholders accepted) |
| P3.7 | R12 consent: taken on the lender's application form (owner, 23 November 2026); account review, employment and tenancy screening and debt collection are also permitted under the same consent (owner, 23 November 2026); R7 L.I. 2394 (retention, access); R11 Bank of Ghana directives (returns, retention) | Yes |
| P3.8 | R14 operating costs; R18 taxes (already partly in) | Yes for costs |
| P3.11 | R9 report layouts (business report) | Yes |
| P3.12 | R15 Bank of Ghana statistics; Ghana inflation and policy-rate history (public) | No (tuning) |
| P3.13 | R13 salaries; R14 costs (Startup budget) | Yes |
| P3.14 | R6, R7, R10, R11, R19 (Handbook v2) | Yes |

---

# 8. Decisions for the Owner

Decided 23 November 2026:

1. **The plan is approved.**
2. **Phase 2 closes first:** the playtests (Section 3) run while P3.0 is built.
3. **The balancing finding:** still open; it goes into P3.0 with the playtest notes.
4. **The SQL console (P3.4)** sees the bureau's tables, the ledger and the work items.
5. **Fairness (P3.5):** a player may use restricted attributes. The workbench flags it, and Compliance raises a finding if the model is deployed.
6. **Reference material:**
   * R8: no prices are published, so reasonable placeholders are used, to be adjusted as needed;
   * R12: consent is given on the lender's application form;
   * R16: three term scorecards and a composite, with Claude's recommended variables, scale and bands (P3.5).
7. **A short 3D trial:** yes, as P3.2.

8. **Mobile loans (P3.3):** decided (23 November 2026): the same template as individual loans, in separate files with the identifier `CONCMOBILE` (`...-1.1-CONCMOBILE-12.csv`); lenders mostly use facility type `122` (personal loan).
9. **Other permissible purposes (R12):** decided (23 November 2026): a subscriber may also enquire to review an existing borrower's account, to screen someone being hired or a prospective tenant, and to collect a debt. The consent on the original form covers these purposes.

Still open:

10. **GitHub CI:** clear the account-level Actions issue so checks run on every pull request.

---

# 9. Risks

| Risk | Mitigation |
| --- | --- |
| Breadth dilutes depth: many thin departments, none fun | Each Playable department gets one real decision loop judged against the truth, like matching in Phase 2; strategy runs and playtests per milestone |
| Test and month times grow with every system | P3.0 targets become checks; measure every increment; the fast/full suite split |
| The SQL console exposes data across games or the world | A dedicated database role with row-level security; tests that try to break out; no writes, ever |
| Scorecard statistics are subtly wrong | An independent calculation in tests; truth-based debrief; R16 |
| Roles make the game tedious (too much switching) | Switching costs little; AI staff cover the departments the player is not in; playtest P3.1 before building more on it |
| Startup mode needs a lot of new content | Built last in milestone D on systems that already exist (hiring, sales, IT, finance) |
| Reference material arrives late | Configuration-driven rules; release-blocking items tracked separately |
| The replay mismatch hides a real determinism bug | P3.0 before anything new |

---

## DOCUMENT CONTROL

| Field | Value |
| --- | --- |
| Document ID | CBS-P3P-001 |
| Version | 0.2 |
| Status | Approved |
| Change history | 0.1 first draft after Phase 2; 0.2 approved; owner's decisions recorded; 3D trial (P3.2) and mobile loans (P3.3) added; term scorecards and composite in P3.5 |
| Next step | Phase 2 playtests; P3.0 |
