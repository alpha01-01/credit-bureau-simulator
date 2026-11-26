# CREDIT BUREAU SIMULATOR

## DOCUMENT 10 — PHASE 4 PLAN: THE OFFICE

**Document ID:** CBS-P4P-001
**Version:** 0.1
**Status:** Draft for owner review
**Date:** 26 November 2026
**Working title:** SimB
**Depends on:**
* CBS-DRTP-001 (06): Phase 4 is outlined in Section 9.
* The PRD (01): the office in Sections 5.3, 6 and 20.1; success criterion 2 in Section 25.
* CBS-GWSD-001 (05): the virtual office in Section 5.
* CBS-P3P-001 (09): Phase 3.
* The P3.2 trial brief: `docs/office-3d-brief.md`.

---

# 1. Purpose

Version 1 is complete in 2D. Phase 3 met PRD criteria 1 and 3–15 (`docs/exit-criteria-v1.md`). Phase 4 builds the remaining criterion, number 2:

> The player can navigate the 3D office and interact with departments.

That means an isometric three-floor office with:
* the staff at their desks, in meetings and moving between rooms;
* objects the player selects to reach the game.

The office is a **view of the simulation, not a second game**. Its rules:

* **Read only from the bureau's state.** It never reads the world, as the rest of the bureau never does.
* **Actions go through the same API as the 2D screens.** Every action taken from the office is recorded and replays exactly, and the role permissions (P3.1) apply.
* **It never shows what the backend does not hold** (Document 05, Section 5.4). Nobody is drawn working on an item that is completed, cancelled or unassigned.
* **The 2D game stays complete without it** (Document 05, Section 6.3). The office is never the only way to do anything.

This document:

1. reviews Phase 3 (Section 2);
2. sets out how Phase 4 starts, by closing Phase 3 (Section 3);
3. breaks Phase 4 into increments with "done when" criteria, in order (Sections 4–5);
4. maps the office requirements to those increments (Section 6);
5. lists the decisions needed from the owner (Section 7) and the risks (Section 8).

---

# 2. Phase 3 in Review

## 2.1 What exists

| Area | State at the end of Phase 3 |
| --- | --- |
| Data | Mobile loans in `CONCMOBILE` files alongside the Phase 2 templates; an economy with stages, inflation, rates and shocks |
| Playable departments | Executive, Data Operations, Data Analytics, Finance, Sales, Compliance, each in its own role and workspace |
| Managed departments | IT, HR, Customer Support, Product Development |
| Products | Consumer and business reports, batch enquiries, three term scorecards and a composite score, and the mobile loan report |
| Scenarios | Established, Startup and Sandbox, at Beginner, Intermediate and Expert |
| Learning | Missions M1–M8 and the short department missions; Handbook v2 |
| Office | One trial floor of Data Operations (P3.2), drawn from `GET /games/<id>/office/` |
| Tooling | Strategy runs over every lever, scenario and difficulty; `manage.py perf` for a full-size game |

## 2.2 What went well

* **The truth boundary held again.** Fifteen increments, and the bureau never read the world.
* **Strategy runs judged every new lever.** Each lever (score quality, compliance effort, pricing, difficulty) came with a number showing what it does.
* **The P3.2 trial was cheap and told us a lot.** One floor met every budget, and the pattern (an endpoint, a pure layout function, a page that only draws) is the one Phase 4 needs.

## 2.3 What hurt

| Issue | Effect | Response in Phase 4 |
| --- | --- | --- |
| A full-size month takes about 250 s (allowance 3 minutes, 8a in Document 09). Applications take 125 s and the pipeline 52 s | "Next event" across a month-end is slow, and the office would sit still while it runs | P4.0 |
| The full test suite takes about 80 minutes, and the fast suite 10 (target 8) | Every merge waits more than an hour | P4.0: bring the fast suite back under 8 minutes. Office work is mostly frontend, so it rarely needs the full run |
| Two balance findings are open: diligent compliance costs nothing (9), and the score takes about two years to pay back (10) | Two levers teach a lesson that is weaker than intended | P4.0, with the owner's choice (Section 7) |
| Team playthroughs, D14 citations and reference texts are open | Release items, not Phase 4 work | Tracked in `docs/exit-criteria-v1.md`; they run alongside Phase 4 |
| GitHub CI is still blocked | The local full check is the only gate | Section 7, item 8 |

