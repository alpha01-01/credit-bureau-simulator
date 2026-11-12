# Assumptions Register

Every rule, value or format used in SimB that has **not** yet been confirmed from reference material (see [`references/`](references/README.md)) is listed here and marked `ASSUMPTION` where it appears in code or documents. When confirmed, record the source and close the entry.

| ID | Assumption | Where used | Needed reference | Status |
| --- | --- | --- | --- | --- |
| A-001 | Development PostgreSQL role, database and password in `.env.example` are local-only values | `.env.example`, `scripts/create_dev_db.sql` | — | Accepted (dev only) |
