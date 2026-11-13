"""Provider Data Quality Profiles (Document 07, Section 7.3).

A profile says how a provider's files deviate from its true book. Row-level
rates are probabilities per data row; ``template_drift`` is a monthly hazard
that the provider changes its extract without notice; ``late_rate`` is the
probability per month of missing the deadline.

ASSUMPTION A-016: all rates and the provider-to-profile assignment are
invented for gameplay until real data quality statistics are available.
Profiles will later change in response to the bureau's feedback, training
and SLA enforcement; for now they are fixed configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

# Fields that are realistically left blank, with relative weights.
INDIVIDUAL_BLANKABLE = {
    "GHANA_CARD_NUMBER": 4.0,
    "DATE_OF_BIRTH": 2.0,
    "MOBILE_NUMBER": 1.5,
    "GENDER": 1.0,
    "BRANCH_CODE": 0.5,
    "MATURITY_DATE": 0.5,
}
COMMERCIAL_BLANKABLE = {
    "TIN": 3.0,
    "REGISTRATION_NUMBER": 2.0,
    "CONTACT_NUMBER": 1.5,
    "BRANCH_CODE": 0.5,
    "MATURITY_DATE": 0.5,
}


@dataclass(frozen=True)
class DataQualityProfile:
    name: str
    file_format: str = "CSV"  # CSV | XLSX
    # Row-level defect rates.
    missing_field: float = 0.0
    phone_format: float = 0.0
    amount_format: float = 0.0
    name_typo: float = 0.0
    name_swap: float = 0.0
    wrong_identifier: float = 0.0
    stale_values: float = 0.0
    inconsistent_status: float = 0.0
    date_format: float = 0.0
    future_date: float = 0.0
    duplicate_row: float = 0.0
    omit_account: float = 0.0
    # Excel drops the leading zero of phone numbers typed as numbers.
    xlsx_numeric_phones: bool = False
    # Relative weights of which field is left blank (overrides the defaults).
    blank_weights: dict[str, float] = field(default_factory=dict)
    # File and submission level.
    template_drift: float = 0.0
    late_rate: float = 0.0
    late_days_max: int = 0
    arrival_days: tuple[int, int] = (5, 10)  # usual day of the month files arrive, inclusive

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


CLEAN = DataQualityProfile("CLEAN")

GOOD = DataQualityProfile(
    "GOOD", missing_field=0.004, phone_format=0.008, amount_format=0.0, name_typo=0.003,
    name_swap=0.001, wrong_identifier=0.0005, stale_values=0.002, inconsistent_status=0.001,
    date_format=0.001, future_date=0.0002, duplicate_row=0.001, omit_account=0.001,
    template_drift=0.01, late_rate=0.05, late_days_max=5, arrival_days=(3, 8),
)  # fmt: skip

AVERAGE = DataQualityProfile(
    "AVERAGE", missing_field=0.015, phone_format=0.03, amount_format=0.005, name_typo=0.01,
    name_swap=0.004, wrong_identifier=0.002, stale_values=0.008, inconsistent_status=0.004,
    date_format=0.005, future_date=0.001, duplicate_row=0.004, omit_account=0.004,
    template_drift=0.03, late_rate=0.15, late_days_max=10, arrival_days=(6, 10),
)  # fmt: skip

POOR = DataQualityProfile(
    "POOR", file_format="XLSX", missing_field=0.04, phone_format=0.06, amount_format=0.02,
    name_typo=0.025, name_swap=0.01, wrong_identifier=0.005, stale_values=0.02,
    inconsistent_status=0.01, date_format=0.015, future_date=0.003, duplicate_row=0.01,
    omit_account=0.01, xlsx_numeric_phones=True, template_drift=0.06, late_rate=0.35,
    late_days_max=20, arrival_days=(8, 10),
)  # fmt: skip

# Digital lenders: system-generated files (clean structure) but thin KYC.
DIGITAL = replace(
    GOOD,
    name="DIGITAL",
    missing_field=0.08,
    blank_weights={"GHANA_CARD_NUMBER": 3.0, "DATE_OF_BIRTH": 3.0, "GENDER": 1.0},
    name_typo=0.006,
    late_rate=0.02,
    arrival_days=(1, 4),
)

PRESETS: dict[str, DataQualityProfile] = {p.name: p for p in (CLEAN, GOOD, AVERAGE, POOR, DIGITAL)}

# The five providers reporting at the start of the Established scenario.
PROVIDER_PROFILES: dict[str, str] = {
    "ATB": "GOOD",
    "MRB": "GOOD",
    "UNS": "AVERAGE",
    "SWC": "DIGITAL",
    "HZF": "POOR",
}
REPORTING_PROVIDERS: tuple[str, ...] = tuple(PROVIDER_PROFILES)


def profile_for(lender_code: str, lender_type: str, sophistication: float) -> DataQualityProfile:
    """The profile for a lender: explicit assignment, else from its type and sophistication."""
    if lender_code in PROVIDER_PROFILES:
        return PRESETS[PROVIDER_PROFILES[lender_code]]
    if lender_type == "DIGITAL_LENDER":
        return DIGITAL
    if sophistication >= 0.7:
        return GOOD
    if sophistication >= 0.4:
        return AVERAGE
    return POOR
