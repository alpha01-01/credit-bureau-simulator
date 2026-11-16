"""The Bureau Handbook v1 (P2.11; Document 07, Section 11.4).

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

BY_KEY = {e.key: e for e in ENTRIES}
