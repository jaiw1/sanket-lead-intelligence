# -*- coding: utf-8 -*-
"""SM-5 — a real EMI: a fetched API 473 schedule where the bank computed one, the
API 433 rate through a standard annuity formula where it did not, and the flat
``TYPICAL_EMI`` table only if both are missing.

Three sources, in that order, and :data:`EMI_SOURCE` says which one every product
actually used:

===============================  ==========================================
``BANK_API_473_schedule``        the bank's own amortisation engine answered
                                 for this product's reference ticket
``BANK_API_433_sandbox_fixture`` the 433 rate through :func:`annuity_emi`
``TYPICAL_EMI``                  neither was available (a broken reference
                                 table; the retained flat constant)
===============================  ==========================================

The sandbox is a keyed store, not a blob
----------------------------------------
An earlier reading of this sandbox — from API 433, the one endpoint that *does*
return a 106-key kitchen-sink record — concluded that it "serves the same
response to every endpoint regardless of the request body". It does not. Every
other API returns its own structured record, and an unknown key comes back as
``{"message": "Data not found", "sentKey": "acctId#SANDBOX-ACCT-3"}``. What is true
is that the store holds a **handful** of sample customers and accounts, so a 200
proves the shape and the wiring and says nothing about this book's 60,000
synthetic customers. :data:`SANDBOX_FIXTURE` records that, and every field derived
from 433 carries ``BANK_API_433_sandbox_fixture`` rather than a bare ``BANK_API``.

API 433 — the rate
------------------
``data/bank/SCHEMA.md`` documents 433 as product-level, no customer id, feeding
``product_rate_code`` / ``card_rate_pa``. Its record carries two rate readings:

* ``rateInfo.effectiveRate`` (12.75%, alongside a matching ``baseRate`` and a
  penal slab table) — the rate-card reading, which is what ``SCHEMA.md`` maps 433
  onto (``card_rate_pa``).
* ``loanInfo.netIntRate`` (8.75%) — sits next to ``loanAmt`` / ``disbAmt`` /
  ``emiAmount`` for an *existing* loan already on the books, not a fresh quote.

Per the brief — "if the blob has one rate, use it for all and say so" — every
product prices off :data:`UNIFORM_RATE_PA` (the ``rateInfo`` reading);
``loanInfo.netIntRate`` is kept alongside for the record and used only as a sanity
check on the amortisation formula (see ``tests/test_model_emi.py``).

API 473 — the schedule
----------------------
``generateLoanRepaymentScheduletest`` was long recorded here as an API that "has
never returned a body in this sandbox at all". **That was wrong** — it was absent
from 433's composite record, and absence from that record was mistaken for absence
from the sandbox. It is a live amortisation engine: give it a principal, a rate
and an instalment count and it returns ``lamodRepaymentLL`` (the level instalment)
and ``oamortLL`` (one row per month, with the interest/principal split and the
closing balance).

``rrsquad-platform``'s batch pull asks it once per reference ticket
(``batch/pull.py::TICKET_LADDER``), so ``data/bank/pulled.json`` carries six real
bank-computed schedules and :func:`schedule_for` returns the bank's rows rather
than ours. :func:`amortisation_schedule` — the same reducing-balance annuity, kept
as the fallback and as the thing the bank's answer is checked against — is used
only when a product has no fetched schedule.

**The two agree to the paise.** All six reference tickets were fetched on
2026-09-17 and every one matches :func:`annuity_emi` exactly (personal ₹10,072.10,
gold ₹13,380.00, auto ₹13,575.18, education ₹9,028.16, home ₹34,614.35, lap
₹24,976.74), so adopting the bank's schedule moved no number downstream. That is a
result, not an assumption: ``tests/test_model_emi.py`` asserts it against the
captured schedules, and if the bank's engine ever disagrees the test says so
rather than the difference landing silently in a lead's EMI.
"""


from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from book.products import PRODUCTS, TYPICAL_EMI  # noqa: F401 (re-exported fallback)

#: This repo's root, so the module can find ``data/bank/pulled.json`` on import without
#: every caller having to hand it a path. ``src/model/emi.py`` -> ``<repo>``.
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

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
#: 433 record — kept for the sanity check, never used to price a new lead.
LOAN_INFO: Final[dict[str, float]] = dict(net_int_rate_pa=8.75, loan_amt=2_000_000.0,
                                          loan_period_months=240, emi_amount=16_800.0)