## 2.4 Known gaps carried into Phase 4

* Games loaded before the facility-status codes changed (e.g. 15 and 16) show an empty live book in Analytics.
* The trial's people stand by their chairs rather than sitting, and know only "at the desk" or "not here" (brief, findings 2 and 3).
* The office download carries the whole of three.js (brief, finding 1).
* No floor yet for the ground floor's departments or the executive floor.
* Meetings are not places in the game. The Data Quality Review, board reviews and sales meetings happen, but nobody is anywhere while they do.

---

# 3. How Phase 4 Starts: Closing Phase 3

The Phase 3 items that are not code run alongside Phase 4 and do not block it:

1. **Team playthroughs** of Startup and Sandbox at two difficulties, recorded in `docs/playtests/` as before.
2. **D14:** the owner reviews the Handbook's citations.
3. **Reference texts:** R6, R7, R10, R11 and R19 for the Handbook; R9 for the business report layout; R13 and R14 for salaries and costs.

The Phase 3 items that are code go into P4.0, before the office is built on top of the month.

---

# 4. Phase 4 Increments

Each increment ends as in Phase 3:
* tests that judge it against the game's state;
* a playthrough in the browser;
* all checks green;
* notes in `docs/progress.md` and `docs/assumptions.md`;
* a pull request.

Every increment that adds to the office also measures it against the budget (Section 4.1) and records the figures.

## 4.1 The office's budget (from the P3.2 brief, widened to three floors)

| Measure | Budget |
| --- | --- |
| Frame rate on the dev laptop, busiest floor | 60 frames a second |
| Frame rate on the low-spec laptop (Section 7, item 6) | 30 frames a second, with shadows off if needed |
| JavaScript memory with the office open | +80 MB |
| The office's download | 400 KB compressed, loaded only when the Office is opened |
| Download for the rest of the game | Unchanged |
| Data from the server | One small request every 2 s, for the floor in view only |

## P4.0 — Close-out and foundations

