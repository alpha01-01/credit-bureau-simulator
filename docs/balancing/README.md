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
