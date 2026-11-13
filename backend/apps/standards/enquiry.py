"""Permissible purposes for credit enquiries.

ASSUMPTION A-025: placeholder list until consent and permissible-purpose
practice (reference R12) and the relevant provisions of the Credit Reporting
Act, 2007 (Act 726) are confirmed. Every enquiry must state a purpose and
carry the subscriber's reference to the subject's consent.
"""

from __future__ import annotations

PURPOSES: dict[str, str] = {
    "NEW_CREDIT": "Assessing an application for credit",
    "CREDIT_REVIEW": "Reviewing an existing credit facility",
    "COLLECTIONS": "Recovering a debt owed",
    "SUBJECT_REQUEST": "The data subject requesting their own report",
}
