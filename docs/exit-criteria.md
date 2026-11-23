# First playable slice: exit criteria (Document 07, Section 13.2)

Where each criterion stands at the end of Phase 2 (P2.13, 16 November 2026), and
the evidence. A criterion is **met** when its evidence is a passing test or a
recorded result; **open** when it needs people or the owner.

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A new player completes M1–M6 without outside help in about two hours | **Open: needs a playtest with people** | A scripted player completes M1–M6 from what the screens show, in 23 working days of game time, about 70 minutes at 1x before reading time (`tests/simulation/test_learning.py`). Claude played M1 in the browser (below). |
| 2 | Three months of play run without errors or inconsistencies | Met | `tests/simulation/test_exit_criteria.py`: after three months every journal balances, the trial balance and balance sheet balance, every processing run reconciles, every tick ran once in order, nothing due is left pending, every decided item's decision is on its case. The balancing runs played 30 games of six months (three on the default world) without an error (`docs/balancing`). |
| 3 | Two clearly different strategies lead to measurably different outcomes, neither dominating | Met, with one open finding | `tests/simulation/test_balancing.py`; `docs/balancing/README.md`. Open: keeping the starting policies beats strict quality within six months on the default world (options listed for the owner). |
| 4 | Every dashboard figure drills down to underlying records | Met | `tests/simulation/test_exit_criteria.py` follows all ten dashboard figures through the API and checks that the records behind each add up to it. Two drills were fixed in P2.13: "Work items" now counts what its drill shows, and "Open accounts" drills to a new accounts list rather than to customers. Lists say how many records there are in all ("Showing the first 200 of 1,611"). |
| 5 | A replay test reproduces a full game month exactly from seed plus action log | Met (the intermittent failure was the fingerprint's, found and fixed in P3.0) | `tests/simulation/test_clock.py::test_replaying_the_action_log_reproduces_the_game_exactly`; replays in the P2.6–P2.11 tests cover every player action added since. It had differed in about one full-suite run in ten (four times, never alone); see below. |
| 6 | Every posted journal balances; statements derive only from posted entries | Met | `tests/finance/test_finance.py` (`test_only_balanced_entries_are_posted`, `test_statements_come_from_posted_entries_and_balance`); checked again after three months of play in `test_exit_criteria.py`. |
| 7 | The bureau modules never read the world layer | Met | import-linter contracts in `backend/pyproject.toml`, run by `scripts/check.py` (5 contracts kept). |
| 8 | The project team has played it end to end at least three times with different strategies, and recorded its findings | **Open: needs the owner** | Claude's scripted playthroughs of three strategies (`docs/balancing`) and its browser playthrough (below) are recorded. Three end-to-end playthroughs by the team, with the Phase 1 playtest protocol (branch `docs/phase-1-playtest`, PR #12, not yet merged), remain. |

## The intermittent replay mismatch (found and fixed in P3.0)

**Cause (23 November 2026):** the fingerprint, not the game. A field changed twice in one staging record (cleansed, then corrected by a reviewer) has two transformation-log rows with the same sort key, so the fingerprint read them in whichever order PostgreSQL returned them, which depends on where rows lie on disk after a long run. The per-section fingerprint named the section on the next failure (`transformations`: same 106 rows, different digest). Ties are now broken by the order the changes were made. What had been ruled out before:

The replay test has failed three times in about thirty runs of the whole suite,
and never on its own. What has been ruled out (P2.13):

* database ids: a replay with every id sequence pushed far ahead matches;
* query plans: replays with sequential scans, hash joins and hash aggregation
  turned off, or index and bitmap scans and merge joins turned off, match;
* the real clock: nothing in the game reads it (the pipeline's fallback is
  always overridden by game time);
* randomness: every random draw comes from a named stream of the world's seed;
  the per-game organisation code is random but nothing reads it;
* the two process-wide caches keyed by database ids (`_customer_borrower`,
  `_reported_borrowers`): their answers cannot change once given.

The fingerprint now keeps a digest per section, and the test names the
sections that differ when it fails (`fingerprint.differences`). The next failure
will say where the two games part ways.

## Performance (P2.13)

On a default-world game six months in (game 27), every screen's API answered in
under half a second; the slowest were the dashboard (445 ms), the game header
(332 ms), the briefing (307 ms) and open accounts (303 ms). A month of play
takes about 4.5 minutes to compute on the default world with five subscribers
(it was about 2 minutes in P2.1 with three); at 1x a game month is about an
hour of real time, so the clock never waits on the engine, but "Next event"
across a month-end takes noticeable seconds.

## Claude's browser playthrough (16 November 2026)

A new game on a small world with three months of history, played in the
browser from the Games page to the end of M1.

What worked: the game prepared in about 20 seconds; the Briefing pointed to the
first mission; the first file arrived and was processed overnight; the mission's
question was answered from the submission page (389 received = 388 loaded + 1
unloadable reconciles); a wrong answer got a gentle note; the right answer
completed M1 and showed its debrief at once; the dashboard's "Open accounts"
drilled to the accounts; the skip link is the first thing the keyboard reaches.

Found and fixed:

* A game whose setup failed showed a raw Python error with a file path on the
  Games page. It now says the history could not be prepared and to start
  another game; the details go to the server log.
* On a narrow window the sticky header (22 links on four rows) covered much of
  the screen and hid the mission's answer box. It is sticky only on wide screens
  now.
* The "Not quite" note says to look at the screen the question names, but M1's
  and M4's questions named none. They now say "(Submissions)".
* While a game prepared, the browser tab still said "Your games". It now names
  the game being prepared.

Found, not fixed (for P2.13 follow-up or the owner):

* Account lists show facility types and statuses as codes ("122", "A"), not
  words.
* M2 asks for three unloadable records to decide; in a small world they are
  rare, so the mission can wait some days for them.
