# Balancing runs (P2.12)

Headless runs of scripted strategies, made with:

```
python manage.py balance --size small --seeds 81 82 83 --months 6 --out ../docs/balancing/runs-small-after.jsonl
python manage.py balance --size default --seeds 43 --months 6 --out ../docs/balancing/runs-default-after.jsonl
```

Each line of a `.jsonl` file is one run: the strategy, the world and every outcome
(`apps/simulation/balancing.py`, `outcomes`). The strategies are defined in the
same file:

| Strategy | What it does |
| --- | --- |
| `strict_quality` | Rejects on any field failure; advanced fuzzy matching with a wide review band (0.97 / 0.75); hires a senior officer; trains every provider and sends every feedback report, every month |
| `fast_coverage` | Rejects only on core fields; relaxes every relaxable check; links readily (0.80 / 0.78); no extra staff, no provider work |
| `cheap_staffing` | Keeps the starting policies; pays everyone the bottom of their band |

All three send the same two proposals in the first month (the two largest lenders
that do not subscribe, at list price), so their differences come from how they
run the data.

## Files

| File | Health formula | What it shows |
| --- | --- | --- |
| `runs-small-before.jsonl` | P2.10 | Three small worlds, six months |
| `runs-default-before.jsonl` | P2.10 | The default world (seed 43), six months |
| `runs-small-after.jsonl` | P2.12 (A-070) | The same small worlds |
| `runs-default-after.jsonl` | P2.12 (A-070) | The same default world |

