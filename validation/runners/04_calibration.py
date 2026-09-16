"""
04 Calibration — the probability the RM is shown

Pre-registered criteria this runner answers: SK-11, SK-12

Consumes
--------
* ``data/liability_book.csv``
      - cust_id, segment (occupation), age, city_tier, tenure_m, consent,
        dnd, product, event_month, channel, true_income — today's file is
        data/customer_book.csv; plan §B L6 SD-S1 renames and extends it to
        60k customers x 30 months x 6 products
* ``data/application_journeys.csv  (PLANNED — plan §B L6 SD-S2)``
      - one row per application attempt: cust_id, product, attempt_id,
        channel, start_ts, stage_reached, abandon_ts, disburse_ts,
        fee_paid, fee_balk, doc_refusal, income_refused, blank_ratio,
        revisit_count
* ``app/public/sanket_data.json``
      - queue[].{cust_id, score, product_menu[].{product, prob, reason},
        retained_income, negative_chips[]}, metrics.{baseline,
        precision_curve[], per_product[], suppressed_count}

Produces
--------
* ``figures/reliability_overall.png``
* ``figures/ece_by_product.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
Isotonic-calibrate the scores, then compute expected calibration error
overall and per product, plus the reliability curve. The packed score in
app/public/sanket_data.json must be the calibrated one; flag any drift
between what is measured here and what the cockpit renders.

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
    "data/application_journeys.csv",
    "app/public/sanket_data.json",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    raise NotImplementedError(
        "runner 04 pending: needs data/liability_book.csv (product), "
        "data/application_journeys.csv (disburse_ts), app/public/sanket_data.json "
        "(queue[].score)"
    )
