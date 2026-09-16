"""
05 Menu of four, top-1, and the direction of the shopper signals

Pre-registered criteria this runner answers: SK-13, SK-14, SK-15

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
* ``data/liability_book_truth.csv  (PLANNED — generator ground truth)``
      - cust_id, window_shopper, persuadable, true_income, p_prod,
        p_win_start, p_win_end — latents the model never sees; used only
        as evaluation labels
* ``app/public/sanket_data.json``
      - queue[].{cust_id, score, product_menu[].{product, prob, reason},
        retained_income, negative_chips[]}, metrics.{baseline,
        precision_curve[], per_product[], suppressed_count}

Produces
--------
* ``figures/menu_hit_rate.png``
* ``figures/shopper_signal_directions.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
Among held-out converters, the share whose realised product is inside the
model's top-4 product_menu, and the same at rank 1. Then the sign of the
mean signed contribution of each of the four window-shopper signals — vague
or blank answers, refusal to share income, the Rs 1,000 fee balk, and
document refusal — all four of which must be negative.

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
    "data/liability_book_truth.csv",
    "app/public/sanket_data.json",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    raise NotImplementedError(
        "runner 05 pending: needs data/application_journeys.csv (product, "
        "disburse_ts, fee_balk, doc_refusal, income_refused, blank_ratio), "
        "app/public/sanket_data.json (queue[].product_menu), "
        "data/liability_book_truth.csv (window_shopper)"
    )
