# -*- coding: utf-8 -*-
"""SM-5 — a real EMI, from an API 433 rate and a standard amortisation formula,
replacing the hard-coded ``TYPICAL_EMI`` constant on every lead.

API 433 (rates) and API 473 (repayment schedule)
--------------------------------------------------
``data/bank/SCHEMA.md`` documents 433 as product-level, no customer id,
feeding ``product_rate_code`` / ``card_rate_pa``. A probe against the live IDBI
Atlas sandbox on 2026-09-16 returned exactly one canned JSON blob — the sandbox
serves the same response to every endpoint regardless of the request body
(``rrsquad-platform/batch/enrich.py``'s docstring calls this BR-6a) — so the
constants below are read off that single captured response rather than issued
per product; a sixth call would return the same numbers.  :data:`SANDBOX_FIXTURE`
records that this is the sandbox's canned data, not a live customer- or
product-specific quote, and every field derived from it downstream carries the
``BANK_API_433_sandbox_fixture`` tag rather than a bare ``BANK_API``.

The blob carries two rate readings:

* ``rateInfo.effectiveRate`` (12.75%, alongside a matching ``baseRate`` and a
  penal slab table) — the rate-card reading, which is what
  ``data/bank/SCHEMA.md`` maps 433 onto (``card_rate_pa``).
* ``loanInfo.netIntRate`` (8.75%) — sits next to ``loanAmt`` / ``disbAmt`` /
  ``emiAmount`` for an *existing* loan already on the books, not a fresh quote.

Per the brief — "if the blob has one rate, use it for all and say so" — every
product prices off :data:`UNIFORM_RATE_PA` (the ``rateInfo`` reading) until a
per-product 433 call against a live (non-canned) sandbox is available;
``loanInfo.netIntRate`` is kept alongside for the record and used only as a
sanity check on the amortisation formula (see ``tests/test_model_emi.py``).

API 473 (``generateLoanRepaymentScheduletest``) has never returned a body in
this sandbox at all — ``rrsquad-platform/app/atlas/adapters/a473_repayment_schedule.py``
says so plainly ("Absent from the live sandbox's canned blob ... one of the two
APIs whose shape we have never actually seen").  There is nothing to read a
schedule off, so :func:`amortisation_schedule` **derives** one with a standard
reducing-balance annuity formula from the 433 rate, tagged
:data:`SCHEDULE_SOURCE_DERIVED` rather than any flavour of ``BANK_API``.
"""

from __future__ import annotations

from typing import Final

from book.products import PRODUCTS, TYPICAL_EMI  # noqa: F401 (re-exported fallback)

# --------------------------------------------------------------------------- #
# API 433, as the IDBI Atlas sandbox actually returned it (2026-09-16 probe)
# --------------------------------------------------------------------------- #

SANDBOX_FIXTURE: Final[bool] = True

#: ``rateInfo`` verbatim (the fields this module reads), from the captured
#: sandbox response.  A ``penalRate`` and slab table also rode along; unused
#: here, since prospecting quotes the normal rate, not the overdue one.
RATE_INFO: Final[dict[str, float]] = dict(effective_rate_pa=12.75, base_rate_pa=12.75,
                                          penal_rate_pa=2.0)

#: ``loanInfo`` verbatim, describing an *existing* disbursed loan in the same
#: canned blob — kept for the sanity check, never used to price a new lead.
LOAN_INFO: Final[dict[str, float]] = dict(net_int_rate_pa=8.75, loan_amt=2_000_000.0,
                                          loan_period_months=240, emi_amount=16_800.0)

#: The rate every product prices off, absent a per-product 433 call.
UNIFORM_RATE_PA: Final[float] = RATE_INFO["effective_rate_pa"]

EMI_SOURCE_BANK: Final[str] = "BANK_API_433_sandbox_fixture"
EMI_SOURCE_TYPICAL: Final[str] = "TYPICAL_EMI"
SCHEDULE_SOURCE_DERIVED: Final[str] = "DERIVED_FROM_433"

# --------------------------------------------------------------------------- #
# reference ticket size and tenor per product — what "the typical loan of this
# kind" looks like, so a rate turns into a rupee EMI.  ``assumed``, the same
# convention ``book/products.py`` uses for the retired ``TYPICAL_EMI`` table.
# --------------------------------------------------------------------------- #

REFERENCE_PRINCIPAL: Final[dict[str, int]] = {
    "personal": 300_000, "gold": 150_000, "auto": 600_000,
    "education": 500_000, "home": 3_000_000, "lap": 2_000_000,
}
REFERENCE_TENOR_MONTHS: Final[dict[str, int]] = {
    "personal": 36, "gold": 12, "auto": 60, "education": 84, "home": 240, "lap": 180,
}


