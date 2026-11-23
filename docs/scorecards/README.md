# Scorecard study (P3.5)

`manage.py scorecard_study` builds every scorecard twice over the same 12 months of provider files:

- a **clean** bureau, loaded with the usual policies (the world's history template);
- a **careless** bureau, linking fuzzy matches automatically at a score of 0.6 and sending nothing to review.

It judges each scorecard on its holdout, both against the bureau's own labels and against the world's truth.

**Run (23 November 2026):** world 12 (seed 44, default size, with mobile loans); observed 30 June 2026; 6-month window; seed 20261123. Raw results are in `world12-seed44.json`.

## Against the world's truth (holdout AUC)

| Scorecard | Clean | Careless |
| --- | --- | --- |
| Short term | **0.832** | 0.821 |
| Mid term | **0.806** | 0.792 |
| Long term | **0.789** | 0.785 |
| All loans | **0.815** | 0.814 |

Clean data ranks the true risk better in every case, but only slightly: by 0.001 to 0.014. The careless setting made few extra false merges in this world; the number of defaults on file that were not the customer's was the same in both bureaus (27 among 6,638 customers on the all-loans scorecard). A harsher test of carelessness is still to come, for example wrong review decisions or a strict rejection policy losing whole records.

## Term scorecards against one all-loans scorecard (holdout AUC on each term's own customers)

| Term | Term scorecard (clean) | All-loans scorecard (clean) | Term (careless) | All-loans (careless) |
| --- | --- | --- | --- | --- |
| Short | **0.861** | 0.850 | **0.855** | 0.841 |
| Mid | **0.829** | 0.824 | **0.835** | 0.810 |
| Long | 0.836 | **0.837** | **0.843** | 0.839 |

The term scorecards win on their own customers, except long term in the clean bureau, which is level (0.001 behind). This holds once the short-term scorecard includes the borrower's arrears history (A-075): without it, short term scored 0.807 against 0.837.

## The composite (holdout AUC on everyone)

| | Clean | Careless |
| --- | --- | --- |
| Composite | **0.864** | **0.857** |
| Short-term scorecard alone | 0.861 | 0.854 |
| Mid-term scorecard alone | 0.842 | 0.843 |
| Long-term scorecard alone | 0.804 | 0.800 |
| One all-loans scorecard | 0.878 | 0.870 |

The composite beats each term scorecard on everyone, though only just against the short term. A single scorecard built on everyone beats the composite.

## What players should learn

- **The real defaults the bureau never saw are the biggest gap.** For the all-loans scorecard, 382 of the holdout's true defaults never appeared on file, mostly at lenders that do not report to the bureau. Wrongly merged files account for only 27. Coverage matters more than polish.
- **Arrears history predicts every term,** mobile loans included.
- **Splitting by term pays a little;** a composite of term scorecards pays less than one good scorecard on everyone, in this world.

## Open (for the owner)

- Whether segment scorecards should win more clearly. In real markets they do when the segments behave very differently; in this world, mobile and term borrowers share one hidden risk.
- A harsher careless bureau for the clean-against-careless comparison.
