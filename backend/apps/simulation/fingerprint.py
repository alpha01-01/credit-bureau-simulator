"""A checksum of everything a game holds, for replay testing (roadmap S4).

Storage paths are excluded (they contain the organisation id); file hashes
cover the content.

Rows are identified by natural keys (references, codes, account numbers, row
numbers) rather than database ids, and wall-clock audit columns (created_at)
are left out, so two games in the same database can be compared. Game-time
columns are included.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from apps.bureau.core.models import (
    AccountObservation,
    BusinessProfile,
    CourtJudgment,
    CreditAccount,
    CustomerContact,
    CustomerIdentifier,
    DishonouredCheque,
    Enquiry,
    IndividualProfile,
    ProviderCustomerLink,
)
from apps.bureau.core.models import Customer as BureauCustomer
from apps.bureau.quality.models import (
    CleansingRule,
    CorrectionRecord,
    Dispute,
    RegulatoryReturn,
    ReviewCase,
    TransformationLog,
    ValidationIssue,
)
from apps.bureau.reports.models import BatchFile, BatchRecord, CreditScore
from apps.bureau.submissions.models import (
    FeedbackReport,
    ProcessingRun,
    StagingRecord,
    Submission,
    SubmissionFile,
    TemplateMapping,
)
from apps.commercial.models import Contract, UsageRecord
from apps.finance.models import (
    BankStatement,
    Budget,
    Invoice,
    JournalLine,
    MonthClose,
    Payment,
    StatementLine,
    SupplierBill,
)
from apps.org.models import Employee, Organization
from apps.workitems.models import WorkItem

from .models import (
    BoardReview,
    Candidate,
    ComplianceFinding,
    ConsentCheck,
    Consequence,
    DataQualityReview,
    EnquiryJudgement,
    FundingRequest,
    Game,
    Incident,
    LenderResearch,
    LendingDecision,
    MissionState,
    Notice,
    Onboarding,
    OnboardingStep,
    PlayerAction,
    ProductDevelopment,
    Proposal,
    ProviderRelationship,
    RegulatorFinding,
    RegulatorStanding,
    Sanction,
    ScheduledEvent,
    ScoreModel,
    SolvencyState,
    SubscriberView,
    SupportTicket,
    TickLog,
)


class _Hasher:
    """The whole-game digest, and one per section to say where two games part ways."""

    def __init__(self) -> None:
        self.whole = hashlib.sha256()
        self.parts: dict[str, str] = {}


def _section(h: _Hasher, name: str, rows: Iterable[Iterable[Any]]) -> int:
    count = 0
    part = hashlib.sha256()
    h.whole.update(f"[{name}]".encode())
    for row in rows:
        data = json.dumps(list(row), default=str, sort_keys=True).encode()
        h.whole.update(data)
        part.update(data)
        count += 1
    h.whole.update(f"[{name}:{count}]".encode())
    h.parts[name] = f"{count}:{part.hexdigest()[:16]}"
    return count


def fingerprint(game: Game) -> str:
    """One digest of everything the game owns: equal digests, identical games."""
    return _fingerprint(game).whole.hexdigest()


def fingerprint_parts(game: Game) -> dict[str, str]:
    """Row count and digest per section, to find where two games differ."""
    return _fingerprint(game).parts


def differences(a: Game, b: Game) -> list[str]:
    """The sections in which two games differ, with each one's rows and digest."""
    pa, pb = fingerprint_parts(a), fingerprint_parts(b)
    return [f"{k}: {pa.get(k)} != {pb.get(k)}" for k in pa if pa.get(k) != pb.get(k)]