The games are identical before and after; only the Health score (and so the
board's confidence) changed.

## Default world, six months

| | Strict quality | Fast coverage | Cheap staffing |
| --- | --- | --- | --- |
| Revenue (GHS) | 762,615 | 662,505 | 766,530 |
| Net profit (GHS) | -79,599 | +111,447 | +270,930 |
| False merges (true) | 0.16% | 5.5% | 0.02% |
| Reports on the wrong person | 0.31% | 6.6% | 0.04% |
| Accuracy (true) | 99.79% | 99.30% | 99.39% |
| Disputes | 182 | 1,603 | 154 |
| Health before (P2.10) | 88.5 | 88.3 | 90.1 |
| Health after (A-070) | 87.7 | 81.7 | 90.0 |
| Data quality score after | 88.4 | 64.8 | 90.8 |

## Findings

1. **The economy works at the default size, not at the small one.** A bureau in
   the default world becomes profitable once the two digital lenders sign. In a
   small world (2,000 people) revenue cannot cover an Accra office, so every
   strategy loses money; small worlds serve the tests, which compare strategies
   with each other.
2. **The demand model works.** Fast coverage's wrong-person reports cost it 13% of
   its revenue as lenders lost faith in the bureau.
3. **The Health score could not see quality** (fixed, A-070). Data quality scored
   accuracy linearly, so 99.3% and 99.8% looked the same; a bureau with 1,603
   disputes scored like one with 182. It now uses an error-sensitive scale and
   upheld disputes per 1,000 reports.
4. **Strict quality against fast coverage: neither dominates** (the done-when).
   Strict has the better data and the better health on every small seed and on
   the default world; fast has the better result. Tested in
   `tests/simulation/test_balancing.py`.
5. **Open: keeping the starting policies beats strict quality within six months
   on the default world**, on both result and health. Two reasons:
   * advanced fuzzy matching at 0.97 links some people who share a name and date
     of birth (0.16% false merges against 0.02% for identifiers only): in this
     world nearly everyone carries a Ghana Card, so fuzzy matching adds risk more
     than coverage;
   * the monthly audit samples 100 accounts, too few to see strict's better
     accuracy (99.79% against 99.39% true), so the Health score cannot reward it.

   A rule that a fuzzy match may never join two different Ghana Card numbers was
   tried and reverted: it removed false merges altogether, and with them the
   merge-against-split trade-off that P2.4 built and mission M3 teaches. Options
   for the owner: a larger audit sample, a cheaper provider-training effect that
   shows within months, or treating a conflicting identifier as strong evidence
   against a match (a review, never an automatic link) rather than a veto.
6. **Provider training is the most expensive part of strict quality** (five
   providers, GHS 5,000 each, every month). Its benefit (cleaner files) is real
   but slow and, at the current audit size, invisible.

# Phase 3 runs (P3.15)

The runs were widened to the levers Phase 3 added. Each pair differs from `steady`
(the starting policies, the same sale as above) in one lever only
(`apps/simulation/balancing.py`). Every P3.15 run is played, as a new game in the
app would be, in a current world (mobile loans) with the economy its difficulty asks
for; `--legacy-worlds` replays P2.12's runs in their original worlds.

```
python manage.py balance --size small --seeds 81 --months 6 --history 12 --strategies steady score_careful score_careless compliance_diligent compliance_lax price_high price_low --out ../docs/balancing/runs-p3-levers.jsonl
python manage.py balance --size small --seeds 82 --months 6 --scenario STARTUP --difficulty BEGINNER EXPERT --strategies steady strict_quality --out ../docs/balancing/runs-p3-startup.jsonl
python manage.py balance --size small --seeds 83 --months 6 --history 6 --scenario SANDBOX --difficulty BEGINNER EXPERT --sandbox '{"provider_quality": 2, "starting_cash": 3000000}' --strategies steady fast_coverage --out ../docs/balancing/runs-p3-sandbox.jsonl
```

| Strategy | The lever |
| --- | --- |
| `steady` | None: the base |
| `score_careful` | Develops the score product; a scorecard per term on its recommended features, on the longest window the data allows, then the composite |
| `score_careless` | Develops the score product; one long-term scorecard on a single weak feature (facilities ever) |
| `compliance_diligent` | A consent sample of 50 from every subscriber each month; a warning for each found short, and the access review, as soon as each is due; retention at the legal 5 years |
| `compliance_lax` | Retention at 7 years; nothing else |
| `price_high`, `price_low` | The sale at 130% and 75% of the list price (GHS 19.50 and 11.25) |

## The levers (small world, seed 81, 12 months of history, six months, Intermediate)

| | Revenue (GHS) | Net profit | Reports sold | Price a report | Scores sold (AUC) | Subscribers | Findings to the regulator | Health |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| steady | 41,107 | -548,574 | 2,455 | 15.00 | 0 | 5 | 2 | 75.9 |
| score_careful | 44,272 | -665,409 | 2,455 | 15.00 | 636 (0.82) | 5 | 2 | 75.9 |
| score_careless | 41,107 | -668,574 | 2,455 | 15.00 | 0 (0.38) | 5 | 2 | 75.9 |
| compliance_diligent | 41,107 | -548,574 | 2,455 | 15.00 | 0 | 5 | 0 | 82.5 |
| compliance_lax | 41,107 | -548,574 | 2,455 | 15.00 | 0 | 5 | 2 | 75.9 |
| price_high | 27,622 | -562,060 | 1,342 | 16.12 | 0 | 4 | 2 | 73.6 |
| price_low | 34,511 | -555,170 | 2,551 | 13.50 | 0 | 5 | 2 | 74.3 |

## Startup and Sandbox at two difficulties (six months)

| | Beginner | Expert |
| --- | --- | --- |
| Startup, `steady` (seed 82): bank at the end | 1,861,355 | 676,384 |
| Startup, `steady`: net profit | -558,943 | -719,690 |
| Startup, `strict_quality`: bank / net profit | 1,650,630 / -769,418 | 433,492 / -962,103 |
| Startup: reports sold (`steady`) | 1,755 | 1,580 |
| Sandbox (seed 83, quality +2, GHS 3,000,000), `steady`: net profit | -523,059 | -577,632 |
| Sandbox, `fast_coverage`: net profit | -563,995 | -633,360 |

Every Startup reached paying subscribers (two in six months) and every game ran
six months without an error or a failure ending.

## Findings (P3.15)

7. **Each new lever moves what it should** (`tests/simulation/test_levers.py`). A
   careful scorecard predicts the true defaults (AUC 0.82) and lenders buy it with
   636 reports; a careless one predicts worse than chance (0.38) and none buy it.
   Diligent compliance finds subscribers enquiring without consent, warns them (their
   share of such enquiries falls, 2.16% against 2.61%), settles the access review in
   time, and no finding reaches the regulator. A higher price earns more a report and
   loses a subscriber; a lower one sells 4% more reports at 25% less.
8. **Difficulty works in every scenario.** The same strategy ends with more cash and
   a smaller loss at Beginner than at Expert, in a Startup and in a Sandbox whose
   starting cash is the same at both (there, from supplier prices alone).
9. **Decided (P4.0, A-088): diligent compliance costs nothing.** It dominates laxity: the same money,
   better health. A consent check and a warning take none of Compliance's time and
   no subscriber minds them. Options for the owner: a consent check as a work item for
   Compliance (time a team must find), a warned subscriber's goodwill falling a little,
   or both. A retention period beyond the law (7 years) brought no breach in six
   months of a small world, whose history is a year long; the default world's three
   years of history should show it (not yet run).
10. **Decided (P4.0, A-089): the score does not pay for itself within six months of a small world**
    (GHS 3,165 of score sales against GHS 120,000 to develop it). On the default
    world, with about ten times the enquiries, it would take roughly two years at
    this uptake; the development cost or the score's price may want tuning (R8
    placeholders) once played.
