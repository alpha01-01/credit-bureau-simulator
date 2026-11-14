# Reference Material

SimB mirrors real-world credit bureau practice (Document 07, D11). This folder holds the source material the game's rules are built from.

## Rules for this folder

1. **No real personal or customer data, ever.** Sample files must be fully synthetic or have every personal field replaced.
2. **Only share what you are permitted to share.** Internal documents from an employer or a lender may be confidential. Prefer public sources. Where internal knowledge is needed, write it up in your own words (e.g. "the template has these 40 fields, in this order, with these rules") instead of copying the document.
3. **Record provenance.** Add each item to the index below with its source, version or date, and whether it is public or owner-written.
4. Public legal texts can be committed. Anything uncertain stays out of Git (put it in `docs/references/private/`, which is ignored).

## What is needed, by priority

### Priority 1 — needed for the first playable slice

| # | Material | Used for | Status |
| --- | --- | --- | --- |
| R1 | **Data submission template(s)** for consumer and commercial credit data: field names, order, types, lengths, mandatory/optional, allowed values | Provider files, template validation, staging tables | **Received** (`templates.md`); simplified version approved (`template-simplification-proposal.md`). Types and lengths still needed |
| R2 | **Code lists**: account status, facility types, payment status, currency, identifier types, gender/marital codes, sector codes, regions | Validation rules, world generator | Needed |
| R3 | **Validation and rejection rules / error codes** a bureau applies (what makes a record unloadable, warning vs reject) | Pipeline, unloadable records, provider feedback reports | Needed |
| R4 | **Matching practice**: which identifiers and fields are used to link customers and accounts, and how uncertain matches are handled | Referencing engine, match-review work items | Needed |
| R5 | **Submission calendar and SLAs**: reporting deadlines, frequency, correction/resubmission practice | Month loop, provider lateness, SLA penalties | Needed |
| R6 | **Credit Reporting Act, 2007 (Act 726)** (and any amendments) | Handbook, regulator rules | Needed (public) |
| R7 | **Credit Reporting Regulations, 2020 (L.I. 2394)**, especially dispute resolution (Regs 23–26), consent, access, retention | Dispute workflow and deadlines, consent, retention | Needed (public) |
| R8 | **Pricing**: GHS prices for individual reports, business reports, batch enquiries; typical contract structures (pay-per-use, bundles, subscriptions) | Products, billing, demand model | Needed |

### Priority 2 — needed for Version 1

| # | Material | Used for | Status |
| --- | --- | --- | --- |
| R9 | **Credit report layout(s)** — sections and fields of individual and business reports (synthetic sample) | Report product, report QA work items | Needed |
| R10 | **Data Protection Act, 2012 (Act 843)** — relevant sections | Handbook, access control, compliance events | Needed (public) |
| R11 | **Bank of Ghana directives and notices** on credit reporting (e.g. data retention, participation of non-bank institutions, credit scoring) | Regulator rules, events | Needed (public) |
| R12 | **Consent and permissible-purpose practice**: how subscribers evidence consent; what purposes are allowed | Enquiry workflow | Needed |
| R13 | **Typical bureau organisation**: roles, headcount, salary bands (GHS) | Starting organisation, payroll | Needed |
| R14 | **Typical operating costs**: rent (Accra office), IT infrastructure, software licences | Finance, startup scenario | Needed |
| R15 | **Bank of Ghana credit reporting annual reports** (market statistics: enquiries, records, participants) | Calibrating world scale and demand | Public |
| R16 | **Scorecard practice**: score ranges, risk bands, typical variables | Analytics, scoring product | Needed |
| R18 | **Ghana taxes affecting the bureau**: VAT and levies on services (rates and how levies are treated), PAYE monthly bands, SSNIT rates and remittance dates | Finance: invoices, payroll, remittances | Needed (public) |
| R17 | **Ghana public holidays**: the current statutory list (Public Holidays and Commemorative Days Act, as amended), the weekend observance rule, and how Eid dates are announced | Working-day calendar, SLA days | Needed (public) |

## Index

| # | File | Source | Version / date | Public or owner-written |
| --- | --- | --- | --- | --- |
| R1 | `templates.md` | Owner: column lists of the six templates in use | November 2026 | Owner-supplied |
| R1 | `template-simplification-proposal.md` | Written for this project; approved by the owner | 14 November 2026 | Owner-written |
