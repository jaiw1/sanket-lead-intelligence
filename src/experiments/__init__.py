"""Long-running experiments that answer a review question but do not fit inside
``src/score_and_pack.py``'s eleven-minute budget.  Each writes a JSON file under
``data/experiments/`` that the pack reads if present and reports as missing if not.
"""
