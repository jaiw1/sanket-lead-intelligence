"""Static per-customer attributes of the synthetic liability book.

Everything here is a ``(N,)`` array drawn once per customer and held constant
across the panel.  Two groups live side by side:

* the pre-SD-S1 attributes (segment, age, city tier, tenure, consent, income,
  rent, external EMI, auto EMI, school fees, FD) — drawn with the same
  parameters as before so ``--legacy-size`` reproduces the old distributions;
* the SD-S1 additions that the new channels need (salary discipline, cards,
  insurance, property, gold, dependants, UPI adoption, friction).

Parameter provenance is recorded per attribute in the docstrings and collected
in ``DATA_CARD.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import SEGMENT_P, SEGMENTS, BookConfig, substream


@dataclass
class Population:
    """Static attributes, all ``(N,)`` and index-aligned."""

    cust_id: np.ndarray
    seg_idx: np.ndarray            # index into SEGMENTS
    segment: np.ndarray            # str
    age: np.ndarray
    city_tier: np.ndarray
    tenure_m: np.ndarray
    consent: np.ndarray            # bool
    base_income: np.ndarray        # monthly recurring credit, rupees
    inc_drift: np.ndarray          # per-month geometric income drift
    income_vol: np.ndarray         # per-month lognormal-ish credit volatility

    # committed-outflow statics (pre-SD-S1)
    rent_base: np.ndarray
    ext_emi_base: np.ndarray
    has_auto_emi: np.ndarray       # bool
    school_base: np.ndarray
    fd_base: np.ndarray

    # SD-S1 additions
    salary_day_base: np.ndarray        # nominal day-of-month of the salary credit
    salary_regular: np.ndarray         # bool — is there an identifiable salary day at all
    salary_sources: np.ndarray         # distinct recurring credit sources
    other_bank_emi_share: np.ndarray   # share of ext_emi standing to OTHER lenders
    external_emi_count_base: np.ndarray
    has_card: np.ndarray               # bool
    card_spend_base: np.ndarray
    has_insurance: np.ndarray          # bool
    insurance_annual: np.ndarray
    insurance_monthly_mode: np.ndarray  # bool — pays by monthly SI rather than annually
    insurance_renewal_month: np.ndarray  # calendar month 1..12
    owns_property: np.ndarray          # bool
    has_home_loan: np.ndarray          # bool — existing housing EMI, with any lender
    gold_holding_g: np.ndarray
    dependants: np.ndarray
    upi_share: np.ndarray              # share of retail spend routed through UPI P2M
    upi_ticket: np.ndarray             # customer's median P2M ticket, rupees
    amb_threshold: np.ndarray          # average-monthly-balance floor for the tier

    # journey friction truth (consumed by SD-S2, never a feature)
    fee_sensitivity: np.ndarray
    doc_reluctance: np.ndarray

    #: housing EMI already running with any lender; folded into the external-EMI
    #: outflow in the modern preset only (zero under ``--legacy-size``)
    home_emi_base: np.ndarray

    def __len__(self) -> int:
        return len(self.cust_id)


#: Average-monthly-balance floors by city tier, rupees.  IDBI and peers run
#: metro / urban / semi-urban-rural AMB slabs of roughly this shape; the exact
#: numbers are ``assumed`` (public schedules of charges vary by product variant).
AMB_BY_TIER = {1: 10_000.0, 2: 5_000.0, 3: 2_500.0}

#: Day-of-month the salary lands, and its probability.  Indian payroll clusters
#: hard on the 1st and the last working day, with a 5th/7th/10th tail. ``assumed``.
SALARY_DAY_P = {1: 0.30, 30: 0.18, 2: 0.06, 3: 0.05, 5: 0.12, 7: 0.12, 10: 0.08, 15: 0.05, 25: 0.04}


def build_population(cfg: BookConfig) -> Population:
    """Draw every static attribute for ``cfg.n`` customers."""
    rng = substream(cfg.seed, "population")
    n = cfg.n

    seg_idx = rng.choice(len(SEGMENTS), n, p=SEGMENT_P)
    segment = np.array(SEGMENTS, dtype=object)[seg_idx]
    salaried = seg_idx == 0
    self_emp = seg_idx == 1
    gig = seg_idx == 2

    # age: bank books skew to working age; clipped to the lending window
    age = np.clip(rng.normal(36, 9, n).astype(int), 21, 62)
    # city tier mix of a mid-size public-sector bank's retail book. ``assumed``.
    city_tier = rng.choice([1, 2, 3], n, p=[0.38, 0.40, 0.22])
    tenure_m = rng.integers(8, 180, n)
    consent = rng.random(n) < cfg.consent_share

    # monthly recurring credits by segment (lognormal, rupees).  Medians land at
    # roughly Rs 63k / 70k / 34k — a salary-account book sits well above the PLFS
    # all-India wage distribution because unbanked informal workers are absent.
    # ``assumed``, shaped by PLFS 2023-24 regular-wage earnings.
    base_income = np.where(
        salaried, rng.lognormal(11.05, 0.35, n),
        np.where(self_emp, rng.lognormal(11.15, 0.50, n), rng.lognormal(10.45, 0.45, n)),
    )
    base_income = np.clip(base_income, 18_000, 900_000)
    inc_drift = rng.normal(0.004, 0.003, n)                   # ~5%/yr nominal growth
    income_vol = np.where(salaried, 0.05, np.where(self_emp, 0.16, 0.30))

    # committed outflows ------------------------------------------------------
    rent_base = np.where(rng.random(n) < 0.55, base_income * rng.uniform(0.12, 0.30, n), 0.0)
    ext_emi_base = np.where(rng.random(n) < 0.38, base_income * rng.uniform(0.06, 0.22, n), 0.0)
    has_auto_emi = rng.random(n) < 0.22
    school_base = np.where((age > 29) & (rng.random(n) < 0.4), base_income * rng.uniform(0.04, 0.10, n), 0.0)
    fd_base = np.where(rng.random(n) < 0.45, base_income * rng.uniform(1.5, 8.0, n), 0.0)

    # salary discipline -------------------------------------------------------
    # Salaried customers almost always have a fixed credit day; self-employed
    # draws are half-regular; gig earnings arrive whenever the platform settles.
    salary_regular = np.where(salaried, rng.random(n) < 0.97,
                              np.where(self_emp, rng.random(n) < 0.55, rng.random(n) < 0.08))
    days = np.array(list(SALARY_DAY_P), dtype=np.int64)
    probs = np.array(list(SALARY_DAY_P.values()))
    salary_day_base = rng.choice(days, n, p=probs / probs.sum())
    salary_sources = np.where(
        salaried, 1 + (rng.random(n) < 0.15).astype(int) + (rng.random(n) < 0.03).astype(int),
        np.where(self_emp, 1 + rng.poisson(1.6, n), 1 + rng.poisson(2.4, n)),
    ).clip(1, 12)

    # external lenders --------------------------------------------------------
    # The share of an external EMI that stands to *another* bank is exactly the
    # gap AA (API 595/739) would close; ~10% of borrowers service everything here.
    other_bank_emi_share = np.where(rng.random(n) < 0.10, 0.0, rng.uniform(0.40, 1.0, n))
    external_emi_count_base = np.where(ext_emi_base > 0, 1 + rng.geometric(0.55, n) - 1, 0).clip(0, 6)

    # cards -------------------------------------------------------------------
    # RBI reports ~110mn credit cards in force against a far larger deposit base;
    # penetration in a salary-account book is higher and income-skewed.  Target
    # ~30% of the book carries a card. ``assumed`` (RBI card statistics anchor).
    card_logit = (-1.70 + 1.35 * np.log(base_income / 45_000) + 0.55 * salaried
                  + 0.35 * (city_tier == 1) - 0.30 * (city_tier == 3))
    has_card = rng.random(n) < 1 / (1 + np.exp(-card_logit))
    # RBI's card statistics imply roughly Rs 15k of spend per card per month;
    # scaling 5-28% of recurring credits lands a cardholder near that. ``assumed``
    # shape, RBI aggregate as the anchor.
    card_spend_base = np.where(has_card, base_income * rng.uniform(0.05, 0.28, n), 0.0)

    # insurance ---------------------------------------------------------------
    # IRDAI puts Indian life-insurance penetration near 3% of GDP.  Premium here
    # is 2-8% of annual recurring credits for the 55% who hold a policy.
    has_insurance = rng.random(n) < 0.55
    insurance_annual = np.where(has_insurance, base_income * 12 * rng.uniform(0.02, 0.08, n), 0.0)
    insurance_monthly_mode = has_insurance & (rng.random(n) < 0.30)
    insurance_renewal_month = rng.integers(1, 13, n)

    # property, gold, dependants ---------------------------------------------
    own_logit = -1.45 + 0.085 * (age - 30) + 0.75 * np.log(base_income / 45_000) - 0.25 * (city_tier == 1)
    owns_property = rng.random(n) < 1 / (1 + np.exp(-own_logit))
    has_home_loan = owns_property & (rng.random(n) < 0.45)
    # World Gold Council estimates Indian households hold ~25,000 t of gold; the
    # per-customer distribution here (median ~45 g among the 70% who hold any)
    # is ``assumed``.
    gold_holding_g = np.where(rng.random(n) < 0.70, rng.lognormal(np.log(45), 0.8, n), 0.0)
    dep_lam = np.clip((age - 26) / 9.0, 0.0, 2.2)
    dependants = rng.poisson(dep_lam).clip(0, 4)

    # digital payment behaviour ----------------------------------------------
    # NPCI puts UPI person-to-merchant well above half of all UPI volume, with a
    # low median ticket.  Per-customer share and ticket are ``assumed``.
    upi_share = np.clip(rng.normal(np.where(city_tier == 1, 0.55, np.where(city_tier == 2, 0.46, 0.36)), 0.10), 0.05, 0.9)
    upi_ticket = rng.lognormal(np.log(300), 0.45, n).clip(60, 4_000)

    amb_threshold = np.vectorize(AMB_BY_TIER.get)(city_tier).astype(np.float64)

    # journey friction (SD-S2 truth) -----------------------------------------
    fee_sensitivity = np.clip(rng.beta(2.0, 3.0, n) + 0.25 * gig - 0.10 * salaried, 0.0, 1.0)
    doc_reluctance = np.clip(rng.beta(2.0, 4.0, n) + 0.20 * (~salaried), 0.0, 1.0)

    # Drawn last so that switching presets cannot shift any earlier draw.
    home_emi_base = np.where(has_home_loan, base_income * rng.uniform(0.18, 0.32, n), 0.0)
    if cfg.preset == "legacy":
        home_emi_base = np.zeros(n)

    cust_id = np.array([f"LB-{2_000_000 + i}" for i in range(n)], dtype=object)

    return Population(
        cust_id=cust_id, seg_idx=seg_idx, segment=segment, age=age, city_tier=city_tier,
        tenure_m=tenure_m, consent=consent, base_income=base_income, inc_drift=inc_drift,
        income_vol=income_vol, rent_base=rent_base, ext_emi_base=ext_emi_base,
        has_auto_emi=has_auto_emi, school_base=school_base, fd_base=fd_base,
        salary_day_base=salary_day_base, salary_regular=salary_regular, salary_sources=salary_sources,
        other_bank_emi_share=other_bank_emi_share, external_emi_count_base=external_emi_count_base,
        has_card=has_card, card_spend_base=card_spend_base, has_insurance=has_insurance,
        insurance_annual=insurance_annual, insurance_monthly_mode=insurance_monthly_mode,
        insurance_renewal_month=insurance_renewal_month, owns_property=owns_property,
        has_home_loan=has_home_loan, gold_holding_g=gold_holding_g, dependants=dependants,
        upi_share=upi_share, upi_ticket=upi_ticket, amb_threshold=amb_threshold,
        fee_sensitivity=fee_sensitivity, doc_reluctance=doc_reluctance,
        home_emi_base=home_emi_base,
    )
