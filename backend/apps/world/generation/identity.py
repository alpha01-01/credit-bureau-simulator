"""Synthetic identities: names, Ghana Card numbers, phone numbers.

All values are synthetic. Formats are ASSUMPTIONS until confirmed:
  A-002  Ghana Card: "GHA-" + 9 digits + "-" + 1 check digit (Luhn mod 10).
  A-003  Mobile numbers: 10 digits, "0" + network prefix + 7 digits.
"""

from __future__ import annotations

import numpy as np

# Day names (Akan) by gender; used as first or middle names.
AKAN_DAY_MALE = ("Kwadwo", "Kwabena", "Kwaku", "Yaw", "Kofi", "Kwame", "Kwasi")
AKAN_DAY_FEMALE = ("Adwoa", "Abena", "Akua", "Yaa", "Afua", "Ama", "Akosua")

FIRST_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "akan": {
        "M": (*AKAN_DAY_MALE, "Kojo", "Nana", "Kwesi", "Ekow", "Fiifi", "Paa", "Osei", "Kobina"),
        "F": (*AKAN_DAY_FEMALE, "Efua", "Esi", "Araba", "Adjoa", "Ekua", "Maame", "Akos", "Serwaa"),
    },
    "ewe": {
        "M": ("Selorm", "Edem", "Elikem", "Mawuli", "Kafui", "Kodzo", "Yao", "Komla", "Senyo", "Delali"),
        "F": ("Esinam", "Enyonam", "Dzifa", "Akorfa", "Sena", "Elinam", "Mawusi", "Afi", "Ama", "Yawa"),
    },
    "ga": {
        "M": ("Nii", "Tetteh", "Ashitey", "Nortey", "Okai", "Ayitey", "Kpakpo", "Odoi"),
        "F": ("Naa", "Dedei", "Korkoi", "Akweley", "Adoley", "Momo", "Ayorkor", "Shormeh"),
    },
    "northern": {
        "M": ("Abdul", "Mohammed", "Ibrahim", "Alhassan", "Issah", "Yakubu", "Fuseini", "Abubakari",
              "Mahama", "Sulemana", "Awudu", "Iddrisu", "Baba"),
        "F": ("Amina", "Fatima", "Zenabu", "Hawa", "Ayishetu", "Rahinatu", "Mariama", "Salamatu",
              "Memunatu", "Adisa", "Barikisu"),
    },
}  # fmt: skip

# Christian/English given names are common across all groups.
COMMON_FIRST_NAMES: dict[str, tuple[str, ...]] = {
    "M": ("Emmanuel", "Samuel", "Daniel", "Joseph", "Michael", "Isaac", "Francis", "Eric", "Prince",
          "Richard", "Stephen", "George", "Benjamin", "Godfred", "Ebenezer", "Felix", "Collins",
          "Derrick", "Bernard", "Solomon"),
    "F": ("Grace", "Mercy", "Comfort", "Gifty", "Esther", "Patience", "Abigail", "Elizabeth", "Joyce",
          "Priscilla", "Vida", "Beatrice", "Rita", "Linda", "Doris", "Gloria", "Mavis", "Cynthia",
          "Felicia", "Rebecca"),
}  # fmt: skip

SURNAMES: dict[str, tuple[str, ...]] = {
    "akan": ("Mensah", "Owusu", "Boateng", "Asante", "Osei", "Agyeman", "Appiah", "Darko", "Amoah",
             "Adjei", "Ofori", "Danso", "Opoku", "Antwi", "Sarpong", "Acheampong", "Frimpong",
             "Kyei", "Gyamfi", "Bonsu", "Nyarko", "Asamoah", "Ansah", "Amponsah", "Baffour",
             "Yeboah", "Manu", "Kusi", "Nkansah", "Oppong", "Boakye", "Duah", "Annan", "Quansah",
             "Essien", "Arthur", "Eshun", "Mensa", "Bediako", "Twumasi"),
    "ewe": ("Agbeko", "Kpodo", "Dzidzienyo", "Amegah", "Gbedemah", "Agbenyega", "Ahiable",
            "Kumordzi", "Adzraku", "Dogbe", "Ametewee", "Fiagbe", "Gadzekpo", "Akpalu", "Tsikata",
            "Agbodeka", "Zigah", "Kudjoe"),
    "ga": ("Quaye", "Lamptey", "Tetteh", "Laryea", "Nortey", "Ashong", "Okine", "Adjetey",
           "Aryee", "Kotey", "Ankrah", "Sowah", "Allotey", "Quarcoopome", "Odoi", "Addo"),
    "northern": ("Abubakar", "Ibrahim", "Mohammed", "Yakubu", "Alhassan", "Issahaku", "Seidu",
                 "Abdulai", "Mahama", "Dramani", "Iddrisu", "Salifu", "Zakaria", "Musah", "Tahiru",
                 "Bawa", "Adams", "Haruna", "Osman", "Sulley"),
}  # fmt: skip

NAME_GROUPS = tuple(SURNAMES)

# ASSUMPTION A-003: network prefixes and rough market shares.
MOBILE_PREFIXES: dict[str, float] = {
    "024": 0.20, "054": 0.15, "055": 0.12, "059": 0.08, "053": 0.05,  # MTN
    "020": 0.12, "050": 0.10,  # Telecel
    "027": 0.07, "057": 0.05, "026": 0.03, "056": 0.03,  # AT
}  # fmt: skip


