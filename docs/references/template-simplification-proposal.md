# Proposal: simplified submission templates

**Status:** Approved by the owner on 14 November 2026 (Document 07, D18–D20). The game does not use it yet; it is built in increment P2.0 (Document 08).
**Sources:** [`templates.md`](templates.md) (the six column lists) and [`CLEANSER_RULES.md`](CLEANSER_RULES.md) (how the cleanser treats each column).

## 1. What we have today

| Template | Columns | Of which guarantor columns |
| --- | --- | --- |
| Individual credit | 178 | 67 |
| Business credit | 158 | 76 |
| Individual dud cheque | 74 | 0 |
| Business dud cheque | 46 | 0 |
| Individual judgement | 76 | 0 |
| Business judgement | 48 | 0 |

## 2. How I decided what to keep

1. **Keep every field the cleanser's CLEAN gate requires.** A record cannot be CLEAN without these, so they are the true mandatory set:
   * Individual: account number, customer ID, a usable ID, surname, first name, date of birth, facility amount, disbursement date and amount, maturity date, current balance.
   * Business: account number, customer ID, registration number or TIN, business name, facility amount, disbursement date and amount, maturity date, current balance.
2. **Keep what matching uses:** all identifiers, names, date of birth, disbursement date, the old account and customer numbers.
3. **Keep what a credit report or a score needs:** status, balance, arrears, days in arrears, classification, last payment, write-off, restructuring, security, guarantor.
4. **Drop what the cleanser itself discards or fixes:** `Data` (always set to `D`), `CurBalIndicator` (always set to `D`), all postal-code columns (always blanked).
5. **Drop what can be derived:** facility term (from the dates), arrears start date (from days in arrears), the seven overdue-amount buckets and the payment history profile (the bureau builds these from its own monthly history).
6. **Collapse repeats:** four address lines to two; three addresses to one; seven ID columns to four; four guarantors to one.

## 3. Proposed individual credit template: 178 → 62 columns

| Group | Keep | Dropped |
| --- | --- | --- |
| Record (4) | `CorrectionIndicator`, `CreditFacilityAccNum`*, `CustomerID`*, `BranchCode` | `Data` |
| Identifiers (4) | `NatIDNum`* (Ghana Card), `SSNum`, `OtherIDType`, `OtherIDNum` (voter, driver, passport or other, named by type) | `VotersIDNum`, `DriverLicNum`, `PassportNum`, `EzwichNum`, `TINum` as separate columns |
| Person (8) | `Surname`*, `FirstName`*, `MiddleNames`, `PreviousNames`, `DateOfBirth`*, `Gender`, `MaritalStatus`, `Nationality` | `Title`, `Alias` |
| Address and contact (6) | `CurResAddr1`, `CurResAddr2`, `OwnerOrTenant`, `EmailAddress`, `MobileTel1`, `MobileTel2` | `CurResAddr3–4`, previous address (5), postal address (5), `DateMovedCurrRes`, proof of address (2), `HomeTel`, `WorkTel`, postal codes |
| Employment (5) | `EmpType`, `EmpName`, `Occupation`, `IncomeCurrency`, `Income` | `EmpPayrollNum`, `Paypoint`, employer address (5), `DateOfEmp`, `NumOfDependants` |
| Facility terms (10) | `CreditFacilityType`, `PurposeOfFacility`, `JointOrSoleAcc`, `AmountCurrency`, `FacilityAmount`*, `DisbursementDate`*, `DisbursementAmt`*, `MaturityDate`*, `SchdInstalAmount`, `RepaymentFreq` | `FacilityTerm`, `DefPaymentStartDate`, `NoParticipantsInAcc` |
| Monthly position (13) | `CurBal`*, `AmountInArrears`, `NDIA`, `AssetClassification`, `LastPaymentAmount`, `LastPaymentDate`, `FacilityStatusCode`, `FacilityStatusDate`, `ClosedDate`, `ClosureReason`, `WrittenOffAmt`, `DateRestructured`, `LegalFlag` | `CurBalIndicator`, `NextPaymentDate`, `ArrearsStartDate`, `PaymentHistoryProfile`, 7 overdue buckets, `ReasonForWrittenOff`, `ReasonForRestructure`, `SpecialCommentsCode` |
| Security (3) | `CreditCollateralInd`, `SecurityType`, `SecurityValue` | `NatureOfCharge`, `CollRegRefNum` |
| Earlier references (2) | `OldCustomerID`, `OldAccountNum` | `OldSRN`, `OldBranchCode` |
| Guarantor (7) | one guarantor, see below | guarantors 2–4 and the separate company-guarantor columns |