#: The rate every product prices off, absent a per-product 433 call.
UNIFORM_RATE_PA: Final[float] = RATE_INFO["effective_rate_pa"]

#: The three ``emi_source`` values, best to worst. Nothing else is ever emitted, and a
#: consumer can read the ladder straight off the tag: a fetched bank schedule, a bank rate
#: through our own formula, or neither.
EMI_SOURCE_SCHEDULE: Final[str] = "BANK_API_473_schedule"
EMI_SOURCE_BANK: Final[str] = "BANK_API_433_sandbox_fixture"
EMI_SOURCE_TYPICAL: Final[str] = "TYPICAL_EMI"

#: What ``amortisation_schedules[].provenance.schedule`` carries. ``SCHEDULE_SOURCE_BANK``
#: is the same string as :data:`EMI_SOURCE_SCHEDULE` on purpose: the number and the rows
#: come from one fetched response, and two tags for one source would invite them to drift.
SCHEDULE_SOURCE_BANK: Final[str] = EMI_SOURCE_SCHEDULE
SCHEDULE_SOURCE_DERIVED: Final[str] = "DERIVED_FROM_433"

#: Where the platform batch leaves what each API answered. Gitignored; absent on a checkout
#: that has never run a pull, which is why every read of it degrades rather than raises.
PULLED_PATH: Final[Path] = REPO_ROOT / "data" / "bank" / "pulled.json"

#: How far a fetched schedule's implied rate may sit from :data:`UNIFORM_RATE_PA` before it
#: is treated as pricing a different loan and ignored. A tenth of a basis point: the guard
#: is against reading someone else's ticket, not against rounding.
RATE_TOLERANCE_PA: Final[float] = 0.001

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



# --------------------------------------------------------------------------- #
# API 473 — reading a fetched schedule out of the platform's pull
# --------------------------------------------------------------------------- #

def _amount(block: Any) -> float | None:
    """``{"amountValue": "4218.95", "currencyCode": "INR"}`` -> ``4218.95``."""
    if not isinstance(block, dict):
        return None
    try:
        return float(str(block.get("amountValue")))
    except (TypeError, ValueError):
        return None


def _amort_rows(record: Any) -> list[dict]:
    """``oamortLL`` out of whichever envelope this record arrived in.

    The platform's ``slice_response`` unwraps 473 to ``{lamodRepaymentLL, oamortLL}``, the
    spreadsheet contract nests the same thing under ``result``, and the raw response wraps it
    in ``loanModellingSchOutputVO``. All three are accepted; none is assumed.
    """
    node = record
    for _ in range(3):
        if not isinstance(node, dict):
            return []
        if isinstance(node.get("oamortLL"), list):
            return [r for r in node["oamortLL"] if isinstance(r, dict)]
        node = node.get("loanModellingSchOutputVO") or node.get("result")
    return []


def parse_schedule(record: Any) -> dict | None:
    """One 473 record as ``{principal, tenor_months, rate_pa, emi, rows}``, or ``None``.

    Everything is read *off the schedule itself* rather than off the request we sent, so a
    schedule that came back describing a different loan than the one asked for is caught by
    :func:`bank_schedule`'s match instead of being trusted because of what we typed.
    """
    rows = _amort_rows(record)
    if not rows:
        return None
    out: list[dict] = []
    opening_first = interest_first = None
    emi = None
    for n, row in enumerate(rows, start=1):
        block = row.get("amortStruct")
        if not isinstance(block, dict):
            return None
        closing = _amount(block.get("princOutStanding"))
        principal = _amount(block.get("princAmt"))
        interest = _amount(block.get("intAmt"))
        instalment = _amount(block.get("instlAmt"))
        if None in (closing, principal, interest, instalment):
            return None
        opening = closing + principal
        if n == 1:
            opening_first, interest_first, emi = opening, interest, instalment
        out.append(dict(n=n, opening=round(opening, 2), emi=round(instalment, 2),
                        interest=round(interest, 2), principal=round(principal, 2),
                        closing=round(closing, 2)))
    if not opening_first or emi is None or interest_first is None:
        return None
    # The rate the bank actually charged in month one, not the rate we asked for.
    rate_pa = (interest_first / opening_first) * 1200.0
    return dict(principal=round(opening_first, 2), tenor_months=len(out),
                rate_pa=round(rate_pa, 6), emi=round(emi, 2), rows=out)


