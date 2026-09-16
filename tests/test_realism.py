"""SD-S7 — the realism suite, run on the default-size book and on a small one.

Two sizes, for two different reasons.

**Small / fast** (unmarked, runs on every ``pytest``): a book has to be a
useful size for ``realism.py``'s own checks to mean anything — a segment-share
or seasonality-ratio check on a few hundred rows is noise, not a finding. The
brief asked for ``--n 3000`` specifically; it was tried first and rejected: at
n=3000 (and even n=5,000-6,000) ``journeys.build.check()``'s own pre-registered
recovery-rate assertion (``0.08 <= recovery_rate <= 0.10``, plan §B/L6 SD-S4)
fails on more than half of the seeds tried, purely from Monte Carlo noise at
that population size — not a bug, and not this suite's assertion to loosen
(``src/journeys/**`` is frozen for this lane). ``tests/conftest.py`` already
established ``SMALL_N = 8_000`` as the smallest size that clears every
existing generator band reliably; this file reuses that number rather than
inventing a second "small" convention.

**Default / slow** (``-m slow``, deselected by default per ``pytest.ini``):
the real 60,000 x 30 book, generated fresh — the same size ``realism.py``'s
own module docstring shows as the default CLI invocation, and the size every
number in ``DATA_CARD.md``'s realism-check summary was measured at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import realism

#: Matches ``tests/conftest.py``'s ``SMALL_N`` — see the module docstring above
#: for why ``--n 3000``, tried first, is not reliable enough to use here.
SMALL_N = 8_000
SMALL_MONTHS = 30
DEFAULT_N = 60_000
DEFAULT_MONTHS = 30
SEED = 20260709


def _assert_clean(suite: "realism.Suite") -> None:
    failed = suite.failed()
    if failed:
        detail = "\n".join(f"  - {r.group}/{r.name}: observed={r.observed} expected={r.expected}"
                            for r in failed)
        pytest.fail(f"{len(failed)}/{len(suite.results)} realism checks failed:\n{detail}")
    assert suite.n_pass == len(suite.results)
    assert suite.group_count("impossible_states") >= 25, (
        "SD-S7's brief: at least 25 impossible-state assertions must actually have run")


def test_realism_suite_small_book(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Fast path: an 8,000 x 30 book + full journey/label/campaign layer,
    generated fresh into a temp dir and audited with every realism.py check."""
    out = tmp_path_factory.mktemp("realism_small")
    realism.generate_book_and_journeys(n=SMALL_N, months=SMALL_MONTHS, seed=SEED, out_dir=out)
    data = realism.load_data(out)
    suite = realism.run_suite(data, verbose=False)
    _assert_clean(suite)


@pytest.mark.slow
def test_realism_suite_default_size(tmp_path_factory: pytest.TempPathFactory) -> None:
    """The real 60,000 x 30 book.  Generation + the suite together run in well
    under a minute (DATA_CARD §8's generation budget plus realism.py's own
    ~15s of checks), which is why this is `slow` rather than skipped outright."""
    out = tmp_path_factory.mktemp("realism_default")
    cfg_n_months = (DEFAULT_N, DEFAULT_MONTHS)
    realism.generate_book_and_journeys(n=cfg_n_months[0], months=cfg_n_months[1], seed=SEED, out_dir=out)
    data = realism.load_data(out)
    suite = realism.run_suite(data, verbose=False)
    _assert_clean(suite)
    # a handful of headline numbers, so a silent generator regression that still
    # passes every band shows up as a changed assertion rather than nothing at all
    assert len(data.book) == DEFAULT_N
    assert len(data.journeys) > 15_000, "attempts at 60,000 customers should be in the tens of thousands"
    assert len(data.labels) > 50_000, "the drop-off population at 60,000 customers"


def test_load_data_reports_a_clear_error_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make_book.py"):
        realism.load_data(tmp_path)


def test_suite_result_reporting_shape() -> None:
    """The report contract test_realism.py and CI both rely on: PASS/FAIL,
    observed vs expected, a rationale, and a group large enough to be findable."""
    suite = realism.Suite(verbose=False)
    suite.check("demo", "always_true", True, 1, 1, "sanity")
    suite.check("demo", "always_false", False, 0, 1, "sanity")
    assert suite.n_pass == 1
    assert suite.n_fail == 1
    assert not suite.all_passed
    assert [r.name for r in suite.failed()] == ["always_false"]
    summary = suite.summary()
    assert summary["total"] == 2 and summary["passed"] == 1 and summary["failed"] == 1
    assert summary["by_group"]["demo"] == {"pass": 1, "fail": 1, "total": 2}
