"""The Bureau Handbook (v1 P2.11, v2 P3.14; Document 07, Section 11.4).

Each entry explains one concept the player meets, with an "In practice" note on
the Ghanaian market. Regulatory statements cite the instrument by name; where
the provision has not been checked against the text it says so (status
``TO_CONFIRM``). The owner reviews every regulatory entry before release (D14);
until then ``reviewed`` is False and the page says so.

Sources of the in-practice notes: the Data Standards Committee manuals v1.1 (July
2012) as noted in ``docs/references/data-formats.md`` (R1-R3), and the project's
recorded assumptions. Nothing here is legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ACT_726 = "Credit Reporting Act, 2007 (Act 726)"
LI_2394 = "Credit Reporting Regulations, 2020 (L.I. 2394)"
ACT_843 = "Data Protection Act, 2012 (Act 843)"
ACT_1015 = "Corporate Insolvency and Restructuring Act, 2020 (Act 1015)"
DSC = "Data Standards Committee manuals (CONC, BUSC, COND, CONJ), v1.1, July 2012"

DISCLAIMER = (
    "The Handbook is educational. It simplifies, and it is not legal advice. Regulatory "
    "citations are being checked against the texts by the project owner."
)


@dataclass(frozen=True)
class Citation:
    instrument: str
    provision: str = "provision to be confirmed"
    reference: str = ""  # the project's reference number (docs/references/README.md)
    status: str = "TO_CONFIRM"  # or CONFIRMED, once checked against the text


@dataclass(frozen=True)
class Entry:
    key: str
    title: str
    body: str
    in_practice: str
    screen: str = ""
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    regulatory: bool = False
    reviewed: bool = False
    added: str = "v1"  # the Handbook version that added it (v2: P3.14)


ENTRIES: tuple[Entry, ...] = (
    Entry(
        "submission",
        "Data submission",
        "Each month every data provider (a lender reporting to the bureau) sends the "
        "bureau a submission: one file per template, covering every account it holds as at "
        "the month end. The bureau registers the submission before reading it: who sent it, "
        "for which reporting period, when it arrived and whether it was late.",
        "Ghanaian bureaus receive monthly files in the templates of the Data Standards "
        "Committee: consumer credit, business credit, dishonoured cheques and judgments. "
        "Providers report every open account, not only the ones that changed.",
        "submissions",
        (Citation(DSC, "templates CONC, BUSC, COND, CONJ", "R1", "CONFIRMED"),),
    ),
    Entry(
        "validation",
        "Validation",
        "Validation checks a file against its template (the right columns, in order) and "
        "then every field against its rule: mandatory, the right format, a valid code, "
        "consistent with the other fields. A field that fails may be cleansed, held for a "
        "decision, or make its record unloadable.",
        "The manuals list each field's format and code list; bureaus add checks of their "
        "own. Which failures reject a record and which only warn is a bureau's choice.",
        "rules",
        (Citation(DSC, "field definitions and validation rules", "R3", "CONFIRMED"),),
    ),
    Entry(
        "processing-summary",
        "Processing summary",
        "After each run the bureau states what happened to every record: loaded, could not "
        "be loaded, sent twice, or held for a decision. The four must add up to the records "
        "received; if they do not, records have been lost.",
        "Bureaus send providers a similar summary with their error report, so the provider "
        "can reconcile what it sent with what was accepted.",
        "submissions",
    ),
    Entry(
        "unloadable-record",
        "Unloadable record",
        "A record that fails a validation rule the bureau will not relax. It is not loaded: "
        "nothing it says reaches a report until the provider corrects and resends it. Each "
        "unloadable record lowers coverage; each one loaded wrongly lowers accuracy.",
        "Common causes are missing identifiers, impossible dates and codes written as "
        "words. Most are fixed at the provider once it is told.",
        "queue",
    ),
    Entry(
        "cleansing",
        "Cleansing",
        "Correcting a value the bureau can be sure of without asking the provider: trimming "
        "spaces, a known misspelling, a code written as a word. Every change is logged with "
        "the rule that made it, so the original can always be shown.",
        "Cleansing treats symptoms. A good bureau also tells the provider, so the next file "
        "arrives clean.",
        "rules",
    ),
    Entry(
        "provider-feedback",
        "Provider feedback",
        "A report to the provider of the records it sent that could not be loaded, with the "
        "rule, field and value at fault. Feedback, training and fair enforcement improve a "
        "provider's data over the following months.",
        "Service agreements between bureau and provider set deadlines for submissions and "
        "resubmissions.",
        "providers",
        (Citation(DSC, "resubmission deadlines", "R5", "CONFIRMED"),),
    ),
    Entry(
        "identity-resolution",
        "Identity resolution (matching)",
        "Deciding which bureau customer a provider's record belongs to. An identifier that "
        "matches with an agreeing name and date of birth links it at once; a close match "
        "without one is linked automatically above one threshold and held for a person to "
        "decide between two thresholds; below them it becomes a new customer.",
        "The Ghana Card number is now the primary identifier for individuals; older "
        "accounts often carry voter, passport or SSNIT numbers instead, so names and dates "
        "of birth still matter.",
        "queue",
    ),
    Entry(
        "false-merge",
        "False merge",
        "Two different people treated as one customer. Each person's report then shows the "
        "other's accounts: one may be refused credit for someone else's debt.",
        "The error a lender and a consumer notice; it is the usual cause of disputes.",
        "reviews",
    ),
    Entry(
        "false-split",
        "False split",
        "One person held as two customers. Each report shows only part of their history, so "
        "it looks thinner or cleaner than it is, and an enquiry may miss them.",
        "Quieter than a false merge, and costlier to lenders: they lend on half the picture.",
        "reviews",
    ),
    Entry(
        "monthly-observation",
        "Monthly observation",
        "Each month's file reports the same accounts again. The bureau keeps each report as "
        "an observation of balance, arrears and status at that month end; a new account is "
        "only one it has not seen before.",
        "A year of observations is what makes a report useful: a lender reads the pattern "
        "of payments, not one month.",
        "customers",
    ),
    Entry(
        "days-past-due",
        "Days past due",
        "How many days a payment is overdue at the reporting date. It is the main measure of "
        "how an account is performing.",
        "Bank of Ghana's prudential classification goes by days past due: current 0-29, "
        "other loans especially mentioned 30-89, substandard 90-179, doubtful 180-359, loss "
        "360 and over.",
        "customers",
        (Citation("Bank of Ghana prudential classification", "as noted in R2", "R2"),),
        regulatory=True,
    ),
    Entry(
        "lineage",
        "Lineage",
        "Every fact the bureau holds can be traced to the file, row and run it came from, and "
        "every change to the rule or person that made it.",
        "Lineage is how a bureau answers a dispute or a regulator's question: where did this "
        "come from, and who changed it?",
        "submissions",
    ),
    Entry(
        "enquiry",
        "Enquiry",
        "A subscriber asks for a report on an applicant. The bureau looks the subject up by "
        "identifier and name, returns what it holds, records the enquiry on the subject's "
        "file and bills the subscriber.",
        "Enquiries themselves appear on later reports: many in a short time can be a sign of "
        "credit-seeking.",
        "enquiries",
        (Citation(ACT_726, reference="R6"),),
        regulatory=True,
    ),
    Entry(
        "permissible-purpose",
        "Permissible purpose",
        "A bureau may give a report only for a purpose the law allows, such as assessing an "
        "application for credit, reviewing an existing account or collecting a debt. Every "
        "enquiry states its purpose.",
        "The purposes allowed are set out in the Act and the Regulations; the bureau must be "
        "able to show the purpose of every enquiry it answered.",
        "enquiries",
        (Citation(ACT_726, reference="R6"), Citation(LI_2394, reference="R7")),
        regulatory=True,
    ),
    Entry(
        "consent",
        "Consent",
        "A subscriber must have the subject's consent before asking for their report, and "
        "gives a reference to it with each enquiry.",
        "Consent sits alongside data protection duties on everyone who handles personal data.",
        "enquiries",
        (Citation(LI_2394, reference="R7"), Citation(ACT_843, reference="R10")),
        regulatory=True,
    ),
    Entry(
        "hit-rate",
        "Hit rate",
        "The share of enquiries on which the bureau found the subject. A hit is not always "
        "the right person: a false merge can produce a hit on someone else.",
        "Subscribers judge a bureau first by its hit rate, then by whether its reports turn "
        "out to be right.",
        "enquiries",
    ),
    Entry(
        "dispute",
        "Dispute",
        "A subject who believes their report is wrong may dispute it. The bureau must "
        "investigate, correct what is wrong and answer within a statutory period; while the "
        "dispute is open the report is flagged.",
        "Missed deadlines draw findings from the regulator, and repeated findings climb a "
        "ladder from a concern letter to suspension and revocation of the licence.",
        "disputes",
        (
            Citation(LI_2394, "Regulations 23-26 (dispute resolution)", "R7"),
            Citation(ACT_726, reference="R6"),
        ),
        regulatory=True,
    ),
    Entry(
        "data-quality",
        "Accuracy, coverage and freshness",
        "Accuracy: the share of facts on file that are true. Coverage: the share of the "
        "market's active borrowers the bureau holds. Freshness: how old its latest report on "
        "an open account is. The bureau estimates accuracy by auditing a sample with the "
        "providers; the monthly Data Quality Review reveals the truth.",
        "Lenders buy coverage and freshness first and notice accuracy when it fails them.",
        "dashboard",
    ),
    Entry(
        "usage-billing",
        "Usage billing",
        "Each report delivered is recorded as usage at the subscriber's contract price. At the "
        "month end each subscriber's usage becomes an invoice, payable on the agreed terms.",
        "Contracts may be pay-per-report, bundles or subscriptions; the game uses "
        "pay-per-report until real price lists are supplied.",
        "finance",
    ),
    Entry(
        "double-entry",
        "Double-entry bookkeeping",
        "Every business event is posted as a journal entry whose debits equal its credits: an "
        "invoice debits receivables and credits revenue; a payment debits the bank and "
        "credits receivables. The statements are only sums of these entries.",
        "VAT, NHIL and GETFund levies on the bureau's services, PAYE and SSNIT are posted "
        "with the events that give rise to them.",
        "finance",
    ),
    Entry(
        "income-statement",
        "Income statement (P&L)",
        "Income less expenses for a period. Revenue counts when the report is delivered, not "
        "when the subscriber pays, so a profitable month can still leave the bank short.",
        "Boards read the P&L with the cash position: a bureau fails when cash runs out.",
        "finance",
    ),
    Entry(
        "insolvency",
        "Overdraft, creditors and insolvency",
        "When cash runs short the bureau draws on its overdraft. Beyond the agreed limit its "
        "creditors may serve a statutory demand; a company that cannot pay within the period "
        "allowed may be presumed insolvent.",
        "The period and the presumption come from Ghana's corporate insolvency law.",
        "health",
        (Citation(ACT_1015, reference="R19"),),
        regulatory=True,
    ),
    Entry(
        "licence",
        "The bureau's licence",
        "A credit bureau operates under a licence from the Bank of Ghana, which supervises it "
        "and may direct, penalise, suspend or revoke.",
        "The supervisor's directives and notices add detail to the Act and the Regulations.",
        "health",
        (
            Citation(ACT_726, reference="R6"),
            Citation("Bank of Ghana directives and notices", reference="R11"),
        ),
        regulatory=True,
    ),
)

# --- Handbook v2 (P3.14): the concepts Phase 3 added ----------------------------------------

V2 = "v2"

ENTRIES_V2: tuple[Entry, ...] = (
    # Disputes and the regulator (M7)
    Entry(
        "subject-rights",
        "The subject's rights",
        "The person or business a report is about is its subject. A subject may learn what "
        "the bureau holds about them, ask for a copy of their report, and dispute anything in "
        "it they believe is wrong. The bureau may not refuse to investigate.",
        "Subjects usually find a problem when a lender turns them down and names the bureau. "
        "Lenders must say which bureau's report they relied on.",
        "disputes",
        (
            Citation(ACT_726, "on the rights of the data subject", "R6"),
            Citation(LI_2394, "Regulations 23-26 (dispute resolution)", "R7"),
            Citation(ACT_843, "on the data subject's rights of access and correction", "R10"),
        ),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "correction",
        "Correcting a record",
        "When a dispute is upheld the bureau does not delete or overwrite: it writes a "
        "correction record that supersedes the old fact, saying what changed, why, on whose "
        "authority and from which dispute. A falsely merged account is moved to the customer "
        "it belongs to; reports from then on show the corrected file.",
        "The provider is told, so that its next file does not bring the error back. A "
        "correction that the next month's file undoes is a common source of repeat disputes.",
        "disputes",
        (Citation(LI_2394, "Regulations 23-26 (dispute resolution)", "R7"),),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "regulator-ladder",
        "Findings and the regulator's ladder",
        "Each dispute left past its deadline, return filed late or compliance finding left "
        "unremedied is a regulator finding. The regulator acts on the number of findings in "
        "the last six months: a concern letter, a formal directive, a financial penalty, "
        "suspension of the licence, revocation. As findings age out the bureau steps back down.",
        "The thresholds and penalty in the game are assumptions; the supervisor's actual "
        "practice is set out in its directives and notices.",
        "health",
        (
            Citation("Bank of Ghana directives and notices", reference="R11"),
            Citation(ACT_726, "on the supervisor's powers", "R6"),
        ),
        regulatory=True,
        added=V2,
    ),
    # Staff and tooling (M8)
    Entry(
        "capacity-and-skill",
        "Capacity and skill",
        "Capacity is how many work items the team can decide in a day; skill is the chance "
        "each decision is right. Each employee has a skill for each kind of item that grows "
        "with experience and training. Morale falls when pay lags the market or the queue "
        "overwhelms the team, and unhappy staff leave.",
        "Experienced data officers are scarce and ask for more; graduates learn on the job.",
        "staff",
        added=V2,
    ),
    Entry(
        "matching-tooling",
        "Matching tooling",
        "Software that decides automatically whether a record belongs to a customer the "
        "bureau already holds. Basic tooling matches on identifiers only; better tooling adds "
        "fuzzy matching on names, dates of birth and phone numbers. It links more records "
        "without review, at a monthly cost, and its mistakes are made without anyone seeing them.",
        "Without a universal identifier on every record, matching is the core skill of a "
        "Ghanaian bureau; the Ghana Card makes it easier as coverage grows.",
        "queue",
        added=V2,
    ),
    Entry(
        "cost-of-quality",
        "The cost of quality",
        "Every wrong decision costs something later: a dispute, a declined applicant, a "
        "finding, a subscriber's lost trust. Staff, training and tooling cost money now. The "
        "chief executive balances the two.",
        "Bureaus report accuracy to their boards and to the regulator; subscribers judge it "
        "by the disputes their customers raise.",
        "health",
        added=V2,
    ),
    # Analytics (W1)
    Entry(
        "vintage",
        "Vintage",
        "The loans disbursed in one period (here a quarter), followed as they age. Comparing "
        "vintages at the same age shows whether lending is getting riskier.",
        "Young vintages always look good: their loans have not yet had time to go bad.",
        "analytics",
        added=V2,
    ),
    Entry(
        "default-definition",
        "Default",
        "In the game's analytics a loan has defaulted when it reaches 90 or more days past "
        "due within 12 months of disbursement. A vintage is mature once all its loans are 12 "
        "months old; before then its default rate is only 'so far'.",
        "90 days past due is the usual definition in prudential rules and scorecard practice; "
        "lenders may use their own.",
        "analytics",
        added=V2,
    ),
    Entry(
        "roll-rate",
        "Roll rates",
        "The share of accounts that move from one arrears bucket to another between two "
        "months: from current to 1-29 days, from 30-59 to 60-89, and so on. Roll rates show "
        "where a portfolio is deteriorating before defaults rise.",
        "Collections teams watch the roll from current to 1-29 days; risk teams watch the "
        "roll into 90+.",
        "analytics",
        added=V2,
    ),
    Entry(
        "sql-console",
        "The SQL console",
        "A read-only window onto the bureau's own tables, for the Head of Data Analytics: any "
        "question the screens do not answer can be asked in SQL. It never shows the world's "
        "truth, only what the bureau holds.",
        "Analysts at bureaus spend much of their time on such ad hoc questions from lenders "
        "and the regulator.",
        "console",
        added=V2,
    ),
    Entry(
        "mobile-loan",
        "Mobile loans",
        "Small, short loans taken on a phone through a telecom's wallet, reported in the same "
        "template as other consumer loans with the file marked as mobile. They are many, "
        "short and often repeated, and borrowers may hold several at once from different "
        "lenders.",
        "Mobile lending reaches people with no other credit history; its data is what lets "
        "a bureau score them at all.",
        "submissions",
        (Citation(DSC, "template CONC (file marked mobile)", "R1", "CONFIRMED"),),
        added=V2,
    ),
    # Scorecards (W2)
    Entry(
        "scorecard",
        "Scorecard",
        "A model that turns a credit file into a score: each characteristic (worst arrears, "
        "number of recent enquiries, utilisation) is grouped into bins, each bin carries "
        "points, and the points add up. The game builds one for short-, mid- or long-term "
        "credit, or a composite of the three.",
        "Bureau scores in Ghana are sold alongside the report; lenders set their own cut-offs.",
        "scorecards",
        added=V2,
    ),
    Entry(
        "gini",
        "Gini, AUC and the holdout",
        "A scorecard is judged on a holdout: customers it was not fitted on. The AUC is the "
        "chance that a borrower who went bad scores lower than one who did not; Gini is "
        "2 x AUC - 1, from 0 (no better than chance) to 1 (perfect ranking). KS is the widest "
        "gap between the score distributions of goods and bads.",
        "Lenders compare scorecards by Gini; a higher one ranks borrowers better, but only "
        "on a population like the one it was built on.",
        "scorecards",
        added=V2,
    ),
    Entry(
        "restricted-attribute",
        "Restricted attributes",
        "Some facts about a person may not be used to decide whether they get credit, however "
        "well they predict: in the game, gender. The workbench flags a scorecard that uses "
        "one, and Compliance raises a finding if it is deployed.",
        "Which attributes are restricted, and on what authority, is to be confirmed.",
        "scorecards",
        (Citation("Owner's policy for the game (D14); anti-discrimination principles"),),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "credit-score",
        "The credit score as a product",
        "Once a scorecard is deployed, each report carries the subject's score and a subscriber "
        "may buy the score on its own. The score is only as good as the data behind it: a "
        "false merge moves it as surely as a missed payment.",
        "A score shifts when the population does: the bureau watches the scores it sells "
        "drift from those it was built on and rebuilds when they part.",
        "products",
        added=V2,
    ),
    # Compliance (W3)
    Entry(
        "consent-sampling",
        "Consent sampling",
        "The bureau answers an enquiry on the subscriber's word that the subject consented "
        "and that the purpose is permitted. Compliance tests that word by asking a subscriber "
        "for the forms behind a sample of its enquiries; any it cannot produce are a finding.",
        "Consent is given on the lender's application form; it also covers reviewing an "
        "existing account, employment and tenancy screening and collecting a debt.",
        "compliance",
        (
            Citation(LI_2394, "on consent and permissible purpose", "R7"),
            Citation(ACT_726, "on access to credit information", "R6"),
        ),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "sanction",
        "Sanctioning a subscriber",
        "A subscriber that cannot show consent may be warned or suspended. A suspended "
        "subscriber cannot enquire; a sanctioned one becomes more careful.",
        "The bureau is answerable for who sees the data it holds: its contract with each "
        "subscriber sets out the duty and the remedies.",
        "compliance",
        (Citation(LI_2394, "on the bureau's duties toward users of credit information", "R7"),),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "regulatory-return",
        "The monthly return",
        "Each month the bureau reports its activity to the Bank of Ghana: files received, "
        "enquiries answered, disputes received and settled. In the game it is due by the 15th "
        "of the next month; late or missing, it is a finding.",
        "The content and timing of returns are set by the supervisor's directives.",
        "compliance",
        (Citation("Bank of Ghana directives to credit bureaus", reference="R11"),),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "retention",
        "Retention",
        "A closed account stays on reports for a fixed period after it closed, here 5 years, "
        "and no longer. A bureau may keep it for less, not more: a report showing an account "
        "past its period is a breach.",
        "Retention balances the lender's need for history against the borrower's right to a "
        "fresh start.",
        "compliance",
        (
            Citation(LI_2394, "on retention of credit information", "R7"),
            Citation(ACT_843, "on keeping personal data no longer than necessary", "R10"),
        ),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "access-review",
        "Access review",
        "Each quarter Compliance reviews who can reach the bureau's data and removes the "
        "access of anyone who no longer needs it, leavers first.",
        "A leaver's account still open is a common audit finding in any data business.",
        "compliance",
        (Citation(ACT_843, "on security of personal data", "R10"),),
        regulatory=True,
        added=V2,
    ),
    # Finance (W4)
    Entry(
        "supplier-bill",
        "Supplier bills and approval",
        "Suppliers (hosting, software, the landlord, power) send bills. A bill under the "
        "approval limit is paid on its due date; one above it waits for the Head of Finance. "
        "A bill paid late carries a charge, and hosting left unpaid is suspended.",
        "The expense is recorded when the bill arrives: what is owed sits in payables until "
        "the money goes.",
        "finance",
        added=V2,
    ),
    Entry(
        "bank-reconciliation",
        "Bank reconciliation",
        "At each month's start the bank's statement arrives. Reconciling matches each of its "
        "lines to an entry in the books; a line with no entry is either a posting the books "
        "are missing or a query for the bank.",
        "Auditors ask first for the reconciliations: they prove the books describe the cash.",
        "finance",
        added=V2,
    ),
    Entry(
        "budget",
        "Budget",
        "The year's plan for each cost, month by month. Reviewing actuals against it each "
        "month shows overspending early, while it can still be cut.",
        "Boards approve the budget and ask about every large variance.",
        "finance",
        added=V2,
    ),
    Entry(
        "month-close",
        "Closing the month",
        "A month is closed once its usage is invoiced, salaries paid, bills decided, the bank "
        "reconciled and the budget reviewed. After that its entries are final: a correction "
        "goes into a later month.",
        "A fast close leaves time to act on what the month's figures show.",
        "finance",
        added=V2,
    ),
    # Sales (W5)
    Entry(
        "lender-research",
        "Researching a lender",
        "Before a proposal, Sales learns what a lender needs: roughly how many applications it "
        "takes a month and what it values most, price, service or coverage. A meeting then "
        "tells what price it would sign at.",
        "Banks buy on coverage and service; microfinance and digital lenders are more "
        "sensitive to price.",
        "sales",
        added=V2,
    ),
    Entry(
        "proposal",
        "Proposals and contracts",
        "A proposal offers a lender a price per report, a term, a service level (standard or "
        "premium), and optionally a monthly minimum and a volume discount. The lender accepts, "
        "counters or declines; accepted, it becomes a contract and the lender a subscriber "
        "once it is set up to enquire.",
        "Contracts in the market typically run a year and renew.",
        "sales",
        added=V2,
    ),
    Entry(
        "pricing",
        "Pricing",
        "A lower price wins subscribers and volume, but every report earns less. A monthly "
        "minimum smooths revenue; a discount above a volume rewards the lenders who enquire "
        "most. The game's prices are placeholders: no bureau publishes its own.",
        "Subscribers stay while reports are worth their price: hit rate, accuracy and disputes "
        "answered on time are what they see.",
        "sales",
        added=V2,
    ),
    Entry(
        "service-level",
        "Service level",
        "What the bureau promises a subscriber about its systems being up. Under a premium "
        "service level the subscriber is owed a service credit for a month with long "
        "downtime; the lender values that promise, and it costs the bureau when it fails.",
        "Subscribers also judge the bureau by how quickly Customer Support answers their tickets.",
        "sales",
        added=V2,
    ),
    # Products and the startup
    Entry(
        "business-report",
        "Business credit report",
        "A report on a business: its facilities, their arrears, dishonoured cheques and "
        "judgments against it, and its directors. Lenders to small businesses read it with "
        "the directors' own reports.",
        "Business data comes in the BUSC template, cheques in COND and judgments in CONJ.",
        "products",
        (Citation(DSC, "templates BUSC, COND, CONJ", "R1", "CONFIRMED"),),
        added=V2,
    ),
    Entry(
        "batch-enquiry",
        "Batch enquiries",
        "A subscriber sends a file of many people at once, for example the applicants for a "
        "scheme, and receives a report on each. Each record is priced below a single report.",
        "Batches are common for employer-linked lending and for reviewing a whole portfolio.",
        "batches",
        added=V2,
    ),
    Entry(
        "provider-onboarding",
        "Onboarding a data provider",
        "A lender becomes a data provider once it has signed a data-sharing agreement and "
        "connected to the bureau. Its first file brings its whole book; from then each month "
        "brings the changes.",
        "The regulations require lenders to report to every licensed bureau; the work of "
        "connecting them still falls to the bureau.",
        "onboarding",
        (Citation(ACT_726, "on the duty of data providers to report", "R6"),),
        regulatory=True,
        added=V2,
    ),
    Entry(
        "it-capacity",
        "IT capacity and outages",
        "The bureau's systems process so many files a night; more capacity costs more each "
        "month. An outage stops enquiries until it is fixed, and subscribers notice.",
        "Systems that are down cost twice: the enquiries lost and the subscribers' trust.",
        "it",
        added=V2,
    ),
    Entry(
        "economy",
        "The economy",
        "Published indicators the bureau reads each month: inflation, the policy rate, wage "
        "growth and growth in activity. Inflation raises suppliers' prices and staff's pay; a "
        "higher policy rate means less lending and fewer enquiries; a shock brings more "
        "arrears and defaults.",
        "Ghana's inflation and policy rate have both moved widely in recent years; the "
        "Bank of Ghana publishes them monthly.",
        "economy",
        (Citation("Bank of Ghana statistical releases", reference="R15", status="TO_CONFIRM"),),
        added=V2,
    ),
    Entry(
        "board",
        "The board",
        "The board reviews the chief executive each quarter on the bureau's health. Reviews "
        "with no confidence in a row remove the chief executive; a startup is given a year "
        "before its first review counts.",
        "Investors in a bureau look for a path to profit within a few years.",
        "health",
        added=V2,
    ),
)

ENTRIES = ENTRIES + ENTRIES_V2
BY_KEY = {e.key: e for e in ENTRIES}
