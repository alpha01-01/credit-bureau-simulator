# Credit data formats: notes from the industry standard

**Source:** Credit Reference Bureau Data Standards Committee (Bank of Ghana, licensed bureaus and selected financial institutions), *Data Format* manuals, version 1.1, July 2012, supplied by the owner on 14 November 2026:

| Manual | File identifier | Pages |
| --- | --- | --- |
| Consumer Credit Data Format | `CONC` | 97 |
| Business Credit Data Format | `BUSC` | 81 |
| Consumer Dishonoured Cheque Data Format | `COND` | 55 |
| Consumer Judgment Data Format | `CONJ` | 55 |

The manuals themselves are not stored in this repository. These notes summarise what the game needs from them, in our own words, plus the owner's rules of practice. A scanned *cleaning rules* document was also supplied; it is images only and has not been read yet.

These notes cover reference items **R1** (templates), **R2** (code lists), **R3** (rejection rules) and part of **R5** (resubmission deadlines).

---

## 1. Files

| Rule | Standard |
| --- | --- |
| File name | `SRN-ReportingDate-DateCreated-Version-FileIdentifier-SequenceNumber.csv`, e.g. `10118-20120130-20120205-1.1-CONC-12.csv` |
| SRN | **Supplier Reference Number**: the reporting institution's number, assigned by the Bank of Ghana (5 characters) |
| Reporting date | The "as at" date of the data, `YYYYMMDD` |
| Date created | When the file was extracted from the provider's system, `YYYYMMDD` |
| Version | Version of the template (`1.1`) |
| Sequence number | 1, 2, 3… for each submission of the same format within a reporting period |
| Format | CSV with a **pipe** (`|`) delimiter; not compressed, not password-protected |
| Header | First line; every column present, named and ordered exactly as defined; no extra or empty columns |
| Rows | No empty rows; no summary rows at the bottom |
| Dates | `YYYYMMDD` |
| Money | Whole numbers only: no separators, no decimals, rounded to the nearest unit |
| Joint accounts | One record per borrower, with the same financial data on each |
| Account number changes | Bureaus must be told in advance |

## 2. Rejection

**A file is rejected when** its name breaks the convention, it is not pipe-delimited CSV, columns are missing, renamed, reordered or extra, the first row is not the header, or there are empty rows.

**A record is rejected when** a value has the wrong type; a mandatory or applicable conditional field is missing; a value is not in its code list; or the record breaks financial logic. The standard's examples:
* closed by "early settlement" but a balance is still outstanding;
* a salary loan with no employer details;
* a secured loan with no collateral details.

**Field options:**

| Option | Meaning |
| --- | --- |
| Mandatory | Must be supplied, or the record is rejected |
| Required conditional | Mandatory when a stated condition holds (e.g. closure reason when the account is closed) |
| If available | Optional, but the column must still be present |

**Resubmission (R5):** the bureau tells the provider (and the Bank of Ghana) about rejected files or records, with reasons, within **2 working days** of receipt. The provider resubmits financial data within **2 working days** of the rejection, and non-financial data (addresses, guarantors) within **5 working days**.

## 3. The owner's rules of practice

| Rule | Detail |
| --- | --- |
| Correction indicator | `0` normal monthly submission; `1` correction or replacement of the most recently reported record for the same reporting date; `2` deletion. A deletion also needs an email to the bureau giving the reason. |
| Valid ID | Mandatory for records from **1 January 2020** |
| Duplicates | When two records are the same, the **lower balance is kept**. This is enforced strictly. If the higher balance should have been kept (because there were defaults rather than payments), the provider raises it through the dispute or customer service department. |
| Disputes | Expect many: they are a major part of the customer service and dispute roles |
| Paypoint | Where the client receives their income |

## 4. Code lists (R2)

### Shared

| List | Codes |
| --- | --- |
| Correction indicator | `0` normal, `1` correction/replacement, `2` delete |
| Gender | `M`, `F` |
| Marital status | `S` single, `M` married, `D` divorced, `W` widowed, `P` separated |
| Other ID type | `STAFF`, `STUD` student, `SERV` service, `NHIS` health insurance |
| Proof of address | water bill, electricity bill (`WAT`/`ELE` in the credit format; `WATER`/`ELECT` in the cheque and judgment formats) |
| Owner or tenant | `O` owner, `T` tenant, `F` family owned |
| Employment type | `101` salaried, `102` unemployed, `103` student, `104` self-employed, `105` home maker, `106` pensioner |
| Joint or sole | `J`, `S` |
| Nationality, country | ISO 3166 alpha-3 (e.g. `GHA`) |
| Currency | ISO 4217 (e.g. `GHS`, `USD`, `EUR`, `GBP`) |

### Credit (consumer and business)

