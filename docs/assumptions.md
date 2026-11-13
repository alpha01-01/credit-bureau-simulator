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
