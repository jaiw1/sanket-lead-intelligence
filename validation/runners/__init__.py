"""
The twelve validation runners.

A runner module is named `NN_slug.py` (`01_holdout` … `12_baseline_ladder`) and
exposes one function:

    def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]: ...

It MEASURES; it does not grade. Set `value`, `ci`, `n` (and `breakdown` for a
per-cut / per-portfolio / per-product criterion, one dict per cell with keys
`level`, `value`, `ci`, `n`); leave `status` alone. `validation.run.grade()`
compares the measurement to the pre-registered band and assigns the status, so
no runner can mark its own criterion a pass.

Figures go in `ctx.figures_dir`; record the filenames in `Result.figures`.

Every runner here is currently a stub that raises NotImplementedError naming the
inputs it will consume. That is deliberate: the interface is documented and
pre-registered now, while the data lanes are still changing the shape of the
CSVs and JSONs underneath. A stub reports `pending`, never `pass`.
"""

from __future__ import annotations

import re
from pathlib import Path

_PATTERN = re.compile(r"^(0[1-9]|1[0-2])_[a-z0-9_]+$")


def discover() -> dict[str, Path]:
    """Map runner name -> module path, for every `NN_slug.py` present here."""
    here = Path(__file__).parent
    found: dict[str, Path] = {}
    for p in sorted(here.glob("*.py")):
        if p.stem.startswith("_"):
            continue
        if _PATTERN.match(p.stem):
            found[p.stem] = p
    return found
