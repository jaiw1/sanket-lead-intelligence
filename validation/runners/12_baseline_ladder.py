"""
12 Baseline ladder — how much of 9-to-30 is the model

Pre-registered criteria this runner answers: SK-25

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
* ``figures/baseline_ladder.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
Four rungs on the same held-out book with the same CIs: random contact,
balance-ranked contact (what a branch does today), a logistic scorecard, and
the production LightGBM. Report precision@10% per rung. The rungs are
pre-registered so the comparison set cannot be chosen after the fact.

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
        "runner 12 pending: needs data/liability_book.csv (bal_avg via "
        "data/customer_panel.csv for the balance rung), "
        "data/application_journeys.csv (disburse_ts)"
    )