def load_bank_schedules(path: Path | None = None) -> dict[tuple[int, int], dict]:
    """Every usable API 473 schedule in ``data/bank/pulled.json``, keyed by (principal, tenor).

    Returns ``{}`` — never raises — when the file is absent (no pull has run on this
    checkout), unreadable, or carries no answered 473 records. That is the ordinary case on
    a fresh clone, and it is what makes the 433 fallback the *reachable* path it has to be.
    """
    path = Path(path) if path is not None else PULLED_PATH
    try:
        pulled = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entry = (pulled.get("apis") or {}).get("473") if isinstance(pulled, dict) else None
    if not isinstance(entry, dict) or entry.get("provenance") != "BANK_API":
        return {}
    found: dict[tuple[int, int], dict] = {}
    for record in entry.get("records") or []:
        parsed = parse_schedule(record)
        if parsed is None:
            continue
        found.setdefault((int(round(parsed["principal"])), parsed["tenor_months"]), parsed)
    return found


#: Read once, at import. A run that wants a different pull passes a path to
#: :func:`load_bank_schedules` and calls :func:`refresh` — the tests do exactly that.
BANK_SCHEDULES: dict[tuple[int, int], dict] = load_bank_schedules()


def bank_schedule(product: str) -> dict | None:
    """The fetched schedule for ``product``'s reference ticket, if the bank computed one.

    A schedule counts only if its principal, tenor *and* implied rate all match what this
    module would otherwise have assumed. A ladder entry that drifts out of step with
    :data:`REFERENCE_PRINCIPAL` is therefore silently not used rather than quietly repricing
    a product off somebody else's ticket — and ``emi_source`` drops to the 433 tag, which is
    the visible signal that it happened.
    """
    principal = REFERENCE_PRINCIPAL.get(product)
    tenor = REFERENCE_TENOR_MONTHS.get(product)
    if not principal or not tenor:
        return None
    found = BANK_SCHEDULES.get((int(principal), int(tenor)))
    if found is None:
        return None
    if abs(found["rate_pa"] - UNIFORM_RATE_PA) > RATE_TOLERANCE_PA:
        return None
    return found


def schedule_for(product: str) -> tuple[list[dict], str]:
    """``(rows, source)`` — the bank's own amortisation if we have it, else ours.

    The rows are the same six columns either way (``n`` / ``opening`` / ``emi`` /
    ``interest`` / ``principal`` / ``closing``), so a consumer reads one shape and the tag
    tells it where the numbers came from.
    """
    found = bank_schedule(product)
    if found is not None:
        return found["rows"], SCHEDULE_SOURCE_BANK
    rows = amortisation_schedule(REFERENCE_PRINCIPAL[product], UNIFORM_RATE_PA,
                                 REFERENCE_TENOR_MONTHS[product])
    return rows, SCHEDULE_SOURCE_DERIVED


def _reference_emi_and_source(product: str) -> tuple[int, str]:
    """The reference EMI on ``product``'s reference ticket, with its source tag.

    The three-step ladder, in order:

    1. **The bank's own schedule.** If API 473 amortised exactly this ticket, take its
       level instalment — ``BANK_API_473_schedule``.
    2. **The bank's rate through our formula.** Otherwise price the ticket off the single
       API 433 rate — ``BANK_API_433_sandbox_fixture``.
    3. **The flat table.** If the reference table or the rate is missing a product, fall
       back to ``TYPICAL_EMI`` — deliberately retained, not dead code; this is the path
       ``tests/test_model_emi.py`` forces to prove it is reachable.

    Every step rounds to the nearest ₹100, as SM-5 always has: what a lead is told is an
    indicative instalment, and quoting it to the paise would claim a precision no
    reference ticket has. Step 1 and step 2 agree on all six products, so the rounding is
    not what hides a disagreement — the tests check the unrounded numbers too.
    """
    try:
        principal = REFERENCE_PRINCIPAL[product]
        tenor = REFERENCE_TENOR_MONTHS[product]
        rate = UNIFORM_RATE_PA
        if rate is None:
            raise KeyError("no sandbox rate available")
        fetched = bank_schedule(product)
        raw = fetched["emi"] if fetched is not None else annuity_emi(principal, rate, tenor)
        source = EMI_SOURCE_SCHEDULE if fetched is not None else EMI_SOURCE_BANK
        value = int(round(raw, -2))
        if value <= 0:
            raise ValueError("non-positive EMI")
        return value, source
    except (KeyError, ValueError, ZeroDivisionError):
        return TYPICAL_EMI[product], EMI_SOURCE_TYPICAL


