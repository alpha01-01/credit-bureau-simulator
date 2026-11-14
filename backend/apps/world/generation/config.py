"""World generation configuration.

Every numeric value here that describes the real Ghanaian market is an
ASSUMPTION until confirmed from reference material (docs/assumptions.md).
Values are plain data so they can be tuned without touching the engine.

Monetary amounts are in GHS. Inside the engine they are handled as integer
pesewas (1 GHS = 100 pesewas) so arithmetic is exact and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

GENERATOR_VERSION = "s1.0"

# --- Scale -------------------------------------------------------------------


@dataclass(frozen=True)
class Scale:
    name: str
    individuals: int
    businesses: int
    target_active_loans: int  # approximate steady-state book across all lenders
    history_months: int  # months of stored history ending at history_end
    burn_in_months: int  # simulated before the history window, not stored


SCALES: dict[str, Scale] = {
    # Established-scenario default (Document 07, Section 7.4).
    "default": Scale("default", 40_000, 4_000, 70_000, 36, 24),
    # For tests and quick iterations.
    "small": Scale("small", 2_000, 200, 3_500, 12, 12),
    "tiny": Scale("tiny", 400, 40, 700, 6, 6),
}

DEFAULT_HISTORY_END = date(2026, 12, 31)


# --- Geography (ASSUMPTION A-004: approximate population shares) -------------

REGIONS: dict[str, float] = {
    "Greater Accra": 0.172,
    "Ashanti": 0.175,
    "Eastern": 0.093,
    "Central": 0.093,
    "Western": 0.066,
    "Western North": 0.029,
    "Volta": 0.054,
    "Oti": 0.025,
    "Northern": 0.075,
    "Savannah": 0.021,
    "North East": 0.020,
    "Upper East": 0.042,
    "Upper West": 0.029,
    "Bono": 0.040,
    "Bono East": 0.039,
    "Ahafo": 0.018,
}

# Main town per region, used for addresses and branch names.
REGION_TOWNS: dict[str, tuple[str, ...]] = {
    "Greater Accra": ("Accra", "Tema", "Madina", "Kasoa", "Dansoman", "Teshie"),
    "Ashanti": ("Kumasi", "Obuasi", "Ejisu", "Konongo", "Mampong"),
    "Eastern": ("Koforidua", "Nkawkaw", "Nsawam", "Akim Oda"),
    "Central": ("Cape Coast", "Winneba", "Mankessim", "Swedru"),
    "Western": ("Takoradi", "Sekondi", "Tarkwa"),
    "Western North": ("Sefwi Wiawso", "Bibiani"),
    "Volta": ("Ho", "Hohoe", "Keta", "Aflao"),
    "Oti": ("Dambai", "Nkwanta"),
    "Northern": ("Tamale", "Yendi", "Savelugu"),
    "Savannah": ("Damongo", "Bole"),
    "North East": ("Nalerigu", "Walewale"),
    "Upper East": ("Bolgatanga", "Navrongo", "Bawku"),
    "Upper West": ("Wa", "Tumu", "Lawra"),
    "Bono": ("Sunyani", "Berekum", "Dormaa Ahenkro"),
    "Bono East": ("Techiman", "Kintampo", "Atebubu"),
    "Ahafo": ("Goaso", "Bechem"),
}

# Which naming tradition dominates a region (for synthetic names only).
REGION_NAME_GROUPS: dict[str, dict[str, float]] = {
    "Greater Accra": {"akan": 0.45, "ga": 0.30, "ewe": 0.15, "northern": 0.10},
    "Volta": {"ewe": 0.85, "akan": 0.15},
    "Oti": {"ewe": 0.45, "akan": 0.30, "northern": 0.25},
    "Northern": {"northern": 0.90, "akan": 0.10},
    "Savannah": {"northern": 0.90, "akan": 0.10},
    "North East": {"northern": 0.95, "akan": 0.05},
    "Upper East": {"northern": 0.95, "akan": 0.05},
    "Upper West": {"northern": 0.95, "akan": 0.05},
}
DEFAULT_NAME_GROUPS: dict[str, float] = {"akan": 0.85, "ewe": 0.05, "ga": 0.03, "northern": 0.07}


# --- Livelihoods (ASSUMPTION A-005: monthly incomes in GHS) -------------------


@dataclass(frozen=True)
class EmploymentType:
    code: str
    share: float
    median_income: float  # GHS per month
    income_sigma: float  # lognormal sigma
    stability: float  # 0..1, higher = steadier income; lowers missed payments
    credit_demand: float  # relative likelihood of applying for credit


EMPLOYMENT_TYPES: tuple[EmploymentType, ...] = (
    EmploymentType("SALARIED_PUBLIC", 0.14, 3_800, 0.45, 0.90, 1.6),
    EmploymentType("SALARIED_PRIVATE", 0.20, 4_500, 0.60, 0.75, 1.4),
    EmploymentType("SELF_EMPLOYED", 0.26, 3_200, 0.80, 0.50, 1.2),
    EmploymentType("INFORMAL", 0.28, 1_600, 0.65, 0.35, 1.0),
    EmploymentType("RETIRED", 0.06, 1_900, 0.50, 0.70, 0.5),
    EmploymentType("UNEMPLOYED", 0.06, 400, 0.70, 0.10, 0.3),
)

# Sectors of work, with sensitivity of borrowers in that sector to economic stress.
SECTORS: dict[str, float] = {
    "AGRICULTURE": 1.3,
    "TRADE": 1.2,
    "MANUFACTURING": 1.1,
    "CONSTRUCTION": 1.4,
    "TRANSPORT": 1.2,
    "HOSPITALITY": 1.4,
    "SERVICES": 1.0,
    "ICT": 0.9,
    "FINANCE": 0.8,
    "EDUCATION": 0.6,
    "HEALTH": 0.6,
    "PUBLIC_ADMINISTRATION": 0.5,
    "MINING": 1.1,
}

# --- Products (ASSUMPTION A-006: terms and annual interest rates) -----------


@dataclass(frozen=True)
class Product:
    code: str
    facility_type: str  # bureau-facing facility type
    borrower: str  # "INDIVIDUAL" or "BUSINESS"
    term_months: tuple[int, int]  # inclusive range
    annual_rate: tuple[float, float]
    amount_income_multiple: tuple[float, float]  # of monthly income / revenue
    amount_bounds: tuple[int, int]  # GHS min, max
    round_to: int  # GHS
    max_dsr: float | None  # max installment / income enforced at origination
    miss_shift: float  # additive log-odds shift on missed payments


PRODUCTS: dict[str, Product] = {
    p.code: p
    for p in (
        Product("PERSONAL_LOAN", "TERM_LOAN", "INDIVIDUAL", (12, 60), (0.27, 0.36), (3, 14), (1_000, 250_000), 100, 0.40, 0.0),
        Product("MORTGAGE", "MORTGAGE", "INDIVIDUAL", (120, 240), (0.19, 0.26), (40, 90), (80_000, 2_500_000), 1_000, 0.40, -0.6),
        Product("AUTO_LOAN", "ASSET_FINANCE", "INDIVIDUAL", (24, 60), (0.24, 0.32), (8, 24), (20_000, 600_000), 500, 0.45, -0.2),
        Product("MICRO_LOAN", "TERM_LOAN", "INDIVIDUAL", (3, 12), (0.45, 0.65), (0.5, 3), (300, 20_000), 50, None, 0.4),
        Product("DIGITAL_LOAN", "MOBILE_LOAN", "INDIVIDUAL", (1, 3), (0.80, 1.40), (0.05, 0.5), (50, 3_000), 10, None, 1.5),
        Product("BUSINESS_TERM_LOAN", "TERM_LOAN", "BUSINESS", (12, 48), (0.26, 0.38), (1, 6), (5_000, 3_000_000), 1_000, 0.50, 0.0),
        Product("MICRO_BUSINESS_LOAN", "TERM_LOAN", "BUSINESS", (3, 12), (0.45, 0.65), (0.5, 2), (1_000, 50_000), 100, None, 0.3),
    )
}  # fmt: skip


# --- Lenders (fictional; ASSUMPTION A-007) -----------------------------------


@dataclass(frozen=True)
class LenderProfile:
    code: str
    name: str
    lender_type: str  # COMMERCIAL_BANK | SAVINGS_AND_LOANS | MICROFINANCE | DIGITAL_LENDER
    book_weight: float  # share of the world's target active loans
    products: dict[str, float]  # product code -> share of originations
    approval_cutoff: float  # approve if observed risk < cutoff (risk is ~N(0,1))
    screening_noise: float  # sd of the lender's error when assessing risk
    writeoff_dpd: int  # days past due at which the lender writes off
    regions: tuple[str, ...] | None  # None = national footprint
    branch_count: int
    customer_prefix: str
    account_prefix: str
    sophistication: float = 0.5  # 0..1, used later for data quality defaults
    founded: int = 2000


LENDERS: tuple[LenderProfile, ...] = (
    LenderProfile("ATB", "Atlas Bank", "COMMERCIAL_BANK", 0.17,
                  {"PERSONAL_LOAN": 0.62, "MORTGAGE": 0.05, "AUTO_LOAN": 0.08, "BUSINESS_TERM_LOAN": 0.25},
                  0.55, 0.45, 360, None, 24, "AT", "0110", 0.8, 1994),
    LenderProfile("MRB", "Meridian Bank", "COMMERCIAL_BANK", 0.14,
                  {"PERSONAL_LOAN": 0.65, "MORTGAGE": 0.04, "AUTO_LOAN": 0.06, "BUSINESS_TERM_LOAN": 0.25},
                  0.65, 0.50, 360, None, 18, "MB", "0230", 0.7, 2001),
    LenderProfile("UNS", "Unity Savings", "SAVINGS_AND_LOANS", 0.09,
                  {"PERSONAL_LOAN": 0.55, "MICRO_LOAN": 0.20, "BUSINESS_TERM_LOAN": 0.10, "MICRO_BUSINESS_LOAN": 0.15},
                  0.95, 0.65, 270, None, 12, "US", "3070", 0.45, 2006),
    LenderProfile("SWC", "SwiftCash", "DIGITAL_LENDER", 0.06,
                  {"DIGITAL_LOAN": 1.0},
                  1.45, 0.85, 120, None, 1, "SC", "77", 0.6, 2019),
    LenderProfile("HZF", "Horizon Finance", "MICROFINANCE", 0.06,
                  {"MICRO_LOAN": 0.60, "MICRO_BUSINESS_LOAN": 0.40},
                  1.20, 0.75, 180, ("Ashanti", "Bono", "Bono East", "Ahafo", "Eastern"), 8, "HF", "5520", 0.3, 2009),
    LenderProfile("CCB", "Coastal Commercial Bank", "COMMERCIAL_BANK", 0.12,
                  {"PERSONAL_LOAN": 0.60, "MORTGAGE": 0.04, "AUTO_LOAN": 0.07, "BUSINESS_TERM_LOAN": 0.29},
                  0.60, 0.45, 360, None, 20, "CC", "0340", 0.75, 1998),
    LenderProfile("PNB", "Pinnacle Bank", "COMMERCIAL_BANK", 0.09,
                  {"PERSONAL_LOAN": 0.58, "MORTGAGE": 0.06, "AUTO_LOAN": 0.08, "BUSINESS_TERM_LOAN": 0.28},
                  0.50, 0.40, 360, None, 14, "PN", "0450", 0.85, 2004),
    LenderProfile("BCB", "Beacon Bank", "COMMERCIAL_BANK", 0.07,
                  {"PERSONAL_LOAN": 0.70, "AUTO_LOAN": 0.05, "BUSINESS_TERM_LOAN": 0.25},
                  0.75, 0.55, 360, None, 10, "BC", "0560", 0.6, 2010),
    LenderProfile("KSL", "Keystone Savings & Loans", "SAVINGS_AND_LOANS", 0.06,
                  {"PERSONAL_LOAN": 0.50, "MICRO_LOAN": 0.25, "MICRO_BUSINESS_LOAN": 0.25},
                  1.00, 0.70, 270, ("Greater Accra", "Central", "Western", "Eastern"), 7, "KS", "3180", 0.4, 2008),
    LenderProfile("EGM", "Evergreen Microfinance", "MICROFINANCE", 0.04,
                  {"MICRO_LOAN": 0.55, "MICRO_BUSINESS_LOAN": 0.45},
                  1.25, 0.80, 180, ("Volta", "Oti", "Greater Accra", "Eastern"), 6, "EG", "5630", 0.25, 2012),
    LenderProfile("HVM", "Harvest Microfinance", "MICROFINANCE", 0.04,
                  {"MICRO_LOAN": 0.50, "MICRO_BUSINESS_LOAN": 0.50},
                  1.30, 0.85, 180, ("Northern", "Savannah", "North East", "Upper East", "Upper West"), 6, "HV", "5740", 0.2, 2011),
    LenderProfile("QLD", "QuickLend", "DIGITAL_LENDER", 0.06,
                  {"DIGITAL_LOAN": 1.0},
                  1.60, 0.95, 90, None, 1, "QL", "88", 0.5, 2020),
)  # fmt: skip


# Supplier Reference Numbers (SRN): each reporting institution's number, assigned by
# the Bank of Ghana and used in file names (ASSUMPTION A-036: fictional values).
LENDER_SRN: dict[str, str] = {
    "ATB": "10104", "MRB": "10117", "UNS": "20236", "SWC": "40318", "HZF": "30425",
    "CCB": "10129", "PNB": "10132", "BCB": "10145", "KSL": "20251", "EGM": "30437",
    "HVM": "30449", "QLD": "40322",
}  # fmt: skip


# --- Behaviour model (Document 07, Section 7.2) ------------------------------


@dataclass(frozen=True)
class BehaviourModel:
    """Log-odds coefficients for monthly repayment behaviour.

    Current loans:   P(miss) = sigmoid(miss_base + miss_risk*z + miss_burden*excess_burden
                                       + miss_stress*stress*sector_sensitivity
                                       - miss_stability*stability + product.miss_shift)
    Loans in arrears: P(cure) and P(pay one) fall with arrears depth and risk.
    """

    miss_base: float = -2.6
    miss_risk: float = 0.95
    miss_burden: float = 2.2
    burden_threshold: float = 0.35  # total installments / income above which burden bites
    miss_stress: float = 0.6
    miss_stability: float = 1.1
    # In arrears
    cure_base: float = -0.6
    cure_depth: float = 0.55  # per installment in arrears
    cure_risk: float = 0.7
    pay_one_base: float = -0.9
    pay_one_depth: float = 0.25
    pay_one_risk: float = 0.4
    # Early settlement of current loans (per month)
    early_settlement: float = 0.008


@dataclass(frozen=True)
class EconomyModel:
    """AR(1) national stress index; positive = harder times. Lending volume falls with stress."""

    stress_phi: float = 0.85
    stress_sigma: float = 0.10
    stress_mean: float = 0.0
    lending_stress_elasticity: float = 0.35
    annual_lending_growth: float = 0.06


@dataclass(frozen=True)
class WorldConfig:
    seed: int
    scale: Scale
    history_end: date = DEFAULT_HISTORY_END
    lenders: tuple[LenderProfile, ...] = LENDERS
    behaviour: BehaviourModel = field(default_factory=BehaviourModel)
    economy: EconomyModel = field(default_factory=EconomyModel)
    # Months simulated after history_end, added one at a time during play.
    # history_end stays the world's original anchor (ages, growth path), so
    # extending a world never changes what came before.
    extra_months: int = 0

    @property
    def total_months(self) -> int:
        return self.scale.burn_in_months + self.scale.history_months

    @property
    def simulated_months(self) -> int:
        return self.total_months + self.extra_months