def _fingerprint(game: Game) -> _Hasher:
    org = game.organization_id
    h = _Hasher()
    sub = "submission__submission_reference"
    # The bureau's settings as stored: an in-memory copy may still hold a default
    # (Decimal("20000") where the database gives Decimal("20000.00")).
    bureau = Organization.objects.get(pk=org)
    _section(
        h,
        "game",
        [(game.clock_start, game.current_tick, game.status, game.speed,
          bureau.rejection_policy, game.pause_severities, game.pause_on_deadlines,
          bureau.rule_overrides, bureau.matching_tooling, bureau.match_auto_link,
          bureau.match_review, game.role, bureau.retention_years, bureau.bill_approval_limit,
          bureau.closed_through, bureau.support_staff, game.scenario, game.difficulty,
          game.parameters, bureau.office, bureau.has_systems, bureau.it_ready_on)],
    )  # fmt: skip
    _section(
        h,
        "ticks",
        TickLog.objects.filter(game=game)
        .order_by("tick")
        .values_list("tick", "sim_time", "events_processed"),
    )
    _section(
        h,
        "events",
        ScheduledEvent.objects.filter(game=game)
        .order_by("sequence")
        .values_list("sequence", "event_type", "due_tick", "payload", "status", "processed_tick"),
    )
    _section(
        h,
        "cleansing_rules",
        CleansingRule.objects.filter(organization_id=org)
        .order_by("code")
        .values_list("code", "field", "action", "find", "replace",
                     "institution__institution_code", "is_active", "created_at"),
    )  # fmt: skip
    _section(
        h,
        "feedback",
        FeedbackReport.objects.filter(organization_id=org)
        .order_by("pk")
        .values_list("submission__submission_reference", "sent_at", "report"),
    )
    _section(
        h,
        "mappings",
        TemplateMapping.objects.filter(organization_id=org)
        .order_by("pk")
        .values_list("institution__institution_code", "file_kind", "received", "columns",
                     "created_at", "created_by"),
    )  # fmt: skip
    _section(
        h,
        "notices",
        Notice.objects.filter(game=game)
        .order_by("tick", "pk")
        .values_list("tick", "sim_time", "kind", "severity", "title", "detail", "drill",
                     "is_deadline", "paused"),
    )  # fmt: skip
    _section(
        h,
        "lending",
        LendingDecision.objects.filter(game=game)
        .order_by("tick", "application__lender__code", "application__seq")
        .values_list("application__lender__code", "application__period", "application__seq",
                     "subscriber_code", "checked", "flagged", "lent", "tick"),
    )  # fmt: skip
    _section(
        h,
        "disputes",
        Dispute.objects.filter(organization_id=org)
        .order_by("dispute_number")
        .values_list("dispute_number", "customer__customer_reference",
                     "enquiry__enquiry_reference", "subject_name", "claim", "accounts",
                     "received_at", "due_date", "status", "outcome", "resolved_at",
                     "resolved_by"),
    )  # fmt: skip
    _section(
        h,
        "corrections",
        CorrectionRecord.objects.filter(organization_id=org)
        .order_by("pk")
        .values_list("kind", "credit_account__facility_account_number",
                     "from_customer__customer_reference", "to_customer__customer_reference",
                     "dispute__dispute_number", "reason", "approved_by", "corrected_at"),
    )  # fmt: skip
    _section(
        h,
        "regulator",
        RegulatorFinding.objects.filter(game=game)
        .order_by("raised_at", "reference")
        .values_list("kind", "reference", "raised_at", "detail"),
    )
    _section(
        h,
        "standing",
        RegulatorStanding.objects.filter(game=game).values_list("level", "history"),
    )
    _section(
        h,
        "providers",
        ProviderRelationship.objects.filter(game=game)
        .order_by("provider_code")
        .values_list("provider_code", "quality", "progress", "goodwill", "trainings",
                     "penalties", "updated_at", "history"),
    )  # fmt: skip
    _section(
        h,
        "consequences",
        Consequence.objects.filter(game=game)
        .order_by("tick", "pk")
        .values_list("tick", "effect", "enquiry__enquiry_reference", "subscriber_code",
                     "accounts", "cause", "work_item__item_number", "provider",
                     "provider_customer", "detail"),
    )  # fmt: skip
    _section(
        h,
        "reviews",
        DataQualityReview.objects.filter(game=game)
        .order_by("period")
        .values_list("period", "tick", "figures", "refs"),
    )
    _section(
        h,
        "actions",
        PlayerAction.objects.filter(game=game)
        .order_by("sequence")
        .values_list("sequence", "tick", "action_type", "payload"),
    )
    _section(
        h,
        "submissions",
        Submission.objects.filter(organization_id=org)
        .order_by("submission_reference")
        .values_list(
            "submission_reference", "institution__institution_code", "reporting_period",
            "due_date", "received_at", "submission_status", "total_records",
        ),
    )  # fmt: skip
    _section(
        h,
        "files",
        SubmissionFile.objects.filter(submission__organization_id=org)
        .order_by(sub, "storage_path")
        .values_list(
            sub, "file_name", "file_kind", "file_hash", "received_at",
            "file_status", "rejection_reason",
        ),
    )  # fmt: skip
    _section(
        h,
        "runs",
        ProcessingRun.objects.filter(submission__organization_id=org)
        .order_by(sub, "run_number")
        .values_list(
            sub, "run_number", "started_at", "completed_at", "processing_status",
            "records_received", "records_accepted", "records_unloadable", "records_duplicated",
            "customers_created", "accounts_created", "observations_created",
        ),
    )  # fmt: skip
    run_sub = "run__submission__submission_reference"
    _section(
        h,
        "staging",
        StagingRecord.objects.filter(run__submission__organization_id=org)
        .order_by(run_sub, "run__run_number", "file__storage_path", "source_row_number")
        .values_list(
            run_sub, "run__run_number", "file__file_name", "source_row_number", "raw",
            "changes", "record_status", "duplicate_of_row",
        ),
    )  # fmt: skip
    _section(
        h,
        "issues",
        ValidationIssue.objects.filter(run__submission__organization_id=org)
        .order_by(run_sub, "run__run_number", "file__storage_path", "source_row_number", "rule_code", "field", "value")
        .values_list(
            run_sub, "run__run_number", "file__file_name", "source_row_number", "field",
            "rule_code", "severity", "value",
        ),
    )  # fmt: skip
    rec = "record__run__submission__submission_reference"
    _section(
        h,
        "transformations",
        TransformationLog.objects.filter(record__run__submission__organization_id=org)
        # A field changed twice (cleansed, then corrected by a reviewer) has two rows:
        # without "pk" (the order they were made) the two came back in either order,
        # which failed one full test run in ten (P3.0).
        .order_by(rec, "record__file__storage_path", "record__source_row_number", "field", "pk")
        .values_list(
            rec, "record__file__file_name", "record__source_row_number", "field", "rule_code",
            "value_before", "value_after",
        ),
    )  # fmt: skip
    _section(
        h,
        "customers",
        BureauCustomer.objects.filter(organization_id=org)
        .order_by("customer_reference")
        .values_list(
            "customer_reference", "customer_type", "record_status",
            "source_submission__submission_reference",
        ),
    )  # fmt: skip
    ref = "customer__customer_reference"
    _section(
        h,
        "individuals",
        IndividualProfile.objects.filter(customer__organization_id=org)
        .order_by(ref)
        .values_list(ref, "first_name", "middle_name", "last_name", "date_of_birth",
                     "gender_code", "employment_status"),
    )  # fmt: skip
    _section(
        h,
        "businesses",
        BusinessProfile.objects.filter(customer__organization_id=org)
        .order_by(ref)
        .values_list(ref, "registered_name", "trading_name", "registration_number",
                     "tin_number", "sector_code", "registration_date"),
    )  # fmt: skip
    _section(
        h,
        "identifiers",
        CustomerIdentifier.objects.filter(organization_id=org)
        .order_by("identifier_type", "identifier_value")
        .values_list("identifier_type", "identifier_value", ref),
    )
    _section(
        h,
        "contacts",
        CustomerContact.objects.filter(customer__organization_id=org)
        .order_by(ref, "contact_value")
        .values_list(ref, "contact_type", "contact_value", "is_primary"),
    )
    _section(
        h,
        "links",
        ProviderCustomerLink.objects.filter(organization_id=org)
        .order_by("institution__institution_code", "provider_customer_number")
        .values_list("institution__institution_code", "provider_customer_number", ref),
    )
    inst = "institution__institution_code"
    _section(
        h,
        "accounts",
        CreditAccount.objects.filter(organization_id=org)
        .order_by(inst, "facility_account_number")
        .values_list(
            inst, "facility_account_number", ref, "branch__branch_code", "facility_type",
            "currency_code", "disbursement_date", "maturity_date", "original_amount",
            "account_status",
        ),
    )  # fmt: skip
    acc = "credit_account__"
    _section(
        h,
        "observations",
        AccountObservation.objects.filter(credit_account__organization_id=org)
        .order_by(
            f"{acc}{inst}", f"{acc}facility_account_number", "reporting_date", "is_current", "pk"
        )
        .values_list(
            f"{acc}{inst}", f"{acc}facility_account_number", "reporting_date",
            "outstanding_balance", "arrears_amount", "days_past_due", "instalment_amount",
            "amount_paid", "facility_status", "asset_classification", "is_written_off",
            "is_current", "source_file__file_name", "source_row_number",
        ),
    )  # fmt: skip
    _section(
        h,
        "cheques",
        DishonouredCheque.objects.filter(organization_id=org)
        .order_by(inst, "account_number", "cheque_number")
        .values_list(
            inst, "account_number", "cheque_number", ref, "date_issued", "date_bounced",
            "reason_code", "currency_code", "amount", "source_file__file_name",
            "source_row_number",
        ),
    )  # fmt: skip
    _section(
        h,
        "judgments",
        CourtJudgment.objects.filter(organization_id=org)
        .order_by(inst, "case_number")
        .values_list(
            inst, "case_number", ref, "court_name", "court_type", "filing_date", "case_type",
            "case_reason", "currency_code", "amount", "source_file__file_name",
            "source_row_number",
        ),
    )  # fmt: skip
    _section(
        h,
        "cases",
        ReviewCase.objects.filter(organization_id=org)
        .order_by("case_number")
        .values_list(
            "case_number", "case_type", "record__file__file_name", "record__source_row_number",
            "candidate_customer__customer_reference", "score", "evidence", "proposal", "status",
            "opened_at", "decision", "decided_by", "decided_at",
        ),
    )  # fmt: skip
    _section(
        h,
        "work_items",
        WorkItem.objects.filter(organization_id=org)
        .order_by("item_number")
        .values_list(
            "item_number", "item_type", "difficulty", "created_tick", "due_tick", "status",
            "assignee__employee_number", "started_tick", "minutes_remaining", "correct_decision",
            "resolved_tick", "resolved_by", "decision", "is_correct", "confidence", "explanation",
        ),
    )  # fmt: skip
    _section(
        h,
        "employees",
        Employee.objects.filter(organization_id=org)
        .order_by("employee_number")
        .values_list(
            "employee_number", "first_name", "last_name", "job_title", "skills", "experience",
            "morale", "work_day", "done_today", "monthly_salary", "is_active", "away_until_tick",
            "has_system_access",
        ),
    )  # fmt: skip
    _section(
        h,
        "departments",
        [
            *Candidate.objects.filter(game=game)
            .order_by("period", "number")
            .values_list("period", "number", "first_name", "last_name", "job_title", "skills",
                         "asking_salary", "hired"),
            *Proposal.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "lender_code", "unit_price", "sent_at", "status",
                         "answered_at", "term_months", "service_level", "monthly_minimum",
                         "discount_threshold", "discount_rate", "counter_price"),
            *SupportTicket.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "source", "subscriber_code", "topic", "opened_on",
                         "opened_tick", "due_on", "answered_on", "answered_tick"),
            *ProductDevelopment.objects.filter(game=game)
            .order_by("code")
            .values_list("code", "started_on", "started_tick", "ready_on", "launched_on", "cost"),
            *LenderResearch.objects.filter(game=game)
            .order_by("lender_code")
            .values_list("lender_code", "requested_tick", "ready_on", "findings", "reported",
                         "meeting_requested_tick", "meeting_on", "meeting_notes",
                         "meeting_reported"),
            *Onboarding.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "lender_code", "proposal__number", "unit_price", "signed_on",
                         "give_up_on", "status", "live_on", "ended_on"),
            *OnboardingStep.objects.filter(onboarding__game=game)
            .order_by("onboarding__number", "position")
            .values_list("onboarding__number", "position", "department", "code", "status",
                         "ready_on", "due_on", "progress", "held", "done_on", "done_tick",
                         "done_by", "outcome", "evidence"),
            *Incident.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "kind", "started_tick", "ends_tick", "response", "detail"),
            (game.organization.it_capacity,),
            *SolvencyState.objects.filter(game=game).values_list(
                "stage", "creditors_deadline", "history"
            ),
            *BoardReview.objects.filter(game=game)
            .order_by("period")
            .values_list("period", "tick", "confidence", "parts", "verdict", "detail"),
            *FundingRequest.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "requested_at", "amount", "granted", "reason"),
            (game.status == "ENDED", game.ended_tick, game.ended_reason),
            (game.campaign, game.assist_accuracy, game.assist_recommend,
             game.assist_extended_deadlines),
            *MissionState.objects.filter(game=game)
            .order_by("code")
            .values_list("code", "answers", "completed_tick", "debrief"),
            *ScoreModel.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "term", "observation_date", "window_months", "features",
                         "seed", "spec", "results", "status", "built_tick", "deployed_tick"),
            *ComplianceFinding.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "kind", "reference", "detail", "raised_tick", "raised_at",
                         "resolved_tick", "due_date", "remedy", "escalated"),
            *ConsentCheck.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "subscriber_code", "month", "sample", "requested_tick",
                         "answer_tick", "answered", "missing"),
            *Sanction.objects.filter(game=game)
            .order_by("number")
            .values_list("number", "subscriber_code", "kind", "tick", "until_tick"),
            *RegulatoryReturn.objects.filter(organization_id=org)
            .order_by("period")
            .values_list("period", "due_date", "filed_at", "filed_by", "figures"),
            *Contract.objects.filter(subscriber__organization_id=org)
            .order_by("subscriber__subscriber_code", "start_date")
            .values_list("subscriber__subscriber_code", "subscriber__is_active", "unit_price",
                         "start_date", "end_date", "term_months", "service_level",
                         "monthly_minimum", "discount_threshold", "discount_rate",
                         "subscriber__billing_ready"),
        ],
    )  # fmt: skip
    _section(
        h,
        "scores",
        CreditScore.objects.filter(organization_id=org)
        .order_by("customer__customer_reference")
        .values_list(
            "customer__customer_reference", "as_of", "score", "band", "reasons", "terms", "model"
        ),
    )
    _section(
        h,
        "batches",
        [
            *BatchFile.objects.filter(organization_id=org)
            .order_by("reference")
            .values_list("reference", "subscriber__subscriber_code", "received_at", "records",
                         "hits"),
            *BatchRecord.objects.filter(batch__organization_id=org)
            .order_by("batch__reference", "row_number")
            .values_list("batch__reference", "row_number", "identifier_type", "identifier_value",
                         "subject_name", "enquiry__enquiry_reference"),
        ],
    )  # fmt: skip
    _section(
        h,
        "enquiries",
        Enquiry.objects.filter(organization_id=org)
        .order_by("enquiry_reference")
        .values_list(
            "enquiry_reference", "subscriber__subscriber_code", "product_code", "purpose",
            "consent_reference", "identifier_type", "identifier_value", "subject_name",
            "enquired_at", "outcome", "customer__customer_reference", "accounts_reported", "report",
        ),
    )  # fmt: skip
    _section(
        h,
        "usage",
        UsageRecord.objects.filter(organization_id=org)
        .order_by("usage_at", "subscriber__subscriber_code", "product__product_code",
                  "enquiry__enquiry_reference")
        .values_list(
            "enquiry__enquiry_reference", "subscriber__subscriber_code", "product__product_code",
            "quantity", "unit_price", "usage_at", "invoiced",
        ),
    )  # fmt: skip
    _section(
        h,
        "subscriber_views",
        SubscriberView.objects.filter(game=game)
        .order_by("subscriber_code")
        .values_list(
            "subscriber_code", "perceived_value", "opportunities", "enquiries", "hits",
            "wrong_person", "at_risk", "score_uptake",
        ),
    )  # fmt: skip
    _section(
        h,
        "enquiry_judgements",
        EnquiryJudgement.objects.filter(game=game)
        .order_by("enquiry__enquiry_reference")
        .values_list(
            "enquiry__enquiry_reference", "should_hit", "hit", "correct_person", "outcome",
            "grounds_held",
        ),
    )  # fmt: skip
    _section(
        h,
        "journal",
        JournalLine.objects.filter(entry__organization_id=org)
        .order_by("entry__journal_reference", "account__code", "debit", "credit", "memo")
        .values_list(
            "entry__journal_reference", "entry__transaction_date", "entry__description",
            "entry__source_type", "entry__source_reference", "entry__posted_at",
            "entry__reversal_of__journal_reference", "account__code", "debit", "credit", "memo",
        ),
    )  # fmt: skip
    _section(
        h,
        "invoices",
        Invoice.objects.filter(organization_id=org)
        .order_by("invoice_number")
        .values_list(
            "invoice_number", "subscriber__subscriber_code", "period_start", "period_end",
            "issue_date", "due_date", "subtotal", "tax", "total",
        ),
    )  # fmt: skip
    _section(
        h,
        "payments",
        Payment.objects.filter(organization_id=org)
        .order_by("reference")
        .values_list("reference", "invoice__invoice_number", "amount", "received_on"),
    )
    # The Finance department (P3.8).
    _section(
        h,
        "supplier_bills",
        SupplierBill.objects.filter(organization_id=org)
        .order_by("number")
        .values_list(
            "number", "supplier_code", "reference", "account_code", "amount", "bill_date",
            "due_date", "status", "approved_by", "paid_on", "late_fee",
            "journal__journal_reference", "payment_journal__journal_reference",
            "duplicate_of__number",
        ),
    )  # fmt: skip
    _section(
        h,
        "bank_statements",
        BankStatement.objects.filter(organization_id=org)
        .order_by("period")
        .values_list(
            "period", "opening_balance", "closing_balance", "received_at", "reconciled_at"
        ),
    )
    _section(
        h,
        "statement_lines",
        StatementLine.objects.filter(statement__organization_id=org)
        .order_by("statement__period", "line_number")
        .values_list(
            "statement__period", "line_number", "value_date", "description", "reference",
            "amount", "cause", "entry__journal_reference", "status",
            "resolution__journal_reference", "corrects__line_number", "answer_tick", "answer",
        ),
    )  # fmt: skip
    _section(
        h,
        "budgets",
        Budget.objects.filter(organization_id=org)
        .order_by("cost_centre", "effective_from")
        .values_list("cost_centre", "effective_from", "amount"),
    )
    _section(
        h,
        "month_closes",
        MonthClose.objects.filter(organization_id=org)
        .order_by("period")
        .values_list("period", "budget_reviewed_at", "closed_at"),
    )
    return h
