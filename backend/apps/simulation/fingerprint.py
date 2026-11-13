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
    CreditAccount,
    CustomerContact,
    CustomerIdentifier,
    IndividualProfile,
    ProviderCustomerLink,
)
from apps.bureau.core.models import Customer as BureauCustomer
from apps.bureau.quality.models import ReviewCase, TransformationLog, ValidationIssue
from apps.bureau.submissions.models import ProcessingRun, StagingRecord, Submission, SubmissionFile
from apps.org.models import Employee
from apps.workitems.models import WorkItem

from .models import Game, PlayerAction, ScheduledEvent, TickLog


def _section(h: Any, name: str, rows: Iterable[Iterable[Any]]) -> int:
    count = 0
    h.update(f"[{name}]".encode())
    for row in rows:
        h.update(json.dumps(list(row), default=str, sort_keys=True).encode())
        count += 1
    h.update(f"[{name}:{count}]".encode())
    return count


def fingerprint(game: Game) -> str:
    org = game.organization_id
    h = hashlib.sha256()
    sub = "submission__submission_reference"
    _section(h, "game", [(game.clock_start, game.current_tick, game.status, game.speed)])
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
            "cleansed", "record_status", "duplicate_of_row",
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
        .order_by(rec, "record__file__storage_path", "record__source_row_number", "field")
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
        .order_by(f"{acc}{inst}", f"{acc}facility_account_number", "reporting_date", "is_current")
        .values_list(
            f"{acc}{inst}", f"{acc}facility_account_number", "reporting_date",
            "outstanding_balance", "arrears_amount", "days_past_due", "instalment_amount",
            "amount_paid", "facility_status", "asset_classification", "is_written_off",
            "is_current", "source_file__file_name", "source_row_number",
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
            "item_number", "item_type", "difficulty", "created_tick", "status",
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
            "morale", "work_day", "done_today",
        ),
    )  # fmt: skip
    return h.hexdigest()
