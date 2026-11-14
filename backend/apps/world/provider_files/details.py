"""Customer details that providers hold but the world generator does not model.

The standard template asks for marital status, addresses, occupation and
employer, which the world's borrowers do not carry. They are derived here,
deterministically from the world seed and the borrower's number, so the same
person has the same details at every lender and in every month.

ASSUMPTION A-037: the distributions and name lists below are placeholders.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from apps.world.generation.rng import stream

STREETS = (
    "Ring Road", "Liberation Road", "Independence Avenue", "Kwame Nkrumah Avenue",
    "Spintex Road", "Oxford Street", "Kumasi Road", "Harper Road", "Prempeh II Street",
    "Station Road", "Market Street", "Church Street", "Hospital Road", "School Road",
    "Zongo Junction Road", "Lake Road", "Airport Road", "Mission Street",
)  # fmt: skip

PUBLIC_EMPLOYERS = (
    "Ghana Education Service", "Ghana Health Service", "Ghana Police Service",
    "Controller and Accountant-General's Department", "Local Government Service",
    "Ghana Revenue Authority", "Electricity Company of Ghana",
)  # fmt: skip

PRIVATE_EMPLOYERS = (
    "Goldfields Logistics Ltd", "Coastal Foods Ltd", "Sunrise Supermarkets Ltd",
    "Prime Telecom Services Ltd", "Heritage Insurance Ltd", "Unity Construction Ltd",
    "Royal Hotels Ltd", "Bright Pharmaceuticals Ltd", "Eagle Security Services Ltd",
)  # fmt: skip

OCCUPATIONS: dict[str, tuple[str, ...]] = {
    "SALARIED_PUBLIC": ("Teacher", "Nurse", "Civil Servant", "Police Officer", "Administrator"),
    "SALARIED_PRIVATE": ("Accountant", "Sales Executive", "Engineer", "Driver", "Bank Officer"),
    "SELF_EMPLOYED": ("Trader", "Tailor", "Hairdresser", "Mechanic", "Caterer"),
    "INFORMAL": ("Market Trader", "Artisan", "Farmer", "Hawker"),
    "RETIRED": ("Pensioner",),
    "UNEMPLOYED": ("None",),
}

# World employment type -> standard EmpType code.
EMPLOYMENT_CODE = {
    "SALARIED_PUBLIC": "101", "SALARIED_PRIVATE": "101", "SELF_EMPLOYED": "104",
    "INFORMAL": "104", "RETIRED": "106", "UNEMPLOYED": "102",
}  # fmt: skip

# World sector -> standard (sector, sub-sector).
SECTOR_CODES = {
    "AGRICULTURE": ("10", "104"), "TRADE": ("60", "603"), "MANUFACTURING": ("30", "309"),
    "CONSTRUCTION": ("40", "402"), "TRANSPORT": ("70", "702"), "HOSPITALITY": ("80", "803"),
    "SERVICES": ("80", "802"), "ICT": ("70", "706"), "FINANCE": ("60", "607"),
    "EDUCATION": ("80", "806"), "HEALTH": ("80", "804"),
    "PUBLIC_ADMINISTRATION": ("80", "806"), "MINING": ("20", "206"),
}  # fmt: skip


def _pick(rng: np.random.Generator, options: tuple[str, ...]) -> str:
    return options[int(rng.integers(len(options)))]


def person_details(
    seed: int, person_seq: int, employment: str, born: date, town: str, as_of: date
) -> dict[str, str]:
    rng = stream(seed, f"person-details:{person_seq}")
    age = (as_of - born).days / 365.25
    if age < 25:
        marital = "M" if rng.random() < 0.15 else "S"
    elif age < 40:
        marital = str(rng.choice(["M", "S", "D", "P"], p=[0.6, 0.33, 0.04, 0.03]))
    else:
        marital = str(rng.choice(["M", "W", "D", "P", "S"], p=[0.7, 0.1, 0.08, 0.04, 0.08]))
    salaried = employment.startswith("SALARIED")
    employer = ""
    if employment == "SALARIED_PUBLIC":
        employer = _pick(rng, PUBLIC_EMPLOYERS)
    elif employment == "SALARIED_PRIVATE":
        employer = _pick(rng, PRIVATE_EMPLOYERS)
    ssnit = ""
    if salaried or employment == "RETIRED":
        ssnit = f"{_pick(rng, ('C', 'D', 'E', 'F'))}{int(rng.integers(10**11, 10**12)):012d}"
    return {
        "MaritalStatus": marital,
        "Nationality": "GHA",
        "CurResAddr1": f"H/No. {int(rng.integers(1, 400))} {_pick(rng, STREETS)}",
        "CurResAddr2": town,
        "OwnerOrTenant": str(rng.choice(["O", "T", "F"], p=[0.35, 0.5, 0.15])),
        "PostAddrLine1": f"P.O. Box {int(rng.integers(1, 9000))}, {town}",
        "EmpType": EMPLOYMENT_CODE[employment],
        "EmpName": employer,
        "Occupation": _pick(rng, OCCUPATIONS[employment]),
        "SSNum": ssnit,
    }


def business_details(
    seed: int, business_seq: int, size_band: str, sector: str, town: str
) -> dict[str, str]:
    rng = stream(seed, f"business-details:{business_seq}")
    sector_code, sub_sector = SECTOR_CODES[sector]
    return {
        "SectorIndCode": sector_code,
        "SubSecIndCode": sub_sector,
        "BusType": "A" if size_band == "MICRO" else "C",
        "CurLocAdd1": f"Plot {int(rng.integers(1, 250))} {_pick(rng, STREETS)}",
        "CurLocAdd2": town,
        "PostAddrLine1": f"P.O. Box {int(rng.integers(1, 9000))}, {town}",
    }
