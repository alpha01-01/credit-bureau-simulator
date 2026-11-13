"""Customer and account referencing, pipeline v0 (roadmap S3).

Customer referencing uses exact identifiers only, in this order:
  1. the provider's own customer number (ProviderCustomerLink);
  2. the national identifier: Ghana Card for individuals; business
     registration number, then TIN, for businesses;
  3. otherwise a new bureau customer.
Account referencing uses (institution, account number), which is unique.

Conflicts (an identifier already held by another customer, an account held by
another customer) are kept as warnings for review; the provider's own keys win.
Partial and fuzzy matching arrive with work items in S5.

Exact matching has a real weakness that the game relies on: a provider that
sends another person's identifier links the record to that person.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from apps.bureau.core.models import (
    BusinessProfile,
    CreditAccount,
    Customer,
    CustomerContact,
    CustomerIdentifier,
    CustomerType,
    IdentifierType,
    IndividualProfile,
    ProviderCustomerLink,
)
from apps.bureau.providers.models import Institution
from apps.bureau.quality.rules import MOBILE, Issue, parse_date
from apps.bureau.referencing.similarity import (
    Comparison,
    compare_businesses,
    compare_individuals,
)
from apps.bureau.submissions.models import Submission
from apps.standards.submission_template import FileKind


@dataclass(eq=False)
class NewCustomer:
    """Handle for a customer created in this run (unsaved models cannot be dict keys)."""

    customer: Customer
    identity: tuple[Any, ...] = ()


# An existing customer is known by its id; a new one by its handle.
CustomerKey = int | NewCustomer

_ID_FIELDS: dict[FileKind, tuple[tuple[str, str], ...]] = {
    FileKind.INDIVIDUAL: (("GHANA_CARD_NUMBER", IdentifierType.GHANA_CARD),),
    FileKind.COMMERCIAL: (
        ("REGISTRATION_NUMBER", IdentifierType.BUSINESS_REGISTRATION),
        ("TIN", IdentifierType.TIN),
    ),
}
_PHONE_FIELDS: dict[FileKind, tuple[str, ...]] = {
    FileKind.INDIVIDUAL: ("MOBILE_NUMBER", "ALT_MOBILE_NUMBER"),
    FileKind.COMMERCIAL: ("CONTACT_NUMBER",),
}


@dataclass(frozen=True)
class MatchQuestion:
    """An identifier matched, but the identity does not agree well enough to link blindly."""

    candidate: CustomerKey
    comparison: Comparison
    identifier_field: str


# How a reviewer settled a match question: link to this customer id, or create a new customer.
Resolution = tuple[str, int | None]
SAME, DIFFERENT = "SAME_CUSTOMER", "DIFFERENT_CUSTOMER"


def _same(a: CustomerKey | None, b: CustomerKey | None) -> bool:
    return a == b  # ids by value, new customers by identity


def _set_customer(obj: object, key: CustomerKey) -> None:
    if isinstance(key, int):
        obj.customer_id = key  # type: ignore[attr-defined]
    else:
        obj.customer = key.customer  # type: ignore[attr-defined]


@dataclass
class Pending:
    """Everything referencing decided to create or change, saved together by the pipeline."""

    customers: list[Customer] = field(default_factory=list)
    individual_profiles: list[IndividualProfile] = field(default_factory=list)
    business_profiles: list[BusinessProfile] = field(default_factory=list)
    identifiers: list[CustomerIdentifier] = field(default_factory=list)
    contacts: list[CustomerContact] = field(default_factory=list)
    links: list[ProviderCustomerLink] = field(default_factory=list)
    accounts: list[CreditAccount] = field(default_factory=list)
    updated_accounts: dict[int, CreditAccount] = field(default_factory=dict)


class Referencer:
    """Resolves the records of one file against the bureau database (plus earlier rows)."""

    def __init__(
        self,
        submission: Submission,
        kind: FileKind,
        records: list[dict[str, str]],
        pending: Pending,
    ) -> None:
        self.submission = submission
        self.organization_id = submission.organization_id
        self.institution: Institution = submission.institution
        self.kind = kind
        self.pending = pending

        numbers = {r["CUSTOMER_NUMBER"] for r in records}
        self.links: dict[str, CustomerKey] = dict(
            ProviderCustomerLink.objects.filter(
                institution=self.institution, provider_customer_number__in=numbers
            ).values_list("provider_customer_number", "customer_id")
        )
        values = {r[f] for r in records for f, _ in _ID_FIELDS[kind] if r[f]}
        types = [t for _, t in _ID_FIELDS[kind]]
        self.identifiers: dict[tuple[str, str], CustomerKey] = {
            (t, v): c
            for t, v, c in CustomerIdentifier.objects.filter(
                organization_id=self.organization_id,
                identifier_type__in=types,
                identifier_value__in=values,
            ).values_list("identifier_type", "identifier_value", "customer_id")
        }
        known = {k for k in self.links.values()} | {k for k in self.identifiers.values()}
        self.ids_of: dict[CustomerKey, dict[str, str]] = defaultdict(dict)
        for t, v, c in CustomerIdentifier.objects.filter(
            customer_id__in=[k for k in known if isinstance(k, int)]
        ).values_list("identifier_type", "identifier_value", "customer_id"):
            self.ids_of[c][t] = v
        self.contacts_of: dict[CustomerKey, set[str]] = defaultdict(set)
        for c, v in CustomerContact.objects.filter(
            customer_id__in=[k for k in known if isinstance(k, int)]
        ).values_list("customer_id", "contact_value"):
            self.contacts_of[c].add(v)

        accounts = {r["ACCOUNT_NUMBER"] for r in records}
        # Who holds each account: existing holders by id, new accounts' holders by key.
        self.holders: dict[str, CustomerKey] = {}
        self.accounts: dict[str, CreditAccount] = {
            a.facility_account_number: a
            for a in CreditAccount.objects.filter(
                institution=self.institution, facility_account_number__in=accounts
            )
        }
        self.branches = dict(self.institution.branches.values_list("branch_code", "id"))

        # Identity of customers an identifier could match, for the similarity check.
        candidates = [k for k in self.identifiers.values() if isinstance(k, int)]
        self.identity: dict[CustomerKey, tuple[Any, ...]] = {}
        if kind is FileKind.INDIVIDUAL:
            for c, first, last, born in IndividualProfile.objects.filter(
                customer_id__in=candidates
            ).values_list("customer_id", "first_name", "last_name", "date_of_birth"):
                self.identity[c] = (first, last, born)
        else:
            for c, name, registered in BusinessProfile.objects.filter(
                customer_id__in=candidates
            ).values_list("customer_id", "registered_name", "registration_date"):
                self.identity[c] = (name, registered)

    def _record_identity(self, values: dict[str, str]) -> tuple[Any, ...]:
        if self.kind is FileKind.INDIVIDUAL:
            return (values["FIRST_NAME"], values["SURNAME"], parse_date(values["DATE_OF_BIRTH"]))
        return (values["REGISTERED_NAME"], parse_date(values["REGISTRATION_DATE"]))

    def _identity_of(self, key: CustomerKey) -> tuple[Any, ...]:
        return key.identity if isinstance(key, NewCustomer) else self.identity[key]

    def compare(self, values: dict[str, str], key: CustomerKey) -> Comparison:
        record, customer = self._record_identity(values), self._identity_of(key)
        if self.kind is FileKind.INDIVIDUAL:
            return compare_individuals(record, customer)
        return compare_businesses(record, customer)

    # --- customers ---------------------------------------------------------------

    def customer_for(
        self, values: dict[str, str], resolution: Resolution | None = None
    ) -> tuple[CustomerKey | MatchQuestion, list[Issue]]:
        """The bureau customer for a record, or a question for a reviewer.

        ``resolution`` settles a question asked earlier: link to a given
        customer, or treat the record as a different customer.
        """
        issues: list[Issue] = []
        linked = self.links.get(values["CUSTOMER_NUMBER"])
        found: CustomerKey | None = None
        found_field = ""
        for name, id_type in _ID_FIELDS[self.kind]:
            owner = self.identifiers.get((id_type, values[name])) if values[name] else None
            if owner is None:
                continue
            if found is None:
                found, found_field = owner, name
            elif not _same(found, owner):
                issues.append(Issue("R001", name, values[name], "WARNING"))

        customer: CustomerKey
        # Once the provider's customer number is linked, it decides (as everywhere else);
        # a reviewer's resolution settles only a number the bureau has not linked yet,
        # e.g. the second loan of a borrower whose first case was decided earlier.
        if linked is None and resolution is not None and resolution[0] == SAME and resolution[1]:
            customer = resolution[1]
            self._link(values["CUSTOMER_NUMBER"], customer)
        elif linked is None and resolution is not None and resolution[0] == DIFFERENT:
            customer = self._new_customer(values)
            self._link(values["CUSTOMER_NUMBER"], customer)
        elif linked is not None:
            customer = linked
            if found is not None and not _same(found, linked):
                issues.append(Issue("R001", _ID_FIELDS[self.kind][0][0], "", "WARNING"))
        elif found is not None:
            comparison = self.compare(values, found)
            if not comparison.auto_link:
                return MatchQuestion(found, comparison, found_field), []
            customer = found
            self._link(values["CUSTOMER_NUMBER"], customer)
        else:
            customer = self._new_customer(values)
            self._link(values["CUSTOMER_NUMBER"], customer)

        # Record identifiers the bureau did not have yet; conflicts stay as warnings.
        for name, id_type in _ID_FIELDS[self.kind]:
            value = values[name]
            if not value:
                continue
            owner = self.identifiers.get((id_type, value))
            held = self.ids_of[customer].get(id_type)
            if owner is None and held is None:
                self._identifier(customer, id_type, value)
            elif (
                (owner is not None and not _same(owner, customer))
                or (held is not None and held != value)
            ) and not any(i.rule_code == "R001" and i.field == name for i in issues):
                issues.append(Issue("R001", name, value, "WARNING"))

        self._contacts(customer, values)
        return customer, issues

    def _new_customer(self, values: dict[str, str]) -> NewCustomer:
        customer = Customer(
            organization_id=self.organization_id,
            customer_type=(
                CustomerType.INDIVIDUAL
                if self.kind is FileKind.INDIVIDUAL
                else CustomerType.BUSINESS
            ),
            source_submission=self.submission,
        )
        self.pending.customers.append(customer)
        if self.kind is FileKind.INDIVIDUAL:
            self.pending.individual_profiles.append(
                IndividualProfile(
                    customer=customer,
                    first_name=values["FIRST_NAME"],
                    middle_name=values["MIDDLE_NAMES"],
                    last_name=values["SURNAME"],
                    date_of_birth=parse_date(values["DATE_OF_BIRTH"]),
                    gender_code=values["GENDER"],
                    employment_status=values["EMPLOYMENT_TYPE"],
                )
            )
        else:
            self.pending.business_profiles.append(
                BusinessProfile(
                    customer=customer,
                    registered_name=values["REGISTERED_NAME"],
                    trading_name=values["TRADING_NAME"],
                    registration_number=values["REGISTRATION_NUMBER"],
                    tin_number=values["TIN"],
                    sector_code=values["SECTOR"],
                    registration_date=parse_date(values["REGISTRATION_DATE"]),
                )
            )
        return NewCustomer(customer, self._record_identity(values))

    def _link(self, number: str, customer: CustomerKey) -> None:
        link = ProviderCustomerLink(
            organization_id=self.organization_id,
            institution=self.institution,
            provider_customer_number=number,
            source_submission=self.submission,
        )
        _set_customer(link, customer)
        self.pending.links.append(link)
        self.links[number] = customer

    def _identifier(self, customer: CustomerKey, id_type: str, value: str) -> None:
        identifier = CustomerIdentifier(
            organization_id=self.organization_id,
            identifier_type=id_type,
            identifier_value=value,
            source_submission=self.submission,
        )
        _set_customer(identifier, customer)
        self.pending.identifiers.append(identifier)
        self.identifiers[(id_type, value)] = customer
        self.ids_of[customer][id_type] = value

    def _contacts(self, customer: CustomerKey, values: dict[str, str]) -> None:
        known = self.contacts_of[customer]
        for name in _PHONE_FIELDS[self.kind]:
            number = values[name]
            if not number or not MOBILE.fullmatch(number) or number in known:
                continue
            contact = CustomerContact(
                contact_type="MOBILE",
                contact_value=number,
                is_primary=not known,
                source_submission=self.submission,
            )
            _set_customer(contact, customer)
            self.pending.contacts.append(contact)
            known.add(number)

    # --- accounts ----------------------------------------------------------------

    def account_for(
        self, values: dict[str, str], customer: CustomerKey
    ) -> tuple[CreditAccount, list[Issue]]:
        issues: list[Issue] = []
        number = values["ACCOUNT_NUMBER"]
        status = values["ACCOUNT_STATUS"]
        account = self.accounts.get(number)
        if account is not None:
            holder = self.holders.get(number, account.customer_id)
            if not _same(holder, customer):
                issues.append(Issue("R002", "ACCOUNT_NUMBER", number, "WARNING"))
            if account.account_status != status:
                account.account_status = status
                if account.pk:
                    self.pending.updated_accounts[account.pk] = account
            return account, issues

        branch_id = self.branches.get(values["BRANCH_CODE"])
        if values["BRANCH_CODE"] and branch_id is None:
            issues.append(Issue("R003", "BRANCH_CODE", values["BRANCH_CODE"], "WARNING"))
        account = CreditAccount(
            organization_id=self.organization_id,
            institution=self.institution,
            branch_id=branch_id,
            facility_account_number=number,
            facility_type=values["FACILITY_TYPE"],
            currency_code=values["CURRENCY"],
            disbursement_date=parse_date(values["DISBURSEMENT_DATE"]),
            maturity_date=parse_date(values["MATURITY_DATE"]),
            original_amount=Decimal(values["ORIGINAL_AMOUNT"]),
            account_status=status,
            source_submission=self.submission,
        )
        _set_customer(account, customer)
        self.pending.accounts.append(account)
        self.accounts[number] = account
        self.holders[number] = customer
        return account, issues


def observed_accounts(account_ids: list[int], period: date) -> set[int]:
    """Accounts that already have a current observation for this reporting date."""
    from apps.bureau.core.models import AccountObservation

    return set(
        AccountObservation.objects.filter(
            credit_account_id__in=account_ids, reporting_date=period, is_current=True
        ).values_list("credit_account_id", flat=True)
    )
