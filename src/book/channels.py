"""Monthly observation channels — what the bank actually sees.

This module renders the latent intent of :mod:`book.latent` into the account
behaviour a core banking system would record, and derives the capacity process
alongside it.

Why there is a loop here
------------------------
Everything is vectorised across customers.  The single ``for m in range(M)``
loop is unavoidable: the balance path is a recursive state machine (this
month's closing balance is next month's opening balance, the FD can only be
broken once, and the trailing six-month median that defines capacity needs the
months already produced).  Thirty iterations of ``(N,)`` numpy work costs about
a second at 60,000 customers; a per-customer row loop costs minutes.

Channel families
----------------
*carried over*  credits, balances, rent, fuel + cab, school fees, e-commerce,
                external EMI, FD balance, product-page dwell
*new in SD-S1*  UPI person-to-merchant count and value, salary credit day and
                source count, EMI standing to other lenders (the AA / API-595
                gap), external EMI count, card spend, insurance premium,
                minimum-balance charge, mandate failures, premature FD closure,
                address and nominee changes, bonus / irregular credits

Parameter provenance is noted inline and collected in ``DATA_CARD.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import BookConfig, substream
from .hard_negatives import Archetypes
from .latent import Latents
from .population import Population

# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #

#: Share of recurring credits that leaves as essential spend. ``assumed``.
ESSENTIAL_SPEND_RANGE = (0.30, 0.45)
FUEL_SHARE_RANGE = (0.015, 0.045)
ECOM_SHARE_RANGE = (0.02, 0.08)

#: Only a quarter of a month's net flow persists into the average balance —
#: the rest is spent, swept or moved. Carried over from the pre-SD-S1 book.
BALANCE_PERSISTENCE = 0.25
BALANCE_FLOOR = 1_000.0
MIN_BALANCE_FLOOR = 500.0

#: Ramp tells, by product.  ``assumed`` throughout; these are the generative
#: reason each product is separable at all, so they are the main tuning knob.
RENT_STEPUP = 0.38          # home: landlord hike that pushes a renter to buy
DOWNPAYMENT_ACCRETION = (0.06, 0.20)
FD_BREAK_P = 0.20           # home: mobilising the down payment late in the ramp
FUEL_SURGE_STRONG, FUEL_SURGE_WEAK = 1.5, 0.6     # auto
EMI_CREEP_STRONG, EMI_CREEP_WEAK = 0.08, 0.03     # personal: EMI stacking
PRE_SALARY_DIP = (0.06, 0.22)                     # personal
LAP_DRAWDOWN = 0.05         # lap: mobilising funds against an owned property
LAP_FD_BREAK_P = 0.25
GOLD_DIP = (0.15, 0.35)     # gold: an acute liquidity squeeze, short fuse
GOLD_DRAWDOWN = 0.12
EDUCATION_FEE_STEP = 0.90   # education: admission and term fees stepping up
EDUCATION_ACCRETION = (0.03, 0.10)

#: Red-herring tells: the same shapes, slightly weaker, with no dwell and no
#: purchase. Carried over verbatim from the pre-SD-S1 book.
RH_RENT_STEPUP = 0.35
RH_ACCRETION = (0.05, 0.15)
RH_FUEL_SURGE = 1.4
RH_EMI_CREEP = 0.09
RH_DIP = (0.08, 0.22)

#: Browsing. ``assumed``.
RAMP_DWELL_MINUTES = (1.0, 7.0)
WINDOW_SHOPPER_DWELL = (6.0, 14.0)
AMBIENT_BROWSE_P = 0.12
AMBIENT_DWELL = (0.5, 3.0)

#: Dormant-rich customers hold a permanently fat balance. ``assumed``.
DORMANT_RICH_MULTIPLE = 4.5

#: UPI adoption drift per month (share of retail spend routed P2M).  NPCI's
#: monthly UPI statistics show P2M running well above half of all UPI volume and
#: still growing; the per-customer share and the drift are ``assumed``.
UPI_ADOPTION_DRIFT = 0.006
UPI_WEIGHTS = {"essential": 0.50, "ecommerce": 0.80, "fuel": 0.60}
UPI_MAX_COUNT = 600

#: Salary-day jitter (weekend / holiday shifts). ``assumed``.
SALARY_JITTER = ([-2, -1, 0, 1], [0.10, 0.22, 0.56, 0.12])

#: Minimum-balance charge: banks waive it often enough that the flag is noisy.
MIN_BAL_CHARGE_ENFORCED_P = 0.85
MIN_BAL_CHARGE_RANGE = (150.0, 600.0)

#: NACH / e-mandate failure.  NPCI reports ecosystem-wide NACH debit success well
#: below 100%, but that is dominated by NBFC and MFI mandates; for a bank's own
#: savings customers the base rate is much lower and driven by the balance at the
#: presentation date.  Base rate ``assumed``, balance coupling ``assumed``.
MANDATE_FAIL_BASE = 0.015
MANDATE_FAIL_SQUEEZE = 0.55
MANDATE_FAIL_CAP = 0.45

#: Rare KYC events. ``assumed``.
ADDRESS_CHANGE_BASE = 0.004
ADDRESS_CHANGE_HOME_RAMP = 6.0     # property finalisation, last two ramp months
ADDRESS_CHANGE_YOUNG_RENTER = 2.0
NOMINEE_CHANGE_BASE = 0.002
NOMINEE_CHANGE_RAMP = 3.0
AMBIENT_FD_CLOSURE_P = 0.002

#: Seasonality (modern preset only).  Indian school fees cluster in Apr-Jun, the
#: bonus season straddles the March financial-year end and the Oct-Nov festive
#: months, and festive discretionary spend spikes. ``assumed``.
FEE_SEASON_MONTHS = (4, 5, 6)
FEE_SEASON_MULTIPLIER = 1.6
FESTIVE_MONTHS = (10, 11)
FESTIVE_ECOM_MULTIPLIER = 1.4
FESTIVE_CARD_MULTIPLIER = 1.5
BONUS_P = {"fy_end": 0.45, "festive": 0.25, "other": 0.02, "irregular": 0.14}
BONUS_FY_END_MONTHS = (3, 4)
BONUS_SIZE_SALARIED = (0.35, 1.60)
BONUS_SIZE_IRREGULAR = (0.20, 0.90)

#: A shared gold-price / liquidity-shock index: an AR(1) market factor every
#: gold ramp rides at once.  A deliberate seasonal confounder — it stops the
#: gold signal from being a clean per-customer story. ``assumed``.
GOLD_INDEX_RHO = 0.75
GOLD_INDEX_SD = 0.35

#: Essential-spend floor used by the capacity process; matches the committed
#: outflow that ``score_and_pack.build_features`` assumes. ``assumed``.
CAPACITY_ESSENTIAL_FLOOR = 0.38
CAPACITY_WINDOW = 6


@dataclass
class Channels:
    """Monthly channels; every array is ``(N, M)`` float32 unless noted."""

    monthly: dict[str, np.ndarray] = field(default_factory=dict)
    dwell: dict[str, np.ndarray] = field(default_factory=dict)   # canonical product name -> (N, M)
    capacity_abs: np.ndarray | None = None
    capacity_ratio: np.ndarray | None = None


def _uni(rng: np.random.Generator, lo: float, hi: float, n: int) -> np.ndarray:
    return rng.uniform(lo, hi, n)


def build_channels(cfg: BookConfig, pop: Population, arche: Archetypes, lat: Latents) -> Channels:
    """Render the latent structure into monthly account behaviour."""
    rng = substream(cfg.seed, "channels")
    mkt = substream(cfg.seed, "market")
    n, m_n, p_n = cfg.n, cfg.months, cfg.n_products
    rows = np.arange(n)
    pidx = {p: i for i, p in enumerate(cfg.products)}
    cal = cfg.calendar_months()

    # shared market factor (AR(1)), normalised to [0, 1] for use as a multiplier
    shock = np.zeros(m_n)
    for m in range(1, m_n):
        shock[m] = GOLD_INDEX_RHO * shock[m - 1] + mkt.normal(0, GOLD_INDEX_SD)
    gold_index = 1 / (1 + np.exp(-shock))

    # ---- names of every monthly column we emit ---------------------------- #
    legacy_cols = ["credits", "bal_avg", "bal_min", "rent", "fuel_cab", "school_fees",
                   "ecommerce", "ext_emi", "fd_bal"]
    new_cols = ["upi_p2m_count", "upi_p2m_value", "salary_credit_day", "salary_credit_source_count",
                "emi_outflow_to_other_bank", "external_emi_count", "card_spend", "insurance_premium",
                "min_balance_charge_flag", "mandate_failure_count", "fd_premature_closure_flag",
                "address_change_flag", "nominee_change_flag", "bonus_or_irregular_credit"]
    out = {c: np.zeros((n, m_n), dtype=np.float32) for c in legacy_cols + new_cols}
    dwell_out = {p: np.zeros((n, m_n), dtype=np.float32) for p in cfg.products}
    capacity_abs = np.zeros((n, m_n), dtype=np.float32)
    capacity_ratio = np.zeros((n, m_n), dtype=np.float32)

    # ---- recursive state -------------------------------------------------- #
    inc = pop.base_income
    bal = inc * rng.uniform(0.5, 2.2, n)
    fd = pop.fd_base.copy()
    credit_hist = np.full((n, CAPACITY_WINDOW), np.nan)

    use_dwell = arche.browses | arche.near_miss
    c_a, c_b = arche.expresses_primary, arche.expresses_secondary
    sig = lat.sig_strength
    ramp_prod_safe = lat.ramp_prod.clip(0)
    ws_prod_safe = arche.ws_prod.clip(0)

    for m in range(m_n):
        cal_m = int(cal[m])
        fee_season = cfg.seasonality and cal_m in FEE_SEASON_MONTHS
        festive = cfg.seasonality and cal_m in FESTIVE_MONTHS

        # ---- baseline month ---------------------------------------------- #
        credits = inc * (1 + pop.inc_drift) ** m * np.maximum(0.25, 1 + rng.normal(0, pop.income_vol, n))
        spend_ess = credits * _uni(rng, *ESSENTIAL_SPEND_RANGE, n)
        fuel = credits * _uni(rng, *FUEL_SHARE_RANGE, n)
        ecom = credits * _uni(rng, *ECOM_SHARE_RANGE, n)
        school = pop.school_base * (1 + 0.05 * (m // 12))
        if fee_season:
            school = school * FEE_SEASON_MULTIPLIER
        if festive:
            ecom = ecom * FESTIVE_ECOM_MULTIPLIER
        emi = pop.ext_emi_base + pop.home_emi_base
        rent_now = pop.rent_base.copy()
        dip = np.zeros(n)
        dwell_m = np.zeros((n, p_n))

        ir = lat.in_ramp[:, m]
        ks = lat.ks[:, m]
        kk_ramp = lat.k[:, m]

        # ---- the ramp: product-specific tells ----------------------------- #
        if use_dwell.any():
            add = np.where(ir & use_dwell, _uni(rng, *RAMP_DWELL_MINUTES, n) * (0.4 + ks), 0.0)
            dwell_m[rows, ramp_prod_safe] += add

        fd_break = np.zeros(n, dtype=bool)

        mh = ir & (lat.ramp_prod == pidx["home"])
        rent_now = np.where(mh & c_a, pop.rent_base * (1 + RENT_STEPUP * ks), rent_now)
        bal = bal + np.where(mh & c_b, credits * _uni(rng, *DOWNPAYMENT_ACCRETION, n) * (0.5 + sig), 0.0)
        fd_break |= mh & (kk_ramp > 0.6) & (fd > 0) & (rng.random(n) < FD_BREAK_P * sig)

        ma = ir & (lat.ramp_prod == pidx["auto"])
        fuel = np.where(ma, fuel * (1 + np.where(c_a, FUEL_SURGE_STRONG, FUEL_SURGE_WEAK) * ks), fuel)

        mp = ir & (lat.ramp_prod == pidx["personal"])
        emi = np.where(mp, emi + credits * np.where(c_a, EMI_CREEP_STRONG, EMI_CREEP_WEAK) * ks, emi)
        dip = np.where(mp & c_b, credits * _uni(rng, *PRE_SALARY_DIP, n) * ks, dip)

        if cfg.preset != "legacy":
            ml = ir & (lat.ramp_prod == pidx["lap"])
            bal = np.where(ml, bal * (1 - LAP_DRAWDOWN * ks), bal)
            fd_break |= ml & (kk_ramp > 0.5) & (fd > 0) & (rng.random(n) < LAP_FD_BREAK_P * sig)

            # the gold ramp rides a shared market shock, so every gold prospect
            # deepens at once — a confounder the model must see through
            mg = ir & (lat.ramp_prod == pidx["gold"])
            ks_gold = ks * (0.7 + 0.6 * gold_index[m])
            dip = np.where(mg, credits * _uni(rng, *GOLD_DIP, n) * ks_gold, dip)
            bal = np.where(mg, bal * (1 - GOLD_DRAWDOWN * ks_gold), bal)

            me = ir & (lat.ramp_prod == pidx["education"])
            school = np.where(me, school * (1 + EDUCATION_FEE_STEP * ks), school)
            bal = bal + np.where(me & c_b, credits * _uni(rng, *EDUCATION_ACCRETION, n) * (0.5 + sig), 0.0)

        # ---- outside the ramp: drift, plus the red-herring run-up ---------- #
        nb = ~ir
        bal = np.where(nb, bal * _uni(rng, 0.97, 1.03, n) + credits * _uni(rng, -0.02, 0.04, n), bal)

        rh_on = nb & (arche.rh_start >= 0) & (m >= arche.rh_start) & (m < arche.rh_start + arche.rh_len)
        kk = np.where(rh_on, (m - arche.rh_start) / np.maximum(arche.rh_len, 1), 0.0)

        rh_home = rh_on & (arche.rh_prod == pidx["home"])
        rent_now = np.where(rh_home, pop.rent_base * (1 + RH_RENT_STEPUP * kk), rent_now)
        bal = bal + np.where(rh_home, credits * _uni(rng, *RH_ACCRETION, n), 0.0)

        rh_auto = rh_on & (arche.rh_prod == pidx["auto"])
        fuel = np.where(rh_auto, fuel * (1 + RH_FUEL_SURGE * kk), fuel)

        if cfg.preset == "legacy":
            rh_debt = rh_on & (arche.rh_prod == pidx["personal"])
        else:
            rh_lap = rh_on & (arche.rh_prod == pidx["lap"])
            bal = np.where(rh_lap, bal * (1 - LAP_DRAWDOWN * kk), bal)
            rh_gold = rh_on & (arche.rh_prod == pidx["gold"])
            dip = np.where(rh_gold, credits * _uni(rng, *RH_DIP, n) * kk, dip)
            rh_edu = rh_on & (arche.rh_prod == pidx["education"])
            school = np.where(rh_edu, school * (1 + EDUCATION_FEE_STEP * kk), school)
            rh_debt = rh_on & (arche.rh_prod == pidx["personal"])
        emi = np.where(rh_debt, emi + credits * RH_EMI_CREEP * kk, emi)
        dip = np.where(rh_debt, credits * _uni(rng, *RH_DIP, n) * kk, dip)

        # ---- archetype overlays ------------------------------------------- #
        bal = np.where(arche.dormant_rich, np.maximum(bal, inc * DORMANT_RICH_MULTIPLE), bal)

        ws_on = (arche.ws_start >= 0) & (m >= arche.ws_start) & (m < arche.ws_start + 4)
        dwell_m[rows, ws_prod_safe] += np.where(ws_on, _uni(rng, *WINDOW_SHOPPER_DWELL, n), 0.0)

        amb = rng.random(n) < AMBIENT_BROWSE_P
        amb_prod = rng.integers(0, p_n, n)
        dwell_m[rows, amb_prod] += np.where(amb, _uni(rng, *AMBIENT_DWELL, n), 0.0)

        # ---- new channels -------------------------------------------------- #
        # salary credit day: a fixed day with weekend/holiday jitter for the
        # disciplined, a different day every month for gig earners
        jitter = rng.choice(SALARY_JITTER[0], n, p=SALARY_JITTER[1])
        salary_day = np.where(pop.salary_regular,
                              np.clip(pop.salary_day_base + jitter, 1, 28),
                              rng.integers(1, 29, n))
        salary_src = np.where(pop.salary_regular, pop.salary_sources,
                              np.clip(rng.poisson(pop.salary_sources), 1, 12))

        # bonus / irregular credits
        if cal_m in BONUS_FY_END_MONTHS:
            p_bonus = np.where(pop.seg_idx == 0, BONUS_P["fy_end"], BONUS_P["irregular"])
        elif cal_m in FESTIVE_MONTHS:
            p_bonus = np.where(pop.seg_idx == 0, BONUS_P["festive"], BONUS_P["irregular"])
        else:
            p_bonus = np.where(pop.seg_idx == 0, BONUS_P["other"], BONUS_P["irregular"])
        size = np.where(pop.seg_idx == 0,
                        _uni(rng, *BONUS_SIZE_SALARIED, n), _uni(rng, *BONUS_SIZE_IRREGULAR, n))
        bonus = np.where(rng.random(n) < p_bonus, credits * size, 0.0)

        # UPI P2M: a routing label over retail spend, not extra outflow
        upi_share_t = np.clip(pop.upi_share * (1 + UPI_ADOPTION_DRIFT * m), 0.05, 0.95)
        upi_value = (UPI_WEIGHTS["essential"] * spend_ess + UPI_WEIGHTS["ecommerce"] * ecom
                     + UPI_WEIGHTS["fuel"] * fuel) * upi_share_t
        upi_count = np.clip(np.round(upi_value / pop.upi_ticket), 0, UPI_MAX_COUNT)

        # card spend: also a routing label; rises under personal-loan stress
        card = pop.card_spend_base * _uni(rng, 0.5, 1.6, n)
        if festive:
            card = card * FESTIVE_CARD_MULTIPLIER
        card = np.where(mp, card * (1 + 0.6 * ks), card)
        card = np.where(pop.has_card, card, 0.0)

        # insurance: monthly standing instruction, or one annual renewal debit
        insurance = np.where(
            pop.has_insurance & pop.insurance_monthly_mode, pop.insurance_annual / 12.0,
            np.where(pop.has_insurance & (pop.insurance_renewal_month == cal_m), pop.insurance_annual, 0.0))

        # external lenders — the gap AA (API 595/739) would close
        other_bank_emi = emi * pop.other_bank_emi_share
        emi_count = (pop.external_emi_count_base + pop.has_home_loan.astype(int)
                     + np.where(mp, np.round(1.5 * ks), 0)).astype(int)
        emi_count = np.where(emi > 0, np.maximum(emi_count, 1), 0)

        # ---- cash-flow close-out ------------------------------------------ #
        outflow = spend_ess + fuel + ecom + school + emi + rent_now
        if cfg.new_channels_move_balance:
            outflow = outflow + insurance

        min_bal = np.maximum(MIN_BALANCE_FLOOR, bal * _uni(rng, 0.15, 0.5, n) - dip)

        charge_flag = (min_bal < pop.amb_threshold) & (rng.random(n) < MIN_BAL_CHARGE_ENFORCED_P)
        charge_amt = np.where(charge_flag, _uni(rng, *MIN_BAL_CHARGE_RANGE, n), 0.0)

        p_fail = np.clip(MANDATE_FAIL_BASE + MANDATE_FAIL_SQUEEZE
                         * np.clip(1 - min_bal / np.maximum(emi, 1.0), 0, 1), 0, MANDATE_FAIL_CAP)
        fails = np.where(emi_count > 0, rng.binomial(np.maximum(emi_count, 1), p_fail), 0)

        fd = np.where(fd_break, fd * 0.5, fd)
        fd_closed = fd_break | ((fd > 0) & (rng.random(n) < AMBIENT_FD_CLOSURE_P))

        late_home_ramp = mh & (kk_ramp > 0.7)
        p_addr = ADDRESS_CHANGE_BASE * (1 + (ADDRESS_CHANGE_HOME_RAMP - 1) * late_home_ramp) \
            * (1 + (ADDRESS_CHANGE_YOUNG_RENTER - 1) * ((pop.rent_base > 0) & (pop.age < 32)))
        addr_change = rng.random(n) < p_addr
        p_nom = NOMINEE_CHANGE_BASE * (1 + (NOMINEE_CHANGE_RAMP - 1) * (ir & (kk_ramp > 0.8)))
        nom_change = rng.random(n) < p_nom

        net = credits - outflow
        if cfg.new_channels_move_balance:
            net = net + bonus - charge_amt
        bal = np.maximum(BALANCE_FLOOR, bal + net * BALANCE_PERSISTENCE)

        # ---- capacity process --------------------------------------------- #
        credit_hist[:, m % CAPACITY_WINDOW] = credits
        med6 = np.nanmedian(credit_hist, axis=1)
        committed = rent_now + emi + school + insurance + CAPACITY_ESSENTIAL_FLOOR * med6
        cap = med6 - committed
        capacity_abs[:, m] = cap
        capacity_ratio[:, m] = cap / np.maximum(med6, 1.0)

        # ---- store --------------------------------------------------------- #
        out["credits"][:, m] = credits
        out["bal_avg"][:, m] = bal
        out["bal_min"][:, m] = min_bal
        out["rent"][:, m] = rent_now
        out["fuel_cab"][:, m] = fuel
        out["school_fees"][:, m] = school
        out["ecommerce"][:, m] = ecom
        out["ext_emi"][:, m] = emi
        out["fd_bal"][:, m] = fd
        out["upi_p2m_count"][:, m] = upi_count
        out["upi_p2m_value"][:, m] = upi_value
        out["salary_credit_day"][:, m] = salary_day
        out["salary_credit_source_count"][:, m] = salary_src
        out["emi_outflow_to_other_bank"][:, m] = other_bank_emi
        out["external_emi_count"][:, m] = emi_count
        out["card_spend"][:, m] = card
        out["insurance_premium"][:, m] = insurance
        out["min_balance_charge_flag"][:, m] = charge_flag
        out["mandate_failure_count"][:, m] = fails
        out["fd_premature_closure_flag"][:, m] = fd_closed
        out["address_change_flag"][:, m] = addr_change
        out["nominee_change_flag"][:, m] = nom_change
        out["bonus_or_irregular_credit"][:, m] = bonus
        for p, i in pidx.items():
            dwell_out[p][:, m] = dwell_m[:, i]

    return Channels(monthly=out, dwell=dwell_out,
                    capacity_abs=capacity_abs, capacity_ratio=capacity_ratio)
