"""Billing usage for enquiries (roadmap S6; invoiced in S7)."""

from __future__ import annotations

from django.db.models import Q

from apps.bureau.core.models import Enquiry

from .models import Contract, Product, UsageRecord


class NoContract(Exception):
    pass


def active_contract(subscriber_id: int, product: Product, on: object) -> Contract:
    contract = (
        Contract.objects.filter(subscriber_id=subscriber_id, product=product, start_date__lte=on)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=on))
        .order_by("-start_date", "-pk")
        .first()
    )
    if contract is None:
        raise NoContract(f"Subscriber {subscriber_id} has no contract for {product.product_code}")
    return contract


def record_usage(
    enquiry: Enquiry,
    product: Product | None = None,
    contract: Contract | None = None,
    save: bool = True,
) -> UsageRecord:
    """One billable unit per enquiry, priced by the subscriber's contract.

    A caller that has already looked up the product and the contract in force
    may pass them in. With ``save=False`` the record is returned unsaved, for a caller
    that saves many at once (P4.0: the simulation's tick).
    """
    if product is None:
        product = Product.objects.get(
            organization_id=enquiry.organization_id, product_code=enquiry.product_code
        )
    if contract is None:
        contract = active_contract(enquiry.subscriber_id, product, enquiry.enquired_at.date())
    record = UsageRecord(
        organization_id=enquiry.organization_id,
        subscriber_id=enquiry.subscriber_id,
        contract=contract,
        enquiry=enquiry,
        product=product,
        quantity=1,
        unit_price=contract.unit_price,
        usage_at=enquiry.enquired_at,
    )
    if save:
        record.save()
    return record
