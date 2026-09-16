"""
Fixtures for the runner tests (`test_status_mapping.py`, `test_report_schema.py`).

`src/` on the import path
--------------------------
So a test can `import model.metrics` / `import realism` the same way
`validation/runners/_shared.py`'s `_ensure_src_on_path` does at runtime.

`small_metrics_root` — a real, small, fast pipeline run
----------------------------------------------------------
`tests/conftest.py` (the model lane's own suite) already established
``SMALL_N = 8_000`` as "the smallest size that clears every existing generator
band reliably" (see its module docstring, and `tests/test_realism.py`'s note
that `--n 3000` was tried first and rejected — Monte Carlo noise at that size
fails `journeys.build.check()`'s own pre-registered recovery-rate assertion on
more than half of seeds tried). This fixture reuses that number rather than
inventing a second "small" convention, and reuses `realism.generate_book_and_journeys`
(never `src/score_and_pack.py`'s hardcoded repo-root path) plus `model.pack.run`
to produce a real `data/model_metrics.json` at that size — fast (~15s total: a
few seconds of generation, ~10s to fit one small LightGBM), and deterministic
under the fixed seed.

Unlike `tests/conftest.py`'s own `packed` fixture, no monkey-patching of
`model.pack.F.load_tables` is needed: `realism.generate_book_and_journeys`
writes straight into `<root>/data/`, exactly where `model.ModelConfig.data`
looks, so `ModelConfig(root=root)` finds everything on its own. SM-4's roster
(`model.roster.load_roster`) still needs a real `data/roster.yaml`, which is
copied in from the repository's own (`data/roster.yaml` is committed, not
generated) rather than fabricated a second time.

This is a genuinely independent, real run of the pipeline this pack grades —
useful precisely because it is small: every by-cut cell lands under the
`min_n = 500` floor at this size (see the values this fixture's first user,
`test_status_mapping.py`, asserts), which is exactly the `skipped_low_n` path a
purely hand-built fixture would have to fake.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

#: Matches tests/conftest.py's SMALL_N — see the module docstring for why.
SMALL_N = 8_000
SMALL_MONTHS = 30
SMALL_SEED = 7

#: A model small enough to fit inside this suite in a few seconds: 150 trees,
#: one seed, `quick=True` (no OOT / permuted-label / ladder — 02_oot's own
#: test covers the resulting "pending" path explicitly, which is itself a
#: real, worth-testing behaviour, not a gap).
MODEL_KW = dict(
    seed=SMALL_SEED, seeds=(SMALL_SEED,), quick=True, queue_size=40, excluded_sample=6,
    lgbm=dict(n_estimators=150, learning_rate=0.06, num_leaves=31, min_child_samples=40,
             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_jobs=-1, verbose=-1),
)


@pytest.fixture(scope="session")
def small_metrics_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh small book + journey/label layer, scored once.

    Returns the tmp `repo_root` such that `<root>/data/model_metrics.json`
    exists — exactly what `validation/runners/_shared.py load_metrics_doc`
    looks for given `RunnerContext(repo_root=<root>, ...)`.
    """
    import realism
    from model import ModelConfig
    from model.pack import run as pack_run

    root = tmp_path_factory.mktemp("sanket_validation_small")
    data_dir = root / "data"
    realism.generate_book_and_journeys(
        n=SMALL_N, months=SMALL_MONTHS, seed=SMALL_SEED, out_dir=data_dir)

    real_roster = REPO_ROOT / "data" / "roster.yaml"
    if real_roster.is_file():
        shutil.copy(real_roster, data_dir / "roster.yaml")

    cfg = ModelConfig(root=root, **MODEL_KW)
    pack_run(cfg, out_json=None, metrics_json=data_dir / "model_metrics.json", verbose=False)
    return root


@pytest.fixture()
def make_ctx(tmp_path):
    """`RunnerContext` factory: `make_ctx(repo_root)` -> a context with fresh,
    per-test figures/out dirs (so tests never collide on figure filenames)."""
    from validation.criteria import load

    doc = load(REPO_ROOT / "validation" / "criteria.yaml")

    def _make(repo_root: Path):
        from validation.criteria import RunnerContext

        out_dir = tmp_path / "report"
        figures_dir = out_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        return RunnerContext(
            repo_root=Path(repo_root), out_dir=out_dir, figures_dir=figures_dir,
            doc=doc, seeds=tuple(doc.seeds.seed_list or ()),
        )

    return _make


@pytest.fixture()
def criteria_doc():
    from validation.criteria import load

    return load(REPO_ROOT / "validation" / "criteria.yaml")
