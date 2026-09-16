"""SANKET synthetic liability book — thin wrapper around ``book.build``.

The generator moved into the vectorised ``src/book/`` package at SD-S1.  This
file stays so the documented command line keeps working:

    python3 src/make_book.py                  # 60,000 customers x 30 months, 6 products
    python3 src/make_book.py --legacy-size     # the pre-SD-S1 book (15,000 x 27, 3 products)
    python3 src/make_book.py --help            # every flag

See ``src/book/build.py`` for the outputs and ``DATA_CARD.md`` for the
parameters, their provenance and the known unrealisms.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from book.build import main  # noqa: E402

if __name__ == "__main__":
    main()
