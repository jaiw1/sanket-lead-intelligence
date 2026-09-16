"""Put ``src/`` on the import path so tests can ``import book`` / ``import journeys``.

Also builds, once per session, a small book and the journey layer on top of it.
Journeys are generated *from written CSVs* rather than from in-memory frames,
because reading the book back off disk is exactly what
``src/make_journeys.py`` does and is where a schema drift would show up first.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

#: Small enough that the whole suite stays quick, large enough that the
#: window-shopper coefficients are significant at p < 0.01 (see
#: ``tests/test_journeys_shoppers.py``); the default 60,000-customer book is
#: exercised separately in ``tests/test_journeys_perf.py``.
SMALL_N = 8_000
SMALL_MONTHS = 30


@pytest.fixture(scope="session")
def small_book(tmp_path_factory) -> Path:
    """A written 8,000 x 30 book: the three CSVs the journey layer reads."""
    from book import BookConfig
    from book.build import build_frames

    out = tmp_path_factory.mktemp("book")
    cfg = BookConfig(n=SMALL_N, months=SMALL_MONTHS, out_dir=out)
    panel, book, truth = build_frames(cfg)
    panel.to_csv(out / "customer_panel.csv", index=False)
    book.to_csv(out / "customer_book.csv", index=False)
    truth.to_csv(out / "liability_book_truth.csv", index=False, float_format="%.4g")
    return out


@pytest.fixture(scope="session")
def journeys(small_book: Path) -> SimpleNamespace:
    """The journey layer generated on :func:`small_book`, plus its checked stats."""
    from journeys import JourneyConfig
    from journeys.build import check, generate

    cfg = JourneyConfig(book_dir=small_book, out_dir=small_book)
    j, e, t, params = generate(cfg)
    stats = check(cfg, j, e, t, small_book)
    return SimpleNamespace(cfg=cfg, book_dir=small_book, journeys=j, events=e,
                           truth=t, params=params, stats=stats, anchor=(2024, 4))
