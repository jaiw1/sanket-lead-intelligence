"""
03 Per-product floors, the macro average, and the full by-cut table

Pre-registered criteria this runner answers: SK-08, SK-09, SK-10

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
* ``data/liability_book_truth.csv  (PLANNED — generator ground truth)``
      - cust_id, window_shopper, persuadable, true_income, p_prod,
        p_win_start, p_win_end — latents the model never sees; used only
        as evaluation labels

Produces
--------
* ``figures/auc_by_product.png``
* ``figures/auc_by_cut_grid.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
AUC (and precision@10%) with a bootstrap CI and an n for every level of all
seven registered cuts. The product cut gates on all six products and on
their unweighted macro average; the other six cuts are reported. Income and
tenure bands come from the pre-registered binning rules in criteria.yaml.

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
    "data/liability_book_truth.csv",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    raise NotImplementedError(
        "runner 03 pending: needs data/liability_book.csv (product, segment, "
        "city_tier, tenure_m, channel), data/liability_book_truth.csv "
        "(true_income for the income bands), data/application_journeys.csv "
        "(stage_reached)"
    )