def annuity_emi(principal: float, annual_rate_pct: float, tenor_months: int) -> float:
    """The standard reducing-balance EMI: ``P * r * (1+r)^n / ((1+r)^n - 1)``.

    ``r`` is the *monthly* rate; ``annual_rate_pct`` is in percent (``12.75``,
    not ``0.1275``), matching the sandbox blob's own spelling.
    """
    if tenor_months <= 0:
        raise ValueError("tenor_months must be positive")
    if principal <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        return principal / tenor_months
    f = (1.0 + r) ** tenor_months
    return principal * r * f / (f - 1.0)


def amortisation_schedule(principal: float, annual_rate_pct: float,
                          tenor_months: int) -> list[dict]:
    """Month-by-month reducing-balance schedule: opening/emi/interest/principal/closing.

    Tagged :data:`SCHEDULE_SOURCE_DERIVED` by every caller — API 473 has never
    answered in this sandbox, so this *is* the schedule, not a stand-in for one.
    """
    emi = annuity_emi(principal, annual_rate_pct, tenor_months)
    r = (annual_rate_pct / 100.0) / 12.0
    rows: list[dict] = []
    opening = float(principal)
    for n in range(1, tenor_months + 1):
        interest = opening * r
        princ = emi - interest
        closing = max(0.0, opening - princ)
        rows.append(dict(n=n, opening=round(opening, 2), emi=round(emi, 2),
                         interest=round(interest, 2), principal=round(princ, 2),
                         closing=round(closing, 2)))
        opening = closing
    return rows


def _reference_emi_and_source(product: str) -> tuple[int, str]:
    """The bank-rate EMI on ``product``'s reference ticket, with its source tag.

    Falls back to ``TYPICAL_EMI`` — deliberately retained, not dead code — if
    the reference table or the sandbox rate is ever missing a product; this is
    the path :func:`reference_emi` exercises when the fallback is forced.
    """
    try:
        principal = REFERENCE_PRINCIPAL[product]
        tenor = REFERENCE_TENOR_MONTHS[product]
        rate = UNIFORM_RATE_PA
        if rate is None:
            raise KeyError("no sandbox rate available")
        value = int(round(annuity_emi(principal, rate, tenor), -2))
        if value <= 0:
            raise ValueError("non-positive EMI")
        return value, EMI_SOURCE_BANK
    except (KeyError, ValueError, ZeroDivisionError):
        return TYPICAL_EMI[product], EMI_SOURCE_TYPICAL


#: Precomputed once, at import time: the reference EMI and its source, per
#: product.  ``REFERENCE_EMI`` is what replaces ``TYPICAL_EMI`` at every call
#: site (``model.pack``'s capacity check and the product-menu display).
_REF = {p: _reference_emi_and_source(p) for p in PRODUCTS}
REFERENCE_EMI: Final[dict[str, int]] = {p: v[0] for p, v in _REF.items()}
EMI_SOURCE: Final[dict[str, str]] = {p: v[1] for p, v in _REF.items()}


def reference_emi(product: str) -> int:
    """The number every other lane should read instead of ``TYPICAL_EMI[product]``."""
    return REFERENCE_EMI[product]


def indicative_label(product: str) -> str:
    """A label describing what :func:`reference_emi` is and where it came from —
    what ``product_menu[].indicative_emi`` carries once ``emi`` is a real number.
    """
    principal = REFERENCE_PRINCIPAL.get(product)
    tenor = REFERENCE_TENOR_MONTHS.get(product)
    source = EMI_SOURCE[product]
    if source == EMI_SOURCE_BANK and principal and tenor:
        return (f"Indicative EMI on a ₹{principal:,}/{tenor}-month {product} loan @ "
                f"{UNIFORM_RATE_PA:g}% p.a. (IDBI Atlas sandbox rate, API 433)")
    return f"Indicative EMI on a typical {product} ticket (assumed, no bank rate available)"


__all__ = [
    "SANDBOX_FIXTURE", "RATE_INFO", "LOAN_INFO", "UNIFORM_RATE_PA",
    "EMI_SOURCE_BANK", "EMI_SOURCE_TYPICAL", "SCHEDULE_SOURCE_DERIVED",
    "REFERENCE_PRINCIPAL", "REFERENCE_TENOR_MONTHS", "REFERENCE_EMI", "EMI_SOURCE",
    "annuity_emi", "amortisation_schedule", "reference_emi", "indicative_label",
]
