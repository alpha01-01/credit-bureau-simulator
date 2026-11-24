"""Batch enquiries (P3.11): a subscriber's file of applicants, answered record by record.

Each record is searched exactly as a single enquiry is, and logged as an enquiry of its
own, so a batch's hits and misses are those single enquiries would give. The result
file lists each record with its outcome and the reference of the report delivered.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db import transaction

from apps.org.models import Organization

from .enquiries import enquire
from .models import BatchFile, BatchRecord

BATCH_ENQUIRY = "BATCH_ENQUIRY"


def answer_batch(
    organization: Organization,
    subscriber: Any,
    reference: str,
    rows: Iterable[tuple[str, str, str]],
    purpose: str,
    at: datetime,
) -> BatchFile:
    """Answer a file of (identifier type, identifier value, name) records."""
    with transaction.atomic():
        batch = BatchFile.objects.create(
            organization=organization, subscriber=subscriber, reference=reference, received_at=at
        )
        records, hits = [], 0
        for n, (id_type, id_value, name) in enumerate(rows, 1):
            enquiry = enquire(
                organization, subscriber, BATCH_ENQUIRY, purpose, f"{reference}-{n:05d}",
                id_type, id_value, name, at,
            )  # fmt: skip
            hits += enquiry.customer_id is not None
            records.append(
                BatchRecord(
                    batch=batch, row_number=n, identifier_type=id_type,
                    identifier_value=id_value, subject_name=name[:200], enquiry=enquiry,
                )
            )  # fmt: skip
        BatchRecord.objects.bulk_create(records)
        batch.records, batch.hits = len(records), hits
        batch.save(update_fields=["records", "hits"])
    return batch


def result_file(batch: BatchFile) -> str:
    """The file returned to the subscriber: one line per record, in the order sent."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["row", "identifier_type", "identifier_value", "name", "outcome",
                     "report_reference", "accounts"])  # fmt: skip
    for r in batch.rows.select_related("enquiry").order_by("row_number"):
        writer.writerow([
            r.row_number, r.identifier_type, r.identifier_value, r.subject_name,
            r.enquiry.outcome, r.enquiry.enquiry_reference, r.enquiry.accounts_reported,
        ])  # fmt: skip
    return out.getvalue()
