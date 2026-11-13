# Assumptions Register

Every rule, value or format used in SimB that has **not** yet been confirmed from reference material (see [`references/`](references/README.md)) is listed here and marked `ASSUMPTION` where it appears in code or documents. When confirmed, record the source and close the entry.

| ID | Assumption | Where used | Needed reference | Status |
| --- | --- | --- | --- | --- |
| A-001 | Development PostgreSQL role, database and password in `.env.example` are local-only values | `.env.example`, `scripts/create_dev_db.sql` | — | Accepted (dev only) |
| A-002 | Ghana Card number format `GHA-#########-#` with a Luhn mod-10 check digit | `apps/world/generation/identity.py` | R2 | Open |
| A-003 | Mobile numbers: 10 digits, network prefixes 024/054/055/059/053 (MTN), 020/050 (Telecel), 027/057/026/056 (AT), with rough market shares | `identity.py` | R1, R2 | Open |
| A-004 | Regional population shares across the 16 regions; main towns per region | `config.py` (`REGIONS`, `REGION_TOWNS`) | R15 / census | Open |
| A-005 | Employment mix, median monthly incomes (GHS), income spread and stability by employment type | `config.py` (`EMPLOYMENT_TYPES`) | R13 / statistics | Open |
| A-006 | Product terms, annual interest rates, loan sizes and affordability (debt-service) limits | `config.py` (`PRODUCTS`) | R8, R15 | Open |
| A-007 | Twelve fictional lenders: types, book shares, product mixes, approval strictness, write-off thresholds (90–360 DPD), footprints | `config.py` (`LENDERS`) | R15 | Open |
| A-008 | Business registration number `CS#########` and company TIN `C000#######` formats | `population.py` | R1, R2 | Open |
| A-009 | Repayment behaviour calibration: 12-month default rate (90+ DPD) of roughly 8–10% at default scale, ordered mortgages < auto < digital/personal < business < microfinance; economic stress as an AR(1) index | `config.py` (`BehaviourModel`, `EconomyModel`) | R15 | Open |
| A-010 | Days past due = reporting date − oldest unpaid due date (an instalment due on the reporting date itself is in arrears at 0 DPD); outstanding balance = scheduled principal + unpaid interest on missed instalments, no penalty interest | `engine.py` | R1, R3 | Open |
| A-011 | Lender customer numbers (prefix + 8 digits) and account numbers (prefix + digits, 14 characters) | `persist.py` | R1 | Open |
| A-012 | Submission template SIMB-T0: one flat file per borrower type (individual `IND`, commercial `COM`) per provider per month, one row per facility with borrower details repeated; field list, mandatory flags; UTF-8 CSV with header; dates DD/MM/YYYY; amounts with two decimals, no separators; file name `{PROVIDER}_{IND|COM}_{YYYYMM}` | `apps/standards/submission_template.py` | R1 | Open |
| A-013 | Code lists: facility type (TL, MG, AF, ML), account status (AC, PD, ES, WO), currency, repayment frequency, gender, employment type, sector, region | `submission_template.py` (`CODE_LISTS`) | R2 | Open |
| A-014 | Monthly data is due by the 10th of the following month | `submission_template.py` (`SUBMISSION_DUE_DAY`) | R5, R6, R7 | Open |
| A-015 | Bank of Ghana prudential classification by days past due: Current 0–29, OLEM 30–89, Substandard 90–179, Doubtful 180–359, Loss 360+ | `submission_template.py` (`asset_classification`) | R2, R15 | Open |
| A-016 | Data Quality Profiles: defect types and rates (GOOD, AVERAGE, POOR, DIGITAL), which provider has which profile, arrival days and lateness | `apps/world/provider_files/profiles.py` | R3, R15 | Open |
| A-017 | Pipeline validation rules, rule codes (T, F, D, R, L, C series) and severities; strict formats with one cleansing rule (C001 phone normalisation); whole-file rejection when columns do not match the template | `apps/bureau/quality/rules.py` | R3 | Open |
| A-018 | Customer referencing order: provider customer number, then Ghana Card (individuals) or registration number then TIN (businesses), else a new customer; on conflict the provider's own keys win and a warning is kept | `apps/bureau/referencing/matching.py` | R4 | Open |
| A-019 | Ghana public holidays: fixed dates (1 Jan, 7 Jan, 6 Mar, 1 May, 1 Jul, 4 Aug, 21 Sep, 25 Dec, 26 Dec), Good Friday, Easter Monday, Eid al-Fitr and Eid al-Adha (expected dates 2023–2030), Farmers' Day (first Friday in December); fixed-date holidays on a weekend observed on the next working day | `apps/standards/calendar.py` | R17 | Open |
| A-020 | Game time: working day 08:00–17:00 in 15-minute ticks; provider files arrive at a seeded time on their arrival day (next working day if it falls on a weekend or holiday); received submissions are processed in an overnight batch at 17:00 | `apps/simulation/clock.py`, `engine.py` | R5 | Open |