#: Precomputed once, at import time: the reference EMI and its source, per
#: product.  ``REFERENCE_EMI`` is what replaces ``TYPICAL_EMI`` at every call
#: site (``model.pack``'s capacity check and the product-menu display).
_REF = {p: _reference_emi_and_source(p) for p in PRODUCTS}
REFERENCE_EMI: dict[str, int] = {p: v[0] for p, v in _REF.items()}
EMI_SOURCE: dict[str, str] = {p: v[1] for p, v in _REF.items()}


def refresh(path: Path | None = None) -> dict[str, str]:
    """Re-read the pull and recompute every product's EMI and source. Returns `EMI_SOURCE`.

    Import time is the wrong moment to have read a gitignored file that a batch run may
    have rewritten since, and a test that wants the 433 path cannot unwrite one. Both get
    this: hand it a path (or one that does not exist) and the module re-derives from it.
    """
    global BANK_SCHEDULES
    BANK_SCHEDULES = load_bank_schedules(path)
    ref = {p: _reference_emi_and_source(p) for p in PRODUCTS}
    REFERENCE_EMI.clear()
    REFERENCE_EMI.update({p: v[0] for p, v in ref.items()})
    EMI_SOURCE.clear()
    EMI_SOURCE.update({p: v[1] for p, v in ref.items()})
    return dict(EMI_SOURCE)


def reference_emi(product: str) -> int:
    """The number every other lane should read instead of ``TYPICAL_EMI[product]``."""
    return REFERENCE_EMI[product]


def indicative_label(product: str) -> str:
    """A label describing what :func:`reference_emi` is and where it came from —
    what ``product_menu[].indicative_emi`` carries once ``emi`` is a real number.

    Three sources, three sentences. A reader who only ever sees this string still learns
    whether the bank computed the number, whether we computed it off the bank's rate, or
    whether neither happened.
    """
    principal = REFERENCE_PRINCIPAL.get(product)
    tenor = REFERENCE_TENOR_MONTHS.get(product)
    source = EMI_SOURCE[product]
    if source == EMI_SOURCE_SCHEDULE and principal and tenor:
        return (f"Indicative EMI on a ₹{principal:,}/{tenor}-month {product} loan @ "
                f"{UNIFORM_RATE_PA:g}% p.a. (IDBI Atlas sandbox schedule, API 473)")
    if source == EMI_SOURCE_BANK and principal and tenor:
        return (f"Indicative EMI on a ₹{principal:,}/{tenor}-month {product} loan @ "
                f"{UNIFORM_RATE_PA:g}% p.a. (IDBI Atlas sandbox rate, API 433)")
    return f"Indicative EMI on a typical {product} ticket (assumed, no bank rate available)"


__all__ = [
    "SANDBOX_FIXTURE", "RATE_INFO", "LOAN_INFO", "UNIFORM_RATE_PA", "PULLED_PATH",
    "EMI_SOURCE_SCHEDULE", "EMI_SOURCE_BANK", "EMI_SOURCE_TYPICAL",
    "SCHEDULE_SOURCE_BANK", "SCHEDULE_SOURCE_DERIVED", "BANK_SCHEDULES",
    "REFERENCE_PRINCIPAL", "REFERENCE_TENOR_MONTHS", "REFERENCE_EMI", "EMI_SOURCE",
    "annuity_emi", "amortisation_schedule", "parse_schedule", "load_bank_schedules",
    "bank_schedule", "schedule_for", "refresh", "reference_emi", "indicative_label",
]
