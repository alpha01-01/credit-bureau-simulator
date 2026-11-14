# Changing a rule (the rule book)

Rules change in the real world: the regulator revises the data standard, the government changes a tax rate. The game follows those changes without rewriting any game's past (Document 07, D19). This note says how to make a change.

## What is versioned

The rule book is `backend/apps/standards/rulebook.py`. It holds **series** of **editions**. Each edition has a version and an effective date.

| Series | What it holds | Chosen by |
|---|---|---|
| `DATA_STANDARDS` | Templates (columns, mandatory or conditional, types, lengths), code lists, core fields for the core-fields policy, which IDs count, the date from which an ID is required, the submission due day | The **reporting period** of the data. December's data follows the standard in force for December, whenever it is processed or reviewed. |
| `TAX_RULES` | VAT and levies, SSNIT rates, PAYE bands, the remittance day | The **transaction date**: the invoice date (tax point) or the pay day. |

What used each edition is recorded:
- **Data standard:** a submission and every processing run record the data standard version, and the version also appears in the provider's file name.
- **Tax rules:** journal entries for invoices and payroll record the tax rules version.

Reviews and reprocessing use the recorded version, not today's.

The bureau's own prices are not in the rule book. Each subscriber contract carries its price with a start date, and every usage record keeps the price charged.

## Making a change

1. **Add a new edition and leave the old one alone.** For example, the regulator publishes standard 1.2 for data from July 2027:

   ```python
   STANDARD_1_2 = replace(
       STANDARD_1_1,
       version="1.2",
       effective=date(2027, 7, 1),
       fields={...},          # the new column list
       note="What changed and the source (circular, date).",
   )
   DATA_STANDARDS = Series("data standard", (STANDARD_1_1, STANDARD_1_2))
   ```

2. **Teach the world any new field.** Providers' true values come from `apps/world/provider_files/truth.py`. Until the world produces a new column, it is sent blank, and a new mandatory column would then be rejected.

3. **Release it.** Record the edition's parts in `apps/standards/rulebook.lock.json`. You can print them with `parts(STANDARD_1_2)`: one digest per template, code list and threshold. The lock test fails until you do, and it fails whenever a released part is edited or removed.

4. **Record it.** Add a row to `docs/assumptions.md` (or cite the source) and a line to `docs/progress.md`.

## What happens in a running game

- Games whose clock is before the effective date carry on under the old edition. They switch when their data reaches that date.
- From the effective date, providers name their files with the new version and send the new columns.
- A file sent on the old version for a period under the new one is rejected with **T005**.
- Data already loaded, invoices already issued and decisions already made keep the edition they used.

## Never

- Never edit a released part of an edition (the lock test stops this).

Adding a part the standard always had to a released edition is allowed. The dishonoured cheque and judgment templates were added to 1.1 this way (P2.0c), because no recorded data used them. Record the new parts in the lock file.
- Never delete one: games that used it still need it for reviews and reprocessing.
- Never give two editions of one series the same effective date.
