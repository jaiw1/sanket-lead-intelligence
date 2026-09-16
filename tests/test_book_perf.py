"""SD-S1 performance budget.

Plan §J.1: tuning the generator to the pre-registered SANKET criteria needs
15-20 regeneration rounds.  At the pre-SD-S1 row-loop's throughput a single
60,000 x 30 book would take minutes, which turns a tuning round into hours.
The budget the plan sets is therefore hard:

* ``--legacy-size`` (15,000 x 27)  — under 10 s end to end
* the new default (60,000 x 30)    — under 60 s end to end

"End to end" means generation *and* writing the three CSVs, because that is what
a tuning round actually costs.  Generation alone is asserted separately with a
tighter budget so a regression in the numpy work is not masked by disk speed.
"""

from __future__ import annotations

import time

import pytest

from book import BookConfig
from book.build import build_frames, check

#: End-to-end budgets from plan §B/L6 SD-S1.
LEGACY_BUDGET_S = 10.0
FULL_BUDGET_S = 60.0
#: Generation-only budgets, so a numpy regression cannot hide behind disk I/O.
LEGACY_GEN_BUDGET_S = 3.0
FULL_GEN_BUDGET_S = 15.0


def _run(cfg: BookConfig, out_dir) -> tuple[float, float]:
    """Return ``(generation_seconds, end_to_end_seconds)``."""
    t0 = time.perf_counter()
    panel, book, truth = build_frames(cfg)
    t_gen = time.perf_counter() - t0
    check(cfg, panel, book, truth)
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out_dir / "customer_panel.csv", index=False)
    book.to_csv(out_dir / "customer_book.csv", index=False)
    truth.to_csv(out_dir / "liability_book_truth.csv", index=False, float_format="%.4g")
    return t_gen, time.perf_counter() - t0


def test_legacy_size_under_10s(tmp_path) -> None:
    cfg = BookConfig.legacy(out_dir=tmp_path)
    t_gen, t_all = _run(cfg, tmp_path)
    assert t_gen < LEGACY_GEN_BUDGET_S, f"legacy generation took {t_gen:.1f}s"
    assert t_all < LEGACY_BUDGET_S, f"legacy end-to-end took {t_all:.1f}s"


@pytest.mark.slow
def test_full_size_under_60s(tmp_path) -> None:
    cfg = BookConfig(out_dir=tmp_path)
    assert (cfg.n, cfg.months) == (60_000, 30), "the default size moved; update the budget"
    t_gen, t_all = _run(cfg, tmp_path)
    assert t_gen < FULL_GEN_BUDGET_S, f"60,000 x 30 generation took {t_gen:.1f}s"
    assert t_all < FULL_BUDGET_S, f"60,000 x 30 end-to-end took {t_all:.1f}s"


@pytest.mark.slow
def test_generation_scales_roughly_linearly() -> None:
    """Guard against an accidental O(N^2): 4x the customers must cost well under 4x."""
    small = BookConfig(n=5_000, months=30)
    large = BookConfig(n=20_000, months=30)
    t0 = time.perf_counter(); build_frames(small); t_small = time.perf_counter() - t0
    t0 = time.perf_counter(); build_frames(large); t_large = time.perf_counter() - t0
    assert t_large < 8 * max(t_small, 0.05), f"{t_small:.2f}s -> {t_large:.2f}s for 4x the customers"