| List | Codes |
| --- | --- |
| Credit facility type | `101` agriculture, `102` auto loan, `103` bank guarantee, `104` bills discounted, `105` corporate credit card (business), `106` credit card (consumer), `107` education loan, `108` hire purchase, `109` housing loan, `110` leasing, `111` letter of credit, `112` loan against bank deposit, `113` against provident fund, `114` against life insurance, `115` salary/payroll loan, `116` against shares and securities, `117` loan to professional, `118` mortgage, `119` non-secured loan, `120` other secured loan, `121` overdraft, `122` personal loan, `123` pledge loan, `124` property loan, `125` government loan, `126` term loan, `127` travel finance, `128` student loan, `129` others. The business list is a subset. |
| Purpose of facility | `A` crisis, `B` home, `S` study (consumer), `C` other asset acquisition, `D` project, `E` capital, `F` equipment and machinery, `G` working capital, `H` subscription, `P` personal (consumer), `J` trading in securities, `K` consolidation, `L` other |
| Repayment frequency | `10` weekly, `11` bi-monthly, `12` monthly, `13` quarterly, `14` tri-annually, `15` semi-annually, `16` annual, `17` variable, `18` bullet, `19` demand (revolving), `20` unspecified, `21` balloon |
| Asset classification | `A` current (1–30 days), `B` 31–90, `C` 91–180, `D` 181–360, `E` over 360 |
| Facility status | `A` open/active, `C` closed (fully paid), `D` disputed (payment profile hidden until changed), `E` terms extended, `L` handed over/legal, `N` loan against policy, `P` paid up (may become active again), `T` early settlement, `G` charge-off, `Z` deceased, `R` restructured/rescheduled, `B` approved but not disbursed, `W` written off |
| Reason for closure | `A` by the lender without prejudice, `B` balance transfer, `C` death (consumer), `D` end of tenure, `E` merger of facilities, `F` early settlement, `G` court order, `H` lost or compromised cards, `J` bankruptcy, `K` restructured |
| Reason for write-off | `A` part settlement, `B` death, `C` unable to locate, `D` government concession, `E` bankruptcy, `F` other |
| Reason for restructure | `T` top-up request, `E` irregular repayments, `L` loss of job, `D` business downturn, `F` force majeure, `C` other |
| Current balance indicator | `D` debit, `C` credit (credit balances are not added to report summaries; a zero balance is `D`) |
| Legal flag | `101` no, `102` yes (dispute or litigation on the facility) |
| Collateral indicator | `101` yes, `102` no |
| Nature of charge | `A` fixed, `B` floating |
| Type of security | `A` land, `B` shares, `C` government securities, `D` building, `E` cash/fixed deposit, `F` bank guarantee, `G` salary assignment, `H` terminal benefits, `J` bullion, `K` plant and machinery (consumer), `L` vehicles, `M` corporate guarantee, `N` individual guarantee, `P` government guarantee, `Q` others |
| Special comments | `101` paid by co-maker, `102` assumed by another party, `103` closed at lender's request, `104` transferred to another lender, `105` adjustment pending, `106` partial payment agreement, `107` purchased by another lender, `108` payroll deduction (consumer), `109` credit line suspended, `110` closed due to refinance, `111` closed due to transfer, `112` paid in full for less than the balance, `113` first payment never received, `114` paid from collateral, `115` interest only |
| Nature of guarantor | `101` individual, `102` commercial entity, `103` no guarantor (consumer); business adds `103` individual relationship (proprietor, partner, director) |
| Payment history profile | `0` current (1–30 days), `1` 31–60, `2` 61–90, `3` 91–120, `4` 121–180, `5` over 180 |

### Business only

| List | Codes |
| --- | --- |
| Business type | `A` sole proprietorship, `B` limited partnership, `C` company limited by shares, `D` limited by guarantee, `E` unlimited company, `F` cooperative, `G` foreign/external company, `H` consultancy or professional body, `J` social organisation, `K` international organisation, `L` NGO |
| Sector and sub-sector | `10` agriculture, forestry and fishing (`101`–`107`); `20` mining and quarrying (`201`–`206`); `30` manufacturing (`301`–`309`); `40` construction (`401`–`402`); `50` electricity, gas and water (`501`–`503`); `60` commerce and finance (`601`–`609`); `70` transport, storage and communication (`701`–`706`); `80` services (`801`–`806`) |

### Dishonoured cheques and judgments

| List | Codes |
| --- | --- |
| Reason cheque returned | `11` insufficient funds, `12` fraud |
| Case type | `A` admin order, `C` court order, `J` judgment by default, `S` sequestration, `M` judicial management, `L` liquidation |
| Case reason | `F` fraud, `R` debt recovery, `O` other |
| Court type | free text (e.g. regional, high) |

## 5. Conditional rules worth building

* **Identity (consumer):** at least one of national ID, voter's ID, driver's licence or passport. (Owner: a valid ID is mandatory from 2020.)
* **Other ID number** is required when an other-ID type is given.
* **Closed accounts:** when the status is closed, the current balance and amount in arrears must be zero, and a closure reason is required.
* **Written off:** the written-off amount and reason are required; the amount must also appear in the balance and amount overdue.
* **Restructured:** the date and reason are required.
* **Collateral:** if collateralised (`101`), the security type, nature of charge, value and registry reference are required.
* **Guarantor:** a commercial guarantor (`102`) needs its name and registration number; an individual guarantor needs name, ID, gender and date of birth.
* **Employer:** a salary or payroll loan needs employer details.
* **Instalment, last and next payment** are required where the facility has scheduled repayments.
* **NDIA** is the number of days from the arrears start date to the reporting date, capped at `999`; `0` when not in arrears.

## 6. Still needed

| Item | Why |
| --- | --- |
| Business dishonoured cheque and business judgment formats | Only the consumer versions were supplied; the cleanser has business versions of both |
| The scanned cleaning rules in text form, or confirmation they match `private/CLEANSER_RULES.md` | It could not be read |
| Field 12 of the business format (registration date) | Not readable in the extracted text |
| Whether the 2012 v1.1 manuals are still current | Templates change (D19); the game should start from the version in force |
