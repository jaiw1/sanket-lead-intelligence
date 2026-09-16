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
    """The whole lane generated on :func:`small_book`, plus its checked stats.

    One ``generate_all`` for the session: the journey layer (SD-S2/S3), the
    campaign history (SD-S6) and the drop-off population with its labels
    (SD-S4), so the label tests are measuring the same draw the journey tests
    are.
    """
    from journeys import JourneyConfig, substream
    from journeys.build import check, generate_all
    from journeys.labels import check as label_check

    cfg = JourneyConfig(book_dir=small_book, out_dir=small_book)
    b = generate_all(cfg)
    stats = check(cfg, b.journeys, b.events, b.truth, small_book)
    lstats = label_check(b.labels, b.label_truth, b.params["labels"],
                         substream(cfg.seed, "measurement"))
    return SimpleNamespace(cfg=cfg, book_dir=small_book, journeys=b.journeys, events=b.events,
                           truth=b.truth, campaigns=b.campaigns, labels=b.labels,
                           label_truth=b.label_truth, params=b.params, stats=stats,
                           label_stats=lstats, anchor=(2024, 4))


#: A model small enough to fit inside the suite: 150 trees, one seed, no
#: out-of-time / permuted-label / ladder exhibits.  The five-seed spread and the
#: expensive exhibits belong to a real run.
MODEL_KW = dict(seed=7, seeds=(7,), quick=True, queue_size=40, excluded_sample=6,
                lgbm=dict(n_estimators=150, learning_rate=0.06, num_leaves=31,
                          min_child_samples=40, subsample=0.8, subsample_freq=1,
                          colsample_bytree=0.8, n_jobs=-1, verbose=-1))


@pytest.fixture(scope="session")
def model_dir(journeys: SimpleNamespace) -> Path:
    """The small book plus the journey / label CSVs, written to disk.

    Written rather than passed in memory for the same reason the journey fixture
    reads the book back off disk: ``src/score_and_pack.py`` loads CSVs, and a
    schema drift between what the generator returns and what the scorer reads
    would show up here first.
    """
    d = journeys.book_dir
    if not (d / "labels.csv").exists():
        journeys.journeys.to_csv(d / "journeys.csv", index=False)
        journeys.events.to_csv(d / "journey_events.csv", index=False)
        journeys.campaigns.to_csv(d / "campaigns.csv", index=False)
        journeys.labels.to_csv(d / "labels.csv", index=False)
        journeys.label_truth.to_csv(d / "label_truth.csv", index=False)
    return d


@pytest.fixture(scope="session")
def model_run(model_dir: Path) -> SimpleNamespace:
    """SM-1's model fitted once: the frames, the split, the ranker, the scores."""
    from model import ModelConfig
    from model.frame import as_categorical, customer_month_frame, load_tables, stack
    from model.train import fit_ranker, split_customers

    cfg = ModelConfig(root=model_dir.parent, **MODEL_KW)
    tables = load_tables(model_dir)
    base = as_categorical(customer_month_frame(tables))
    stacked = as_categorical(stack(base))
    split = split_customers(base["cust_id"].unique(), cfg, cfg.seed)
    ranker = fit_ranker(stacked, split, cfg, with_unconstrained=True)
    return SimpleNamespace(cfg=cfg, data_dir=model_dir, tables=tables, base=base,
                           stacked=stacked, split=split, ranker=ranker,
                           P=ranker.matrix(stacked))


@pytest.fixture(scope="session")
def packed(model_dir: Path, tmp_path_factory) -> SimpleNamespace:
    """The whole ``score_and_pack`` export, run once on the small book."""
    from model import ModelConfig
    import model.pack as pack

    out = tmp_path_factory.mktemp("pack")
    cfg = ModelConfig(root=model_dir.parent, **MODEL_KW)
    real = pack.F.load_tables
    pack.F.load_tables = lambda _d: real(model_dir)
    try:
        payload = pack.run(cfg, out_json=out / "sanket_data.json",
                           metrics_json=out / "model_metrics.json", verbose=False)
    finally:
        pack.F.load_tables = real
    return SimpleNamespace(out=payload, json_path=out / "sanket_data.json",
                           metrics_path=out / "model_metrics.json", cfg=cfg)