def luhn_check_digit(digits: str) -> int:
    """Luhn mod-10 check digit for a string of digits (ASSUMPTION A-002)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def ghana_card_numbers(rng: np.random.Generator, n: int) -> list[str]:
    """n distinct synthetic Ghana Card numbers."""
    values = rng.choice(900_000_000, size=n, replace=False) + 100_000_000
    out = []
    for v in values.tolist():
        body = f"{v:09d}"
        out.append(f"GHA-{body}-{luhn_check_digit(body)}")
    return out


def phone_numbers(rng: np.random.Generator, n: int) -> list[str]:
    """n distinct synthetic mobile numbers in canonical 10-digit form."""
    prefixes = list(MOBILE_PREFIXES)
    weights = np.array(list(MOBILE_PREFIXES.values()))
    weights = weights / weights.sum()
    chosen = rng.choice(len(prefixes), size=n, p=weights)
    # 7-digit subscriber numbers unique within the whole set via a single draw.
    subscribers = rng.choice(10_000_000 * len(prefixes), size=n, replace=False)
    out = []
    for p_idx, sub in zip(chosen.tolist(), subscribers.tolist(), strict=True):
        out.append(f"{prefixes[p_idx]}{sub % 10_000_000:07d}")
    # Uniqueness of (prefix, subscriber) is not guaranteed by the modulo; fix collisions.
    seen: set[str] = set()
    for i, number in enumerate(out):
        while number in seen:
            number = (
                f"{prefixes[int(rng.integers(len(prefixes)))]}{int(rng.integers(10_000_000)):07d}"
            )
        seen.add(number)
        out[i] = number
    return out


def person_names(
    rng: np.random.Generator, groups: list[str], genders: list[str]
) -> list[tuple[str, str | None, str]]:
    """(first, middle, last) for each person, drawn from their naming group."""
    out: list[tuple[str, str | None, str]] = []
    for group, gender in zip(groups, genders, strict=True):
        own = FIRST_NAMES[group][gender]
        common = COMMON_FIRST_NAMES[gender]
        # Many Ghanaians carry a Christian/English or Muslim first name plus a traditional one.
        if group == "northern":
            first = own[int(rng.integers(len(own)))]
            middle = None if rng.random() < 0.6 else own[int(rng.integers(len(own)))]
        elif rng.random() < 0.55:
            first = common[int(rng.integers(len(common)))]
            middle = own[int(rng.integers(len(own)))] if rng.random() < 0.7 else None
        else:
            first = own[int(rng.integers(len(own)))]
            middle = common[int(rng.integers(len(common)))] if rng.random() < 0.35 else None
        if middle == first:
            middle = None
        surnames = SURNAMES[group]
        last = surnames[int(rng.integers(len(surnames)))]
        out.append((first, middle, last))
    return out


BUSINESS_WORDS = (
    "Golden", "Royal", "Unity", "Grace", "Divine", "Excel", "Prime", "Peace", "Blessed", "Victory",
    "Star", "Liberty", "Supreme", "Heritage", "Pioneer", "Sunrise", "Faith", "Trinity", "Crown",
    "Eagle", "Harmony", "Sterling", "Bright", "Evergreen", "Gateway", "Summit", "Noble", "Legacy",
)  # fmt: skip

BUSINESS_SECTOR_WORDS: dict[str, tuple[str, ...]] = {
    "AGRICULTURE": ("Farms", "Agro", "Agribusiness", "Poultry Farms", "Cocoa Ventures"),
    "TRADE": ("Enterprise", "Trading", "Ventures", "Stores", "Merchants", "Supplies"),
    "MANUFACTURING": ("Industries", "Manufacturing", "Products", "Packaging"),
    "CONSTRUCTION": ("Construction", "Builders", "Engineering Works", "Building Materials"),
    "TRANSPORT": ("Transport", "Logistics", "Haulage", "Freight Services"),
    "HOSPITALITY": ("Hotel", "Restaurant", "Catering Services", "Guest House"),
    "SERVICES": ("Services", "Consult", "Solutions", "Cleaning Services"),
    "ICT": ("Technologies", "Systems", "Digital", "Networks"),
    "FINANCE": ("Capital", "Investments", "Partners"),
    "EDUCATION": ("Academy", "School Complex", "Learning Centre"),
    "HEALTH": ("Pharmacy", "Clinic", "Medical Centre", "Diagnostics"),
    "PUBLIC_ADMINISTRATION": ("Services",),
    "MINING": ("Mining", "Minerals", "Quarry"),
}

LEGAL_SUFFIXES = ("Ltd", "Limited", "Company Ltd", "Enterprise", "Ventures")


def business_names(
    rng: np.random.Generator, sectors: list[str], owner_surnames: list[str]
) -> list[str]:
    out = []
    for sector, surname in zip(sectors, owner_surnames, strict=True):
        tail = BUSINESS_SECTOR_WORDS[sector]
        word = (
            surname
            if rng.random() < 0.35
            else BUSINESS_WORDS[int(rng.integers(len(BUSINESS_WORDS)))]
        )
        suffix = LEGAL_SUFFIXES[int(rng.integers(len(LEGAL_SUFFIXES)))]
        out.append(f"{word} {tail[int(rng.integers(len(tail)))]} {suffix}")
    return out
