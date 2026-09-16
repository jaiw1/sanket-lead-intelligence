"""
10 Stress — the pre-registered scenarios

Pre-registered criteria this runner answers: SK-22

Consumes
--------
* ``data/liability_book.csv``
      - cust_id, segment (occupation), age, city_tier, tenure_m, consent,
        dnd, product, event_month, channel, true_income — today's file is
        data/customer_book.csv; plan §B L6 SD-S1 renames and extends it to
        60k customers x 30 months x 6 products
* ``data/customer_panel.csv``
      - cust_id, month, date, credits, bal_avg, bal_min, rent, fuel_cab,
        school_fees, ecommerce, ext_emi, has_auto_emi, fd_bal, dwell_home,
        dwell_auto, dwell_pl, plus the SD-S1 additions upi_p2m,
        salary_credit_day, emi_outflow_to_other_bank, card_spend,
        insurance_premium
* ``data/application_journeys.csv  (PLANNED — plan §B L6 SD-S2)``
      - one row per application attempt: cust_id, product, attempt_id,
        channel, start_ts, stage_reached, abandon_ts, disburse_ts,
        fee_paid, fee_balk, doc_refusal, income_refused, blank_ratio,
        revisit_count

Produces
--------
* ``figures/stress_precision.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
Four scenarios against the base run: consent withdrawal at scale, a
suppression-rule sweep (plan §B L6 SD-S6), cross-bank transaction data
(595/739) unavailable, and a doubled window-shopper share. Report
precision@10% under each. The scenario SET is pre-registered so it cannot be
chosen after seeing which ones look good.

Status
------
STUB. Raises NotImplementedError, which the harness records as `pending` for
every criterion above — never as a pass. The interface is written down now, ahead
of the first model result, while the data lanes are still changing the shape of
these files; implementing against a shape that is mid-flight would be worse than
documenting it.
"""

from __future__ import annotations

from validation.criteria import Criterion, Result, RunnerContext

#: Files this runner will read, relative to the repository root.
INPUTS: tuple[str, ...] = (
    "data/liability_book.csv",
    "data/customer_panel.csv",
    "data/application_journeys.csv",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    raise NotImplementedError(
        "runner 10 pending: needs data/liability_book.csv (consent, dnd) and "
        "data/customer_panel.csv regenerated per scenario, plus the suppression "
        "rules from src/make_book.py"
    )
