# Playtest notes: Phase 1, Claude, 14 November 2026

**Game:** 16, default world (seed 42), Established (12 months of history) **Played:** 4 January to 2 February 2027 **Real time spent:** about 40 minutes

**How I played:** in the browser for the briefing, dashboard, queue, review screens, submissions, enquiries, ledger, statements and invoices. To save time I advanced most days, and made 14 of my 16 decisions, by calling the same API the buttons call. So these notes say less about click-by-click feel than yours will.

**My results (from the hidden answer key, which a player cannot see):** 16 of 16 decisions correct. Staff: 270 of 349 correct (77%).

## Fun

- **Triage of "closed but has a balance" is a real puzzle.** Balance 1,363.14, amount paid 1,363.14, maturity passed: that account really closed, so the "make it active" fix is wrong and it should go back to the lender. Balance 483.94, 15 days in arrears, nothing paid: clearly still live. Working that out felt like the job.
- **The first morning.** A file arrives, 16 items appear, and there is something to do straight away.
- **Following a record back to its file and row** on the customer page.
- **The statements.** Seeing January's revenue, payroll and taxes land in the right places was satisfying.

## Tedious

- **Waiting on the first day.** "End of day" on 4 January took about 50 seconds showing only "Working…". Days when the big files load took 10–20 seconds; quiet days 2–3 seconds.
- **Date fixes need no thought.** `05/14/1992` can only be 14 May. I approved six of these; they should never reach a person (a cleansing rule should do it, which is also what your cleanser does).
- **Deciding an item sends you back to the list.** There is no "next item", so working a queue is list, item, list, item.
- **Nothing to do for most of the month.** After the first week the queue is empty and the days are just clicks.

## Confusing

- **The evidence I needed was not on the screen.** For the closed-with-a-balance puzzle I needed amount paid, maturity date and last month's position. The triage screen shows only balance, status and days in arrears. I got them from the raw record.
- **The briefing at 17:00 describes yesterday.** After playing a day, the page still says "what happened on" the previous day. Today's file and today's 16 new items are not mentioned until tomorrow.
- **"Held" on the submissions register never goes down.** SwiftCash shows 2 held and Meridian 1, but the queue is empty: the count is frozen at the end of the run.
- **"Why?" on the hit rate lists "no record found" enquiries but does not say why.** No subject is shown and an enquiry cannot be opened. I could not tell a new borrower from a record we rejected.
- **Dates appear in two formats on the match screen:** `02/01/2003` for the record and `1997-05-12` for the bureau customer.
- **Similarity numbers are hard to trust.** "Odoi Laryea" against "Abena Kyei" scores name similarity 0.65.
- **Decision buttons do not say what will happen.** "Different customer: create new" leaves open who keeps the Ghana Card number.
- **The late-file warning has no action.** Horizon Finance was two days overdue; all I could do was read it.

## Wrong

- **The bureau loses about GHS 123,000 a month.** January: revenue GHS 20,505 against costs of GHS 143,843 (rent 90,000 for two months booked, salaries 21,100, IT 30,000). Even counting one month of rent, three subscribers at GHS 15 a report cannot carry the costs, and the player has no way to change that yet. A bureau with only three staff and three subscribers is not a believable "established" bureau.
- **Match reviews are all obvious.** Every one I saw paired two plainly different people (a man and a woman, different names, different birth dates). The hard cases a real officer sees, the same person with a typo or a changed name, are linked automatically and never shown.
- **Staff clear the queue too fast for there to be pressure.** About 365 items in January against a team that can do roughly 120 a day. I had to hurry to find 16 items to decide myself, and never reached 20.
- **Staff accuracy of 77% with no way to see it.** Nearly a quarter of staff decisions were wrong and nothing in the game tells the player.
- **606 SwiftCash records are lost every month** (no Ghana Card or date of birth) with nothing the bureau can do or say to the lender.
- Things your cleanser rules show the game gets wrong are listed in `docs/references/template-simplification-proposal.md`, section 8.

## Bugs

- "Records processed" in the briefing leaves out duplicates, so the three numbers do not add up to the total.
- "Held" count frozen (see Confusing).

## If only one thing changed

**Tell the player how good their data and their team really are.** I only know I scored 16 of 16 and the staff 77% because I looked at the answer key. The monthly Data Quality Review (P2.3) is the missing half of every decision in the game.

## What this suggests for the Phase 2 order

1. Milestone A is the right start, and **P2.3 (Data Quality Review) should come before P2.2** (events), since it is what makes decisions meaningful.
2. **Bring the economy forward.** The bureau's size, costs, prices and subscriber numbers need a first balancing pass early (a slice of P2.9 and P2.12), not at the end, or every playtest will be of a company that is quietly going bust.
3. **Queue pressure and harder cases** (P2.4 fuzzy matching, plus staff capacity) matter more than new item types.
4. Small fixes worth doing at once: a "next item" button, the missing evidence on the triage screen, today's events in the briefing, one date format.
