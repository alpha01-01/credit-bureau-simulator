"""Customer and account referencing (roadmap S3, S5; standard template P2.0a).

Customer referencing uses identifiers, in this order:
  1. the provider's own customer number (CustomerID, via ProviderCustomerLink);
  2. an identifier: Ghana Card, voter's ID, passport, driver's licence or SSNIT
     number for individuals; business registration number, then TIN, for
     businesses. A match whose identity does not agree is held for review;
  3. otherwise a new bureau customer.
Account referencing uses (institution, account number), which is unique. A
disbursement date that differs from the account on file cannot be loaded
(R004), except for overdrafts, as the standard says.

Conflicts (an identifier already held by another customer, an account held by
another customer) are kept as warnings for review; the provider's own keys win.

Fuzzy matching (P2.4) depends on the bureau's matching tooling. With STANDARD
tooling, a record that no identifier links is compared with the customers born
on the same day or sharing its surname and year of birth (businesses: registered
on the same day); ADVANCED tooling also
looks up customers by phone number and counts a shared number in the score. At
or above the bureau's auto-link threshold the record is linked; between its
review and auto-link thresholds the match is held for review; below, the record
becomes a new customer. Lower thresholds make fewer false splits and more false
merges; higher ones the reverse. ASSUMPTION A-048.

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
    LinkMethod,
    ProviderCustomerLink,
)
from apps.bureau.providers.models import Institution
from apps.bureau.quality.rules import MOBILE, Issue, parse_date
from apps.bureau.referencing.similarity import (
    Comparison,
    compare_businesses,
    compare_individuals,
    normalise,
)
from apps.bureau.submissions.models import Submission
from apps.standards.submission_template import CONSUMER_KINDS, FileKind


@dataclass(eq=False)
class NewCustomer:
    """Handle for a customer created in this run (unsaved models cannot be dict keys)."""

    customer: Customer
    identity: tuple[Any, ...] = ()


# An existing customer is known by its id; a new one by its handle.
CustomerKey = int | NewCustomer

_ID_FIELDS: dict[FileKind, tuple[tuple[str, str], ...]] = {
    FileKind.INDIVIDUAL: (
        ("NatIDNum", IdentifierType.GHANA_CARD),
        ("VotersIDNum", IdentifierType.VOTER_ID),
        ("PassportNum", IdentifierType.PASSPORT),
        ("DriverLicNum", IdentifierType.DRIVER_LICENCE),
        ("SSNum", IdentifierType.SSNIT),
    ),
    FileKind.COMMERCIAL: (
        ("BusRegNum", IdentifierType.BUSINESS_REGISTRATION),
        ("TINum", IdentifierType.TIN),
    ),
}
_PHONE_FIELDS: dict[FileKind, tuple[str, ...]] = {
    FileKind.INDIVIDUAL: ("MobileTel1", "MobileTel2"),
    FileKind.COMMERCIAL: ("OfficeTel1",),
}
OVERDRAFT = "121"  # the standard allows an overdraft's disbursement date to move


FUZZY_FIELD = "NAME_AND_BIRTH"  # what a fuzzy match question was matched on
PHONE_WEIGHT = 0.15  # share of a fuzzy score that a shared phone number carries (ADVANCED)


@dataclass(frozen=True)
class MatchQuestion:
    """A possible match that is not sure enough to link blindly.

    Either an identifier matched but the identity does not agree, or (fuzzy
    matching) no identifier matched but name and date of birth come close.
    """

    candidate: CustomerKey
    comparison: Comparison
    identifier_field: str


# How a reviewer settled a match question: the same customer as this candidate, or a
# different one (then the candidate is ruled out and, with fuzzy matching, the bureau looks
# for the right customer before creating a new one).
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
        organization = submission.organization
        self.tooling = organization.matching_tooling
        self.auto_link = organization.match_auto_link
        self.review = organization.match_review
        self.institution: Institution = submission.institution
        self.kind = kind
        # Cheque and judgment records identify a person as a consumer credit record does.
        self.consumer = kind in CONSUMER_KINDS
        self.subject = FileKind.INDIVIDUAL if self.consumer else FileKind.COMMERCIAL
        self.pending = pending

        numbers = {r["CustomerID"] for r in records}
        self.links: dict[str, CustomerKey] = dict(
            ProviderCustomerLink.objects.filter(
                institution=self.institution, provider_customer_number__in=numbers
            ).values_list("provider_customer_number", "customer_id")
        )
        values = {r[f] for r in records for f, _ in _ID_FIELDS[self.subject] if r.get(f)}
        types = [t for _, t in _ID_FIELDS[self.subject]]
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

        accounts = {r["FacilityAccNum"] for r in records}
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
        if self.consumer:
            for c, first, last, born in IndividualProfile.objects.filter(
                customer_id__in=candidates
            ).values_list("customer_id", "first_name", "last_name", "date_of_birth"):
                self.identity[c] = (first, last, born)
        else:
            for c, name, registered in BusinessProfile.objects.filter(
                customer_id__in=candidates
            ).values_list("customer_id", "registered_name", "registration_date"):
                self.identity[c] = (name, registered)

        # Fuzzy matching: customers born (or registered) on the records' dates, and with
        # ADVANCED tooling, customers who share a phone number with a record.
        self.born_on: dict[date | None, list[CustomerKey]] = defaultdict(list)
        self.family: dict[tuple[str, int], list[CustomerKey]] = defaultdict(list)
        self.on_phone: dict[str, list[CustomerKey]] = defaultdict(list)
        if self.tooling != "BASIC":
            self._load_fuzzy_pool(records)

    def _load_fuzzy_pool(self, records: list[dict[str, str]]) -> None:
        date_field = "DOB" if self.consumer else "RegistrationDate"
        dates = {d for r in records if (d := parse_date(r.get(date_field, ""))) is not None}
        pool: set[int] = set()
        if self.consumer:
            years = {d.year for d in dates}
            rows = IndividualProfile.objects.filter(
                customer__organization_id=self.organization_id, date_of_birth__year__in=years
            ).values_list("customer_id", "first_name", "last_name", "date_of_birth")
            wanted = {(normalise(r.get("Surname", "")), d.year) for r in records
                      if (d := parse_date(r.get("DOB", ""))) is not None}  # fmt: skip
            for c, first, last, born in rows:
                family = (normalise(last), born.year) if born else None
                if born not in dates and family not in wanted:
                    continue
                self.identity[c] = (first, last, born)
                self.born_on[born].append(c)
                if family:
                    self.family[family].append(c)
                pool.add(c)
        else:
            for c, name, registered in BusinessProfile.objects.filter(
                customer__organization_id=self.organization_id, registration_date__in=dates
            ).values_list("customer_id", "registered_name", "registration_date"):
                self.identity[c] = (name, registered)
                self.born_on[registered].append(c)
                pool.add(c)
        if self.tooling == "ADVANCED":
            phones = {r[f] for r in records for f in _PHONE_FIELDS[self.subject] if r.get(f)}
            for c, number in CustomerContact.objects.filter(
                customer__organization_id=self.organization_id, contact_value__in=phones
            ).values_list("customer_id", "contact_value"):
                self.on_phone[number].append(c)
                pool.add(c)
        for c, number in CustomerContact.objects.filter(customer_id__in=pool).values_list(
            "customer_id", "contact_value"
        ):
            self.contacts_of[c].add(number)

    def _fuzzy(
        self, values: dict[str, str], ruled_out: CustomerKey | None = None
    ) -> tuple[CustomerKey, Comparison] | None:
        """The closest customer by name and date of birth (and phone), if any."""
        date_field = "DOB" if self.consumer else "RegistrationDate"
        phones = [values[f] for f in _PHONE_FIELDS[self.subject] if values.get(f)]
        born = parse_date(values[date_field])
        candidates: list[CustomerKey] = list(self.born_on.get(born, []))
        if self.consumer and born is not None:
            candidates.extend(self.family.get((normalise(values["Surname"]), born.year), []))
        if self.tooling == "ADVANCED":
            for number in phones:
                candidates.extend(self.on_phone.get(number, []))
        best: tuple[CustomerKey, Comparison] | None = None
        seen: list[CustomerKey] = []
        for key in candidates:
            if any(_same(key, k) for k in seen) or (
                ruled_out is not None and _same(key, ruled_out)
            ):
                continue
            seen.append(key)
            comparison = self.compare(values, key)
            if self.tooling == "ADVANCED":
                shared = any(p in self.contacts_of[key] for p in phones)
                comparison = Comparison(
                    round((1 - PHONE_WEIGHT) * comparison.score + PHONE_WEIGHT * shared, 3),
                    [*comparison.reasons, "same phone number" if shared else "no phone in common"],
                )
            if best is None or comparison.score > best[1].score:
                best = (key, comparison)
        return best

    def _record_identity(self, values: dict[str, str]) -> tuple[Any, ...]:
        if self.consumer:
            return (values["FirstName"], values["Surname"], parse_date(values["DOB"]))
        return (values["BusinessName"], parse_date(values["RegistrationDate"]))

    def _identity_of(self, key: CustomerKey) -> tuple[Any, ...]:
        if isinstance(key, NewCustomer):
            return key.identity
        if key not in self.identity:
            # A customer that became a candidate during this run, e.g. one whose
            # identifier was recorded from an earlier row of the same file.
            self.identity[key] = self._load_identity(key)
        return self.identity[key]

    def _load_identity(self, customer_id: int) -> tuple[Any, ...]:
        if self.consumer:
            person = (
                IndividualProfile.objects.filter(customer_id=customer_id)
                .values_list("first_name", "last_name", "date_of_birth")
                .first()
            )
            return tuple(person) if person else ("", "", None)
        business = (
            BusinessProfile.objects.filter(customer_id=customer_id)
            .values_list("registered_name", "registration_date")
            .first()
        )
        return tuple(business) if business else ("", None)

    def compare(self, values: dict[str, str], key: CustomerKey) -> Comparison:
        record, customer = self._record_identity(values), self._identity_of(key)
        if self.consumer:
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
        linked = self.links.get(values["CustomerID"])
        found: CustomerKey | None = None
        found_field = ""
        for name, id_type in _ID_FIELDS[self.subject]:
            value = values.get(name, "")
            owner = self.identifiers.get((id_type, value)) if value else None
            if owner is None:
                continue
            if found is None:
                found, found_field = owner, name
            elif not _same(found, owner):
                issues.append(Issue("R001", name, value, "WARNING"))

        # Fuzzy matching, for a record nothing else settles.
        close = (
            self._fuzzy(values)
            if self.tooling != "BASIC" and linked is None and found is None and resolution is None
            else None
        )

        customer: CustomerKey
        # Once the provider's customer number is linked, it decides (as everywhere else);
        # a reviewer's resolution settles only a number the bureau has not linked yet,
        # e.g. the second loan of a borrower whose first case was decided earlier.
        if linked is None and resolution is not None and resolution[0] == SAME and resolution[1]:
            customer = resolution[1]
            self._link(values["CustomerID"], customer, LinkMethod.REVIEW_SAME)
        elif linked is None and resolution is not None and resolution[0] == DIFFERENT:
            other = (
                self._fuzzy(values, ruled_out=resolution[1]) if self.tooling != "BASIC" else None
            )
            if other is not None and other[1].score >= self.auto_link:
                customer = other[0]
                self._link(values["CustomerID"], customer, LinkMethod.FUZZY)
            else:
                customer = self._new_customer(values)
                self._link(values["CustomerID"], customer, LinkMethod.REVIEW_NEW)
        elif linked is not None:
            customer = linked
            if found is not None and not _same(found, linked):
                issues.append(Issue("R001", _ID_FIELDS[self.subject][0][0], "", "WARNING"))
        elif found is not None:
            comparison = self.compare(values, found)
            if comparison.score < self.auto_link:
                return MatchQuestion(found, comparison, found_field), []
            customer = found
            self._link(values["CustomerID"], customer, LinkMethod.IDENTIFIER)
        elif close is not None and close[1].score >= self.review:
            key, comparison = close
            if comparison.score < self.auto_link:
                if isinstance(key, int):
                    return MatchQuestion(key, comparison, FUZZY_FIELD), []
                customer = self._new_customer(values)  # no case on a customer not yet saved
                self._link(values["CustomerID"], customer, LinkMethod.NEW)
            else:
                customer = key
                self._link(values["CustomerID"], customer, LinkMethod.FUZZY)
        else:
            customer = self._new_customer(values)
            self._link(values["CustomerID"], customer, LinkMethod.NEW)

        # Record identifiers the bureau did not have yet; conflicts stay as warnings.
        for name, id_type in _ID_FIELDS[self.subject]:
            value = values.get(name, "")
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
            customer_type=(CustomerType.INDIVIDUAL if self.consumer else CustomerType.BUSINESS),
            source_submission=self.submission,
        )
        self.pending.customers.append(customer)
        if self.consumer:
            self.pending.individual_profiles.append(
                IndividualProfile(
                    customer=customer,
                    first_name=values["FirstName"],
                    middle_name=values["MiddleNames"],
                    last_name=values["Surname"],
                    date_of_birth=parse_date(values["DOB"]),
                    gender_code=values["Gender"],
                    employment_status=values["EmpType"],
                )
            )
        else:
            self.pending.business_profiles.append(
                BusinessProfile(
                    customer=customer,
                    registered_name=values["BusinessName"],
                    trading_name=values["TradingName"],
                    registration_number=values["BusRegNum"],
                    tin_number=values["TINum"],
                    sector_code=values["SubSecIndCode"],
                    registration_date=parse_date(values["RegistrationDate"]),
                )
            )
        new = NewCustomer(customer, self._record_identity(values))
        # Later rows of the same run can match it too.
        self.born_on[new.identity[-1]].append(new)
        if self.consumer and new.identity[-1] is not None:
            self.family[(normalise(new.identity[1]), new.identity[-1].year)].append(new)
        if self.tooling == "ADVANCED":
            for name in _PHONE_FIELDS[self.subject]:
                if values.get(name):
                    self.on_phone[values[name]].append(new)
        return new

    def _link(self, number: str, customer: CustomerKey, method: str) -> None:
        link = ProviderCustomerLink(
            organization_id=self.organization_id,
            institution=self.institution,
            provider_customer_number=number,
            source_submission=self.submission,
            method=method,
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
        for name in _PHONE_FIELDS[self.subject]:
            number = values.get(name, "")
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
        number = values["FacilityAccNum"]
        status = values["FacilityStatusCode"]
        account = self.accounts.get(number)
        if account is not None:
            disbursed = parse_date(values["DisbursementDate"])
            if (
                account.disbursement_date is not None
                and disbursed != account.disbursement_date
                and account.facility_type != OVERDRAFT
            ):
                # The standard: a changed disbursement date cannot be loaded (D18).
                issues.append(Issue("R004", "DisbursementDate", values["DisbursementDate"]))
                return account, issues
            holder = self.holders.get(number, account.customer_id)
            if not _same(holder, customer):
                issues.append(Issue("R002", "FacilityAccNum", number, "WARNING"))
            if account.account_status != status:
                account.account_status = status
                if account.pk:
                    self.pending.updated_accounts[account.pk] = account
            return account, issues

        branch_id = self.branches.get(values["BranchCode"])
        if values["BranchCode"] and branch_id is None:
            issues.append(Issue("R003", "BranchCode", values["BranchCode"], "WARNING"))
        account = CreditAccount(
            organization_id=self.organization_id,
            institution=self.institution,
            branch_id=branch_id,
            facility_account_number=number,
            facility_type=values["CreditFacilityType"],
            currency_code=values["AmountCurrency"],
            disbursement_date=parse_date(values["DisbursementDate"]),
            maturity_date=parse_date(values["MaturityDate"]),
            original_amount=Decimal(values["FacilityAmount"]),
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