11. **The list price is the best of the three on a small world**: lenders' demand
    hardly moves with price (4% more reports at 25% less), and above list a lender
    declines or counters. Pricing matters most in negotiation (P3.9), less in the
    level.
12. **Every scenario loses money on a small world** (finding 1 still holds): 2,000
    people cannot pay for an Accra office. The default world is where profit is
    possible; the full-size performance run (below) plays it.

## P4.0: month speed and findings 9 and 10

**Month speed** (`manage.py perf --months 1`, default world seed 44, 12 months of history,
run back to back on 26 November 2026 on the code before and after P4.0, each from a
fresh game after a `VACUUM ANALYZE`):

| | Setup | First month | Revenue | Reports | Health |
| --- | --- | --- | --- | --- | --- |
| Before P4.0 | 354 s | 341 s | GHS 50,880 | 2,919 | 83.2 |
| After P4.0 | 250 s | 247 s | GHS 50,880 | 2,919 | 83.2 |

The month is 28% faster, with the same outcomes (`perf-p4.0-before.json`,
`perf-p4.0-after.json`). The machine was slower that day than when P3.15 measured 252 s
(setup took 354 s against 240 s), so on P3.15's footing the month would take about
252 x 247 / 341 = 183 s. Where it went: a loan application went from about 20 queries
to 10 (the tick's lookups made once, its usage and judgements written once, the
borrower and the consequence trace in one query each, cheques and judgments looked up
only for customers that have any), 34.8 ms to 23.7 ms each on the same 500 applications,
with byte-identical reports, judgements, usage and subscriber views; and the missions
are no longer checked each tick while their questions wait for an answer.

**Finding 9** (A-088): Compliance's officer now gives each working day to one task; a
day spent reading consent forms or reviewing access holds the checks on new
subscribers back a day. **Finding 10** (A-089): a score's uptake rises faster the better
it is; on the default world the score sells with some 4,800 reports a month, so the
"two years" estimate above was a small world's.


**Score payback** (`runs-p4.0-score.jsonl`, `score_careful`, default world seed 44, 12
months of history, 11.4 months played): 27,386 scores sold, which at GHS 5 a score is
GHS 136,930 against the GHS 120,000 development cost, so the validated score now pays
for itself within the year. Its AUC was 0.78. The 5 access-review findings come from
the strategy, which never reviews access; P3.15's shorter run showed 3 of the same.