* **Month speed.** Bring a full-size month (default world, every system on) back under the 3-minute allowance. The profile points at the applications step (125 s) first, then the pipeline (52 s).
* **Fast suite** back under 8 minutes.
* **Balance findings 9 and 10**, as the owner chooses (Section 7, item 3).
* **Old status codes.** Analytics reads games loaded before the facility-status codes changed: the old codes are mapped, or such games are marked as unsupported.
* **Trim three.js.** Register only the classes the office uses (R3F's `extend`), then measure the download again (brief, finding 1).

**Done when:**
* `manage.py perf` records a full-size month under 180 s;
* the fast suite runs under 8 minutes;
* findings 9 and 10 have the owner's decision and are applied, with strategy runs showing the effect;
* game 16's Analytics shows its live book;
* the trial floor's download is smaller than 245 KB compressed.

## P4.1 — The building and its floors

* **A building model.** Three floors, each a set of rooms and the departments in them (PRD, Section 6.2; Document 05, Section 5.2), held as data with the scenario. A Startup's rented office has fewer rooms (Document 05, Section 5.2), with the desks its office provides (P4.8).
* **One endpoint per floor,** in the pattern of P3.2: `GET /games/<id>/office/<floor>/`. It returns only what that floor draws.
* **A pure layout function per floor,** unit-tested without WebGL, as `frontend/src/lib/office.ts` is today.
* **Navigation:**
  * move between floors;
  * turn the view in quarter turns (Document 05, Section 5.1: "different angles");
  * zoom to a department and back;
  * keyboard controls for each of these.
* **The text fallback** grows with the floors: every room and person drawn is also a link with a one-line summary.

**Done when:**
* the player can move between three floors (or a Startup's one office) and turn the view, by mouse and by keyboard;
* each floor's layout tests show the rooms of PRD Section 6.2;
* the floors stay inside the budget on the dev laptop.

## P4.2 — Where people are

Today the game knows only whether someone is at their desk. Phase 4 makes **places part of the game's state**:
* desks;
* meeting rooms;
* the training room;
* the boardroom;
* the cafeteria;
* "out" (on a course outside, on leave, gone).

* **Where each person is follows from what they are doing,** at the tick shown:
  * working on an item: at their desk;
  * in the monthly Data Quality Review: in the meeting room;
  * in a board review: in the boardroom;
  * on a sales meeting: away at the prospect;
  * on a course: in the training room or out;
  * free during working hours: at their desk, or at the cafeteria for a break (ASSUMPTION: the break follows from morale and hours worked);
  * after hours: out.
* **No randomness in the view.** Where a person is follows from the game's state alone, so two people watching the same game at the same tick see the same office.
* **Replay is untouched.** The location is computed from what the game already records, not stored as a new state. Where an event has no time today (a meeting), it gains one, and that time is part of the replay.
* **The Document 05 rule as a test.** The office never shows anyone working on an item that is not in progress and assigned to them.

**Done when:**
* a test for each activity shows the person in the right place at the right tick;
* a property test over a month of ticks finds nobody shown working on an item the backend does not have in progress and assigned to them;
* a game replays exactly with this increment in.

## P4.3 — Figures and movement

* **Figures of a few parts,** still low-poly: seated at the desk facing the screen, standing, walking (brief, finding 2).
* **Walking between places** when a person's place changes. The walk is drawn by the browser between two refreshes, along simple paths between doors and stairs. It is decoration over the state, never state.
* **Time of day:** the light follows the game's clock, and the office darkens after hours (brief, finding 5).
* **The busiest case:** the largest staff the game allows on one floor, all moving at once, measured against the budget.

**Done when:**
* a hire walks in and sits down;
* a person leaving for the Data Quality Review walks to the meeting room, and back afterwards;
* the busiest floor holds 60 frames a second on the dev laptop.

## P4.4 — The first floor: data and technology

The trial floor becomes the whole first floor (PRD, Section 6.2):
* Data Operations;
* Data Analytics;
* IT and Infrastructure;
* Product Development;
* the server room;
* the technical meeting room.

* **The server room** shows utilisation, storage, availability and maintenance status when selected (PRD, Section 6.3), from the IT state the game already holds. Racks light up during an outage, and IT staff walk to them while an incident is open.
* **Analytics desks** show the models being built and deployed. **Product Development** shows products in development, with their progress.
* **Selecting** a desk, a computer, a person or a rack opens the matching 2D screen, as in the trial.

**Done when:**
* every department on the floor is drawn from its own state;
* an outage shows on the racks and draws IT staff to the server room within one refresh;
* selecting each object opens its 2D screen.

## P4.5 — The ground floor: the public face

The ground floor (PRD, Section 6.2):
* Reception;
* Customer Support;
* Sales and Business Development;
* Finance and Accounting;
* HR and Administration;
* the cafeteria;
* the visitor waiting area.

* **Reception and the waiting area** show visitors from the game's own events: data subjects coming to dispute a record, prospects coming to meet Sales (ASSUMPTION: a visit is drawn from a dispute or a meeting that is already in the game).
* **Customer Support** shows the open tickets on the desks, so a wave of tickets after an outage is visible.
* **The cafeteria** shows employee welfare: morale and hours (Document 05, Section 5.3).
* **Finance** shows the month-end close checklist's progress on its desks.

**Done when:**
* a dispute brings a visitor to reception, and closing it ends the visit;
* an outage's wave of tickets shows on the Support desks;
* selecting the cafeteria shows the welfare figures;
* every object on the floor opens its 2D screen.

## P4.6 — The second floor: the executive floor

The executive floor (PRD, Section 6.2):
* the CEO's office;
* executive management;
* the boardroom;
* Risk and Compliance;
* the executive meeting rooms.

* **The boardroom** fills for board reviews. Selecting it opens the board's last review.
* **Risk and Compliance** shows its open findings and samples in progress.
* **The CEO's desk** opens the CEO's workspace.
* **The notice board** shows announcements and objectives: the current mission, the month's targets and the regulator's open actions (Document 05, Section 5.3).

**Done when:**
* a board review fills the boardroom;
* a new compliance finding appears on the floor within one refresh;
* the notice board shows the current mission and the regulator's open actions;
* every object on the floor opens its 2D screen.

## P4.7 — Acting from the office

Document 05, Section 5.3 asks for more than opening screens: inspect, assign or discuss tasks with an employee; schedule meetings.

* **Context menus** on people and objects offer the actions the 2D screens already have: assign a work item, send someone on a course, open their record, approve a bill at Finance, start a consent sample at Compliance.
* **Each action calls the same API** as the 2D screen, so it is recorded and replays exactly, and the API refuses it outside the player's role (P3.1).
* **Meetings:** what "schedule a meeting" means is the owner's choice (Section 7, item 4).

**Done when:**
* each context-menu action has a test showing it produces the same recorded action as its 2D screen;
* an action outside the player's role is refused from the office as it is in 2D;
* a game played partly from the office replays exactly.

## P4.8 — The office grows

The game already has two offices for a Startup (`apps/simulation/startup.py`): the SMALL serviced office in Osu (10 desks) and the STANDARD office floor at Ridge (45 desks). Hiring waits for desks.

* **A Startup's office** is drawn as the space it rents: one small office, or one floor laid out with the rooms that fit, until it moves into the building.
* **Growing into the three-floor building** is the owner's choice (Section 7, item 9).
* **Capacity is visible.** Empty desks show room to hire, and a full office shows that hiring needs more space.
* **The established bureau** starts in the full building.

**Done when:**
* a Startup's office matches the space it rents at every step from founding;
* when no desk is free, hiring is refused in 2D, and the office shows why.

## P4.9 — Performance, accessibility and exit

* **The low-spec laptop** (Section 7, item 6): every floor measured. If needed, drop shadows, then the device pixel ratio, then far detail, in that order (brief, finding 6).
* **Accessibility:**
  * every object can be reached and opened by keyboard;
  * the text fallback lists everything drawn;
  * state is shown by shape and position as well as colour, for colour-blind players.
* **A playthrough mostly from the office:** a month of an Established game played by moving through the office, with 2D screens opened from it. Recorded under *Fun*, *Tedious*, *Confusing* and *Wrong*.
* **Exit:** PRD criterion 2 recorded in `docs/exit-criteria-v1.md`, with the budget figures.

**Done when:**
* every floor meets the budget on the dev laptop and on the low-spec laptop;
* the playthrough is recorded;
* criterion 2 is met and recorded.

---

# 5. Order and Milestones

| Milestone | Increments | What the player gets |
| --- | --- | --- |
| **A: a firm base** | P4.0, P4.1, P4.2 | A faster month; a building with three floors to move around; people where the game says they are |
| **B: a living office** | P4.3, P4.4 | People who sit, walk and meet; the whole first floor, with the server room |
| **C: the whole building** | P4.5, P4.6 | The ground and executive floors: reception, support, the cafeteria, the boardroom and the notice board |
| **D: play from the office** | P4.7, P4.8, P4.9 | Acting from the office; an office that grows with a Startup; performance on ordinary laptops; exit |

P4.2 (where people are) comes before the figures and the other floors because everything visible depends on it. It is also the one increment that touches the simulation, so its replay risk is dealt with first.

The first floor comes before the others because the trial already started it and Data Operations is the heart of the game.

**Estimate:** Document 06 allows 2–3 months. Phase 3's engineering ran well ahead of its estimate. Phase 4's pace is set more by the art (getting figures and rooms to read well) and by playtesting the office than by code. A realistic plan is **6–10 weeks**, with P4.0's month speed as the main unknown.

---

# 6. The Office Requirements

| Requirement | Source | Increment |
| --- | --- | --- |
| An isometric 3D office resembling a modern business office | PRD 6.1 | P4.1, P4.3 |
| Three floors with the departments and facilities listed | PRD 6.2; Doc 05, 5.2 | P4.1, P4.4–P4.6 |
| View from different angles; navigate between floors; enter departments | Doc 05, 5.1 | P4.1 |
| Employees, workstations, entrances, meeting rooms, racks, CEO desk, reception, notice boards, cafeteria, equipment | PRD 6.3 | P4.4–P4.6 |
| Selecting an object reveals information or actions; the server room shows utilisation, storage, availability and maintenance | PRD 6.3 | P4.4, P4.7 |
| Employees move, interact and respond to events, driven by state | PRD 5.3; Doc 05, 5.4 | P4.2, P4.3 |
| Never shows work the backend does not hold | Doc 05, 5.4 | P4.2 (as a test) |
| Inspect, assign or discuss tasks; schedule meetings | Doc 05, 5.3 | P4.7 |
| A startup's smaller office, expanding into floors | Doc 05, 5.2 | P4.8 |
| Mouse, touch and keyboard; context menus; application panels | Doc 05, 6.3 | P4.1, P4.7, P4.9 |
| Usable without the office; dashboard and menus always available | Doc 05, 6.3; Doc 06, 9 | Every increment |
| A performance budget for ordinary laptops | Doc 06, 9 | Section 4.1; P4.9 |
| **Criterion 2:** navigate the 3D office and interact with departments | PRD 25 | P4.9 (exit) |

---

# 7. Decisions for the Owner

1. **Approve the plan,** or reorder it.
2. **Month speed target.** Recommendation: the 3-minute allowance (8a in Document 09) for a full-size month with mobile loans, as now, in P4.0. The 2-minute target for worlds without mobile loans stays.
3. **Balance findings 9 and 10.** Recommendations:
   * **9, compliance costs nothing:** consent samples and access reviews take the compliance officer's time, as work items, so diligence competes with other work;
   * **10, the score's payback:** keep the development cost, and let a well-validated score win lenders faster, so a good score pays back within the first year.

   The other choice for each is to accept the finding as it is and say so in the Handbook.
4. **"Schedule a meeting" (P4.7).** Recommendation: the office starts and joins **the meetings the game already has** (the Data Quality Review, board reviews, sales meetings), with no new meeting system. A meeting system of its own (meetings that change morale, decisions or speed) would be new gameplay, better judged after the office is played.
5. **Art.** Recommendation: keep the brief's style, built entirely in code (boxes, cylinders, flat shading), with **no downloaded models or textures**. That keeps the download small, the licensing clean and the style consistent.
6. **The low-spec laptop.** Which machine stands for a school's slowest laptop? If the owner has access to one, its make and model; otherwise a stated profile (for example, integrated graphics, 8 GB of memory, a 1366×768 screen), with the dev laptop throttled to match.
7. **The office's place in the game.** Recommendation: the Office stays one screen in the menu, as today, and the dashboard stays the home screen. The player may set the Office as their home screen in the assistance settings.
8. **GitHub CI:** still open from Phase 3.
9. **A Startup's path to the building (P4.8).** Today a Startup can rent at most the standard office floor (45 desks). Recommendation: a third option, **the building**, at a rent and fit-out set from R14, so a Startup that grows can move into the three floors. The other choice is to leave a Startup on its one floor for Version 1.

---

# 8. Risks

| Risk | Mitigation |
| --- | --- |
| The office becomes a second source of truth, showing something the game does not hold | Locations computed from state, never stored apart from it (P4.2); the Document 05 rule as a property test |
| A change for the office's sake breaks replay | Only P4.2 and P4.7 touch the backend's behaviour; both carry replay tests; the rest is read-only |
| Art takes longer than code | A fixed, coded style (Section 7, item 5); figures of a few parts; an early playthrough on the first floor before the other two |
| Three floors break the budget | Measured at every increment; only the floor in view is drawn and refreshed; the P4.0 trim of three.js; the low-spec order of cuts |
| Ordinary school laptops struggle | Tested in P4.9 against a stated machine (Section 7, item 6); the 2D game is complete without the office |
| The office is pretty but not useful | P4.7 makes it a place to act, not only to watch; the P4.9 playthrough judges it under *Tedious* and *Confusing* |
| Month speed blocks a living office (people freeze while a month computes) | P4.0 first; the office shows the last state it has during a long advance, and says so |
| Accessibility is an afterthought | The text fallback and keyboard controls grow with every floor (P4.1), not at the end |

---

## DOCUMENT CONTROL

| Field | Value |
| --- | --- |
| Document ID | CBS-P4P-001 |
| Version | 0.1 |
| Status | Draft for owner review |
| Change history | 0.1 first draft after Phase 3 |
| Next step | Owner's review and decisions (Section 7); then P4.0 |
