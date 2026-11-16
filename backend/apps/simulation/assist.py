"""Assistance toggles (P2.11; Document 07, Section 12.2).

Independent of difficulty, a learner may ask for:

* the estimated accuracy of a work item's decision: the chance the team's best
  person for that kind of item gets it right (the same model their work follows);
* the bureau's recommended decision: what its own evidence suggests. It never
  reads the hidden truth, so it can be wrong (ASSUMPTION A-069):
  - match review: the same customer when the match score is at least halfway
    from the review threshold to the auto-link threshold, else a different one;
  - triage: load the correction when one is proposed, else send it back;
  - dispute: uphold when the disputed accounts' provider was linked to this
    customer by a fuzzy match or a reviewer, not by an identifier;
* extended deadlines: work items due in ten working days instead of five;
* auto-pause on every event (the pause rules, all severities).
"""

from __future__ import annotations

from typing import Any

from apps.bureau.core.models import LinkMethod, ProviderCustomerLink
from apps.bureau.quality.models import CaseType, Decision, ReviewCase
from apps.org.models import Employee, Organization
from apps.workitems.models import WorkItem
from apps.workitems.resolution import fatigue, p_correct

EXTENDED_DAYS = 10


def estimated_accuracy(item: WorkItem, organization: Organization) -> dict[str, Any] | None:
    best = None
    for person in Employee.objects.filter(organization=organization, is_active=True).order_by(
        "employee_number"
    ):
        skill = float(person.skills.get(item.item_type, 0.5))
        p = p_correct(skill, item.difficulty, person.morale, fatigue(person.done_today))
        if best is None or p > best[0]:
            best = (p, f"{person.first_name} {person.last_name}")
    if best is None:
        return None
    return {"share": round(best[0], 3), "by": best[1]}


def recommend(case: ReviewCase, organization: Organization) -> dict[str, str] | None:
    if case.case_type == CaseType.MATCH_REVIEW:
        if case.score is None:
            return None
        middle = (organization.match_review + organization.match_auto_link) / 2
        if case.score >= middle:
            return {
                "decision": Decision.SAME_CUSTOMER,
                "why": f"The match score {case.score:.2f} is in the upper half of the review "
                f"band ({organization.match_review:.2f}-{organization.match_auto_link:.2f}).",
            }
        return {
            "decision": Decision.DIFFERENT_CUSTOMER,
            "why": f"The match score {case.score:.2f} is in the lower half of the review band.",
        }
    if case.case_type == CaseType.UNLOADABLE_TRIAGE:
        if case.proposal:
            return {
                "decision": Decision.CORRECT_AND_LOAD,
                "why": "The cleanser proposed a correction for every field at fault.",
            }
        return {"decision": Decision.RETURN_TO_PROVIDER, "why": "No correction was proposed."}
    if case.case_type == CaseType.DISPUTE and case.dispute is not None:
        providers = {code for code, _ in case.dispute.accounts}
        methods = set(
            ProviderCustomerLink.objects.filter(
                customer_id=case.candidate_customer_id or 0,
                institution__institution_code__in=providers,
            ).values_list("method", flat=True)
        )
        loose = methods & {LinkMethod.FUZZY, LinkMethod.REVIEW_SAME}
        if loose:
            return {
                "decision": Decision.UPHOLD_DISPUTE,
                "why": "The disputed provider's customer was joined to this person by a "
                "fuzzy match or a reviewer, not by an identifier.",
            }
        return {
            "decision": Decision.REJECT_DISPUTE,
            "why": "The disputed provider's customer was joined to this person by a matching "
            "identifier.",
        }
    return None
