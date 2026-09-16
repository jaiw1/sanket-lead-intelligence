"""SD-S2 performance budget, and the mentor signals at the real size.

Plan §J.1 again: the whole point of vectorising these generators is that tuning
to the pre-registered criteria takes many regeneration rounds, so the budget is
hard — **under 60 s end to end at the default 60,000-customer book**, where "end
to end" means reading the book, generating, running every in-script assertion,
and writing the three CSVs, because that is what a tuning round actually costs.

The four window-shopper coefficients are re-fitted here at the full size too.
They are already asserted on the small book in
``tests/test_journeys_shoppers.py``; this is the version that matches the
wording of the requirement ("p < 0.01 at default size") and it is also the one
that would catch a signal that only looks negative because the sample is small.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from book import BookConfig
from book.build import build_frames
from journeys import JourneyConfig
from journeys.build import check, generate

#: End-to-end budget for the journey layer at the default book size.
FULL_BUDGET_S = 60.0
#: Generation-only budget, so a numpy regression cannot hide behind disk I/O.
FULL_GEN_BUDGET_S = 25.0
MAX_P = 0.01

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def full_book(tmp_path_factory):
    """The real 60,000 x 30 book, written to disk.  Not timed — the book has its
    own budget in ``tests/test_book_perf.py``."""
    out = tmp_path_factory.mktemp("full_book")
    cfg = BookConfig(out_dir=out)
    assert (cfg.n, cfg.months) == (60_000, 30), "the default book size moved; update the budget"
    panel, book, truth = build_frames(cfg)
    panel.to_csv(out / "customer_panel.csv", index=False)
    book.to_csv(out / "customer_book.csv", index=False)
    truth.to_csv(out / "liability_book_truth.csv", index=False, float_format="%.4g")
    return out


@pytest.fixture(scope="module")
def full_run(full_book):
    cfg = JourneyConfig(book_dir=full_book, out_dir=full_book)
    t0 = time.perf_counter()
    journeys, events, truth, _params = generate(cfg)
    t_gen = time.perf_counter() - t0
    stats = check(cfg, journeys, events, truth, full_book)
    journeys.to_csv(full_book / "journeys.csv", index=False)
    events.to_csv(full_book / "journey_events.csv", index=False)
    truth.to_csv(full_book / "journey_truth.csv", index=False)
    t_all = time.perf_counter() - t0
    return journeys, truth, stats, t_gen, t_all


def test_full_size_under_60s(full_run) -> None:
    _j, _t, _s, t_gen, t_all = full_run
    assert t_gen < FULL_GEN_BUDGET_S, f"journey generation took {t_gen:.1f}s"
    assert t_all < FULL_BUDGET_S, f"journey layer end-to-end took {t_all:.1f}s"


def test_volumes_at_the_default_size(full_run) -> None:
    _j, _t, stats, _tg, _ta = full_run
    assert 0.25 <= stats["customers_with_attempt"] <= 0.35
    assert 0.08 <= stats["recovery_rate"] <= 0.10
    assert 0.25 <= stats["shopper_share_of_dropoffs"] <= 0.35
    assert stats["window_respect"] >= 0.90


@pytest.mark.parametrize("signal", ["answers_blank_ratio", "income_refused",
                                    "fee_balk", "doc_refusal"])
def test_four_mentor_signals_are_negative_at_default_size(full_run, signal: str) -> None:
    journeys, _t, _s, _tg, _ta = full_run
    y = (journeys.outcome == "disbursed").to_numpy().astype(int)
    x = sm.add_constant(pd.DataFrame({
        "answers_blank_ratio": journeys.answers_blank_ratio.to_numpy(),
        "income_refused": 1 - journeys.income_shared.to_numpy(),
        "fee_balk": journeys.fee_balk.fillna(0).to_numpy(),
        "doc_refusal": journeys.doc_refusal.fillna(0).to_numpy(),
    }))
    r = sm.Logit(y, x).fit(disp=0)
    assert float(r.params[signal]) < 0, f"{signal} is positive at the default size"
    assert float(r.pvalues[signal]) < MAX_P


def test_generation_scales_roughly_linearly(tmp_path) -> None:
    """Guard against an accidental O(N^2) in the attempt or clock passes."""
    times = []
    for n in (5_000, 20_000):
        out = tmp_path / f"b{n}"
        out.mkdir()
        cfg = BookConfig(n=n, months=30, out_dir=out)
        panel, book, truth = build_frames(cfg)
        panel.to_csv(out / "customer_panel.csv", index=False)
        book.to_csv(out / "customer_book.csv", index=False)
        truth.to_csv(out / "liability_book_truth.csv", index=False, float_format="%.4g")
        t0 = time.perf_counter()
        generate(JourneyConfig(book_dir=out, out_dir=out))
        times.append(time.perf_counter() - t0)
    assert times[1] < 8 * max(times[0], 0.05), \
        f"{times[0]:.2f}s -> {times[1]:.2f}s for 4x the customers"


def test_the_clock_pass_is_not_the_bottleneck(full_run) -> None:
    """A sanity check on the shape of the work: one row per attempt, a handful of
    events each, nothing quadratic in the customer count."""
    journeys, truth, _s, _tg, _ta = full_run
    assert len(journeys) == len(truth)
    assert 15_000 < len(journeys) < 30_000, f"{len(journeys)} attempts at 60,000 customers"
    assert np.isfinite(journeys.journey_days.dropna().to_numpy()).all()
