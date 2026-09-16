"""
11 Fairness — including the gig-worker failure we do not hide

Pre-registered criteria this runner answers: SK-23, SK-24

Consumes
--------
* ``data/liability_book.csv``
      - cust_id, segment (occupation), age, city_tier, tenure_m, consent,
        dnd, product, event_month, channel, true_income — today's file is
        data/customer_book.csv; plan §B L6 SD-S1 renames and extends it to
        60k customers x 30 months x 6 products
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
* ``figures/fairness_contact_rates.png``
* ``figures/gig_gap.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
Contact rate and true-positive rate by group for occupation_segment,
income_band, city_tier and age band at the live contact budget. Report the
four-fifths ratio and the gaps. Then the quantified gig-worker statement:
irregular gig income reads as instability to a model trained mostly on
salaried credits, so gig workers are under-contacted — the number goes in
the report and in the README's 'What we did not build, and why'.

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
    "data/liability_book_truth.csv",
    "app/public/sanket_data.json",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    raise NotImplementedError(
        "runner 11 pending: needs data/liability_book.csv (segment, city_tier, "
        "age), data/liability_book_truth.csv (true_income for income bands), "
        "app/public/sanket_data.json (queue[] at the contact budget)"
    )
