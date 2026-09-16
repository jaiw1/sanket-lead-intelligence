"""
Pre-registered validation package.

`criteria.yaml` is committed before the first model result exists; its git
timestamp is the evidence that the acceptance bands were not chosen to fit an
outcome. `python3 -m validation.run` executes the runners that exist, grades
their output against those bands, and exits non-zero on any failure.

    validation/
      criteria.yaml   the contract — bands, cuts, splits, seeds
      criteria.py     schema + loader (pydantic v2) and the runner contract
      run.py          discovery, execution, grading, exit code
      report.py       REPORT.md + report.json + figures/
      runners/        01_holdout … 12_baseline_ladder
      tests/          schema tests for criteria.yaml itself

See validation/README.md.
"""

__all__ = ["criteria", "report", "run", "runners"]
