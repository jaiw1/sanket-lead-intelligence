"""
Harness: run the pre-registered criteria and grade the results.

    python3 -m validation.run --criteria validation/criteria.yaml --out validation/report/

What it does, in order:

  1. Loads and schema-validates `criteria.yaml` (validation/criteria.py).
  2. Discovers the runner modules `01_holdout … 12_baseline_ladder` that are
     actually present in validation/runners/ and runs the ones the criteria
     file references.
  3. Collects `{criterion_id, value, ci, n, status}` per criterion.
  4. Grades each result against its band — the runner measures, the harness
     grades. A runner cannot mark its own criterion `pass`.
  5. Writes REPORT.md, report.json and figures/ (validation/report.py).
  6. Exits non-zero if any criterion with severity `fail` failed.

Statuses:
  pass          the band was met
  fail          the band was not met, and severity is `fail`
  warn          the band was not met, and severity is `warn`
  report        no comparison is made; the value is recorded for a human
  pending       the runner is not implemented yet — NOT a pass
  skipped_low_n the cell had fewer rows than the criterion's pre-registered min_n
  error         the runner raised

`--strict` (the G7 form) treats pending and warn as failures too, so the gate
cannot be passed by a validation pack that has not been written yet.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from pathlib import Path

from validation.criteria import (
    RUNNERS,
    CriteriaDoc,
    CriteriaError,
    Criterion,
    Result,
    RunnerContext,
    load,
)
from validation.runners import discover
from validation import report as report_mod

_FAILING = {"fail", "error"}
_STRICT_ALSO_FAILING = {"warn", "pending"}


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def _grade_cell(crit: Criterion, value, n: int | None) -> str:
    """Grade one observation against the band. min_n gates before the band does."""
    if n is not None and crit.min_n and n < crit.min_n:
        return "skipped_low_n"
    ok = crit.check(value)
    if ok is None:
        return "report"
    if ok:
        return "pass" if crit.severity != "report" else "report"
    return crit.severity if crit.severity != "report" else "report"


_RANK = {
    "pass": 0, "report": 1, "skipped_low_n": 2,
    "warn": 3, "pending": 4, "fail": 5, "error": 6,
}


def grade(crit: Criterion, res: Result) -> Result:
    """Assign `res.status` from the criterion's band. Idempotent.

    Only `pending` and `error` — which the harness itself sets — survive
    ungraded. A runner leaves `status` at None and is graded here.
    """
    if res.status in ("pending", "error"):
        return res

    if res.breakdown:
        # A per-cut / per-portfolio / per-product criterion: every cell is
        # graded, and the criterion takes the worst cell's status.
        worst = "pass"
        binding = None
        for cell in res.breakdown:
            cell_status = _grade_cell(crit, cell.get("value"), cell.get("n"))
            cell["status"] = cell_status
            if _RANK[cell_status] > _RANK[worst]:
                worst, binding = cell_status, cell
        res.status = worst
        if binding is not None and res.value is None:
            res.value = binding.get("value")
            res.n = binding.get("n")
            res.ci = binding.get("ci")
            res.detail = res.detail or f"binding cell: {binding.get('level')}"
        return res

    res.status = _grade_cell(crit, res.value, res.n)
    return res


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def run_runner(name: str, crits: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Run one runner module, translating its absence or its NotImplementedError
    into `pending` results rather than into a crash."""
    present = discover()
    if name not in present:
        return [
            Result(c.id, status="pending", detail=f"runner {name} module not present")
            for c in crits
        ]
    try:
        mod = importlib.import_module(f"validation.runners.{name}")
    except Exception as exc:
        return [
            Result(c.id, status="error", detail=f"import of {name} failed: {exc}")
            for c in crits
        ]

    fn = getattr(mod, "run", None)
    if fn is None:
        return [
            Result(c.id, status="error", detail=f"runner {name} defines no run()")
            for c in crits
        ]

    try:
        produced = list(fn(crits, ctx))
    except NotImplementedError as exc:
        return [Result(c.id, status="pending", detail=str(exc)) for c in crits]
    except Exception:
        tb = traceback.format_exc(limit=3).strip().splitlines()[-1]
        return [Result(c.id, status="error", detail=f"{name} raised: {tb}") for c in crits]

    # Any criterion the runner stayed silent about is pending, not passed.
    seen = {r.criterion_id for r in produced}
    for c in crits:
        if c.id not in seen:
            produced.append(
                Result(c.id, status="pending", detail=f"runner {name} returned no result for {c.id}")
            )
    return produced


def execute(doc: CriteriaDoc, repo_root: Path, out_dir: Path, only: list[str] | None = None) -> list[Result]:
    figures = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    ctx = RunnerContext(
        repo_root=repo_root,
        out_dir=out_dir,
        figures_dir=figures,
        doc=doc,
        seeds=tuple(doc.seeds.seed_list or ()),
    )

    results: list[Result] = []
    for name in doc.runners_used():
        if only and name not in only:
            continue
        crits = doc.by_runner(name)
        for res in run_runner(name, crits, ctx):
            try:
                results.append(grade(doc.get(res.criterion_id), res))
            except KeyError:
                results.append(
                    Result(res.criterion_id, status="error",
                           detail="runner returned a result for an unregistered criterion")
                )
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python3 -m validation.run",
        description="Run the pre-registered validation criteria and grade the results.",
    )
    ap.add_argument("--criteria", default="validation/criteria.yaml",
                    help="path to criteria.yaml (default: validation/criteria.yaml)")
    ap.add_argument("--out", default="validation/report/",
                    help="output directory for REPORT.md, report.json and figures/")
    ap.add_argument("--runner", action="append", metavar="NAME",
                    help=f"run only this runner (repeatable). One of: {', '.join(RUNNERS)}")
    ap.add_argument("--strict", action="store_true",
                    help="also fail on `warn` and `pending` (the G7 gate form)")
    ap.add_argument("--list", action="store_true",
                    help="list the registered criteria and exit without running anything")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        doc = load(args.criteria)
    except CriteriaError as exc:
        print(f"criteria.yaml did not load:\n{exc}", file=sys.stderr)
        return 2

    if args.list:
        print(f"{doc.product} — {len(doc.criteria)} pre-registered criteria "
              f"(registered {doc.registered_at.isoformat()})")
        for c in doc.criteria:
            print(f"  {c.id}  {c.runner:<18} {c.metric:<46} {c.band_text():<24} [{c.severity}]")
        return 0

    if args.runner:
        unknown = [r for r in args.runner if r not in RUNNERS]
        if unknown:
            print(f"unknown runner(s): {', '.join(unknown)}", file=sys.stderr)
            return 2

    repo_root = Path(args.criteria).resolve().parent.parent
    out_dir = Path(args.out).resolve()

    results = execute(doc, repo_root, out_dir, only=args.runner)

    report_mod.write(doc, results, out_dir, strict=args.strict)
    report_mod.print_summary(doc, results, out_dir, strict=args.strict)

    bad = _FAILING | (_STRICT_ALSO_FAILING if args.strict else set())
    return 1 if any(r.status in bad for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
