"""The compliance rules the game enforces (P3.7; Document 09; D14).

Each rule cites the provision it stands for. Citations are marked ``TO_CONFIRM`` until
the owner has checked them against the texts (R6 Act 726, R7 L.I. 2394, R10 Act 843,
R11 Bank of Ghana directives); the periods and dates are ASSUMPTION A-077 until then.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComplianceRule:
    code: str
    title: str
    rule: str
    citation: str
    status: str = "TO_CONFIRM"


RULES: dict[str, ComplianceRule] = {
    r.code: r
    for r in (
        ComplianceRule(
            "CONSENT",
            "Consent and permissible purpose",
            "A subscriber may enquire only with the subject's consent, given on the "
            "application form, and for a permitted purpose: new credit, review of an "
            "existing account, employment or tenancy screening, or collecting a debt. "
            "The bureau checks a sample and acts on a subscriber that cannot show consent.",
            "Credit Reporting Act, 2007 (Act 726), on access to credit information; Credit "
            "Reporting Regulations, 2020 (L.I. 2394), on consent and permissible purpose",
        ),
        ComplianceRule(
            "RETURN",
            "Monthly return to the Bank of Ghana",
            "The bureau files a return on its activity for each month by the 15th of the "
            "next month (the next working day if that is not one).",
            "Bank of Ghana directives to credit bureaus (R11)",
        ),
        ComplianceRule(
            "RETENTION",
            "Retention of credit information",
            "A closed account is kept on reports for 5 years after it closed, and no "
            "longer. A bureau may keep it for a shorter time, not a longer one.",
            "Credit Reporting Regulations, 2020 (L.I. 2394), on retention; Data Protection "
            "Act, 2012 (Act 843), on keeping personal data no longer than necessary",
        ),
        ComplianceRule(
            "ACCESS",
            "Access to the bureau's data",
            "Only staff who need it may reach the bureau's data. Access is reviewed each "
            "quarter, and a leaver's access is removed.",
            "Data Protection Act, 2012 (Act 843), on security of personal data",
        ),
        ComplianceRule(
            "FAIRNESS",
            "Restricted attributes in credit decisions",
            "A credit score may not use a restricted attribute such as gender.",
            "Owner's policy for the game (D14); anti-discrimination principles to confirm",
        ),
        ComplianceRule(
            "FINDINGS",
            "Putting findings right",
            "Each compliance finding has a remedy and a deadline. A finding left past its "
            "deadline is reported to the regulator.",
            "Bank of Ghana supervisory practice (R11)",
        ),
    )
}

LEGAL_RETENTION_YEARS = 5
RETURN_DUE_DAY = 15
FINDING_WORKING_DAYS = 10  # to put a compliance finding right
CONSENT_ANSWER_WORKING_DAYS = 3  # for a lender to send the consent forms asked for