\* required for a CLEAN record.

**One guarantor, 7 columns instead of 67:** `GuarantorType` (individual or business), `GuarantorName` (business name, or surname), `GuarantorFirstName`, `GuarantorIDType`, `GuarantorIDNum` (Ghana Card or registration number), `GuarantorDOB`, `GuarantorMobile`.

## 4. Proposed business credit template: 158 → 52 columns

Same facility, monthly, security, earlier-reference and guarantor groups as the individual template (34 columns, without `JointOrSoleAcc`), plus:

| Group | Keep | Dropped |
| --- | --- | --- |
| Record (4) | `CorrectionIndicator`, `Facilityaccnum`*, `CustomerID`*, `Branchcode` | `Data` |
| Business (10) | `Busregnum`*, `Tinum`* (one of the two), `Businessname`*, `Tradingname`, `Bustype`, `Sectorindcode`, `Subsecindcode`, `Registrationdate`, `Turnovercurrency`, `Turnoveramount` | `Prevregnum`, `Prevbusname`, `Commencementdate` |
| Address and contact (4) | `Curlocadd1`, `Curlocadd2`, `Emailaddress`, `Officetel1` | `Curlocadd3–4`, postal address (5), proof of address (2), `Websiteadd`, `Officetel2`, `Officefaxnum`, postal codes |

That gives 34 + 18 = 52.

## 5. Dud cheque and judgement templates

These repeat the full person or business block and then add a few columns. They can use the **same simplified identity block** as above:

| Template | Today | Proposed | Identity block | Specific columns kept |
| --- | --- | --- | --- | --- |
| Individual dud cheque | 74 | 27 | record 4 + identifiers 4 + person 8 + contact 4 | `ChequeNumber`, `DateAccountOpened`, `DateIssued`, `DateBounced`, `ReasonReturned`, `Currency`, `ChequeAmount` |
| Business dud cheque | 46 | 21 | record 4 + business 6 + contact 4 | the same 7 |
| Individual judgement | 76 | 29 | as individual dud cheque | `CourtName`, `CourtLocation`, `CourtType`, `CaseNumber`, `FilingDate`, `CaseType`, `CaseReason`, `Currency`, `Amount` |
| Business judgement | 48 | 23 | as business dud cheque | the same 9 |

## 6. Other tidy-ups worth making at the same time

* **One spelling per column across templates.** Today the same field is `CreditFacilityAccNum`, `Facilityaccnum` and `FacilityAccnum`; `DateOfBirth`, `DateOfBrith` and `DOB`; `TINum`, `Tinum` and `TiNum`. Header checks are exact, so each variant is a trap for providers.
* **Ghana Card as the primary individual identifier**, with the older IDs carried in the `OtherIDType` / `OtherIDNum` pair.

## 7. What the cleanser rules already tell us (for the other reference items)

