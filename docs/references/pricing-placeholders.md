# R8 pricing: placeholders (23 November 2026)

**Status:** placeholders accepted by the owner (23 November 2026), to be adjusted as needed. They are not real price lists. Every value below is an ASSUMPTION in code until replaced.

## What was found

A search of public sources (23 November 2026) found **no published bureau prices** in Ghana. What it did find, used to shape the list below:

* **The product range.** A Ghanaian bureau's public posts (March 2023) list a consumer trace report, a basic consumer credit report, a detailed consumer credit report, a detailed business report and a **mobile loan report**. No prices were given.
* **A free report each year.** Individuals may get their own credit report free once a year. Bank of Ghana statements say so and L.I. 2394 is described that way; check against R7.
* **Volumes.** Banks made 22.36 million enquiries in 2025, almost all of them on one bureau (Bank of Ghana, *Credit Reporting Activity Annual Report 2025*). Enquiries grew fast with digital lending.
* **Credit scores.** In 2023 the main bureau stated publicly that it did not produce credit scores in Ghana. A score is therefore a new product in the game's market (P3.6).

## Placeholder price list (GHS, excluding VAT and levies)

The game's existing price of GHS 15 for a detailed consumer report (A-028) is kept, because the P2.12 balancing was tuned on it. The other prices are set relative to it. Mobile-loan decisions are small and frequent, so their report must be cheap or lenders will not check (the demand model already responds to price).

| Product | Unit | Price | Notes |
| --- | --- | --- | --- |
| Consumer trace report | per report | 5 | Identity and contact details only, for tracing and verification |
| Basic consumer credit report | per report | 10 | Summary of accounts and arrears, no payment history |
| Detailed consumer credit report | per report | 15 | The current report (A-028) |
| Mobile loan report | per report | 2 | Short report for loans up to 3 months (P3.3) |
| Credit score, with a report | per score | 5 | Composite score, band and reason codes (P3.6) |
| Credit score, alone | per score | 6 | For high-volume mobile lending |
| Detailed business report | per report | 60 | Business facilities, dud cheques, judgements (P3.11) |
| Batch enquiry | per record | the product's price, less volume discount | P3.11 |
| Own report (individual) | per report | first each year free; then 20 | Check against L.I. 2394 (R7) |

## Contract structures

| Structure | Terms (placeholder) |
| --- | --- |
| **Pay per use** (default) | List price for every unit, billed monthly in arrears |
| **Volume discount** | 10% off units above 10,000 in a month; 20% above 50,000 |
| **Prepaid bundle** | 1,000 detailed reports for GHS 13,200 (12% off), used within 6 months |
| **Subscription** | A monthly minimum of GHS 5,000, which covers 400 detailed reports; further units at 10% off |
| **Term** | One year, renewable (as now, A-063) |

## To confirm with real material

* Actual price levels, and whether banks, microfinance lenders and fintechs pay different rates.
* Whether mobile lenders pay per enquiry or a flat monthly fee.
* The charge, if any, for an individual's second and later reports in a year.
