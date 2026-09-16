"""
01 Held-out queue — baseline, precision at budget, window respect, shopper detection

Pre-registered criteria this runner answers: SK-01, SK-02, SK-03, SK-04, SK-05, SK-06

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
* ``app/public/sanket_data.json``
      - queue[].{cust_id, score, product_menu[].{product, prob, reason},
        retained_income, negative_chips[]}, metrics.{baseline,
        precision_curve[], per_product[], suppressed_count}

Produces
--------
* ``figures/precision_curve.png``
* ``figures/window_respect.png``
* one Result per criterion above: value, 95% CI, n (and `breakdown`
  with one dict per cell for the per-cut / per-portfolio / per-product ones)

Method, as pre-registered
-------------------------
Score the held-out consented book at the snapshot month. Report: the
random-contact disbursement rate (the 8-10% baseline), precision at the 10%
contact budget with a bootstrap CI and the same at 5% and 20%, the window
respect rate (of held-out converters inside the budget, the share disbursing
inside the offered product's pre-registered window), and the AUC of the
window-shopper signal against the generator's latent flag. Bootstrap
resamples at cust_id.

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
    "app/public/sanket_data.json",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    raise NotImplementedError(
        "runner 01 pending: needs data/liability_book.csv (cust_id, consent, "
        "product, event_month), data/application_journeys.csv (stage_reached, "
        "disburse_ts, abandon_ts), data/liability_book_truth.csv "
        "(window_shopper), app/public/sanket_data.json (queue[].score, "
        "metrics.baseline)"
    )