| Reference | What the cleanser rules give us | Still missing |
| --- | --- | --- |
| R1 Templates | Column names and order for six templates; which fields gate a CLEAN record | Data types and maximum lengths |
| R2 Code lists | `CorrectionIndicator` 0/1/2; facility type `V` = overdraft, default `P`; asset classification `A`–`E`; `OwnerOrTenant` O/T; currencies GHS, USD, EUR, GBP (and NGN for turnover) | The full lists and meanings: facility type, purpose, repayment frequency, facility status, closure reason, legal flag, special comments, business type, sector and sub-sector, guarantor nature, security type, gender, marital status |
| R3 Validation | Three outcomes (CLEAN, UNLOADABLE, DUPLICATE); cleanse-then-gate approach; placeholder-ID detection; which bad values are blanked and which block the row | Error codes or messages given to providers; the "recent records" cut-off for mandatory IDs |
| R4 Matching | Facility key = (account number, customer ID), preferring the same disbursement date; duplicate rule (lower balance wins); cross-record ID, name and date-of-birth checks; name-token similarity; trust in previously accepted names; the name-review workflow | Similarity thresholds; how matching works *across* providers |
| R5 Calendar and SLAs | Nothing | Deadlines, frequency, resubmission practice |

## 8. Where real practice differs from what the game does today

| Topic | Cleanser (real practice) | Game today | Proposed change |
| --- | --- | --- | --- |
| Bad optional values | Cleaned or blanked; the row still loads | Many are errors that reject the row | Follow the cleanser: cleanse, then gate only on the required fields |
| Duplicates | Same account, customer and disbursement date; names must agree; the lower balance is kept | Exact duplicate rows only | Adopt the real rule |
| Disbursement date changes | Unloadable, except overdrafts | Not checked | Add |
| Name problems | Held for review (same surname and first name, business words in a person's name, "AND" names) | Not checked | New work-item type |
| Asset classification | Codes `A`–`E` | `CUR`, `OLEM`, `SUB`, `DBT`, `LOSS` | Use `A`–`E` |
| Days in arrears | `NDIA` | `DAYS_PAST_DUE` | Rename |
| Reporting date | Not a column; it comes from the submission | A column on every row | Remove the column |
| Other data | Dud cheques and court judgements | Not in the game | Decide (question 5 below) |

## 9. Owner's answers (14 November 2026)

| Topic | Answer |
| --- | --- |
| Purpose | The game must reflect what is used in the real world. The real templates are bulky; keeping only the necessary columns does not distort the data. The proposed columns are accepted. |
| Change over time | Schemas, templates, pricing and other rules do change in the real world. The game must allow rule changes without corrupting a game in progress (D19). |
| Dud cheques and judgements | Included, as separate templates for now. They may later be folded into the individual and business templates. |
| Mandatory ID | A valid ID is mandatory for records from **1 January 2020**. (To confirm: measured on the disbursement date.) |
| `CorrectionIndicator` | `0` = normal monthly submission; `1` = update or replacement of a record; `2` = deletion. A deletion is not made by the value alone: the provider also emails the bureau with the reason. |
| `Paypoint` | Where the credit client receives their income from. (Not in the simplified template.) |
| Pricing | Use reasonable, fair amounts; the owner adjusts after review. |

## 10. Questions still open

2. **Code lists:** can you export the mapping tables from the cleanser (facility type, purpose, repayment frequency, facility status, closure reason, legal flag, special comments, business type, sector, guarantor nature, security type, asset-classification day ranges)?
3. **Meanings:** `Data` = `D`; `CurBalIndicator` (is a credit balance ever reported?); `SRN`.
6. **Identifiers:** which of the seven ID columns do providers actually fill today? Is collapsing voter, driver and passport into one typed pair acceptable?
7. **`DisbursementAmt` versus `FacilityAmount`:** when do they differ in practice (partial drawdowns)? If rarely, one column is enough.
8. **Duplicates:** why does the *lower* balance win (the most recent position)?
9. **Ghana Card format:** what exactly does the cleanser accept as "Ghana Card-like"?
10. **Publishing:** the repository is now public. `templates.md` (column names) is already in it. May `CLEANSER_RULES.md`, which describes an internal application, be published too, or should it stay in `docs/references/private/`?
