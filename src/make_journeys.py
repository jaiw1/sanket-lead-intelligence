"""SANKET application-journey layer — thin wrapper around ``journeys.build``.

The liability book says *who* disburses and *when*.  This says *how* — one row
per application attempt, eight funnel stages, a Rs 1,000 processing fee, and the
drop-off population the mentors said was the only one that matters.

    python3 src/make_journeys.py                 # reads data/, writes data/
    python3 src/make_journeys.py --seed 8
    python3 src/make_journeys.py --help          # every flag

Run ``python3 src/make_book.py`` first: the journey layer reads the book, never
regenerates it, and never contradicts it.  See ``src/journeys/`` for the model
and ``DATA_CARD.md`` §11 for the parameters, their provenance and the known
unrealisms.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from journeys.build import main  # noqa: E402

if __name__ == "__main__":
    main()
