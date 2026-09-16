"""
Rendering: REPORT.md, report.json and the figures/ directory.

REPORT.md is written for a bank model-risk reviewer who has not read the code.
It leads with the pre-registration statement and the failures, because those are
the two things such a reviewer looks for first, and it prints every band beside
its observed value so a claim can be traced without opening report.json.

report.json is the machine-readable twin — the deploy pipeline's verify step and
the §D G5 honesty gate both read it.
"""

from __future__ import annotations

import datetime as _dt
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from validation.criteria import RUNNERS, CriteriaDoc, Result

_BADGE = {
    "pass": "PASS",
    "fail": "**FAIL**",
    "warn": "WARN",
    "report": "reported",
    "pending": "pending",
    "skipped_low_n": "skipped (low n)",
    "error": "**ERROR**",
}

_ORDER = ["fail", "error", "warn", "pending", "skipped_low_n", "report", "pass"]


# ---------------------------------------------------------------------------
def _git(repo_root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _provenance(doc: CriteriaDoc, out_dir: Path) -> dict[str, Any]:
    repo_root = out_dir.parent.parent
    criteria_path = repo_root / "validation" / "criteria.yaml"
    return {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "git_commit": _git(repo_root, "rev-parse", "HEAD"),
        "git_dirty": bool(_git(repo_root, "status", "--porcelain")),
        "criteria_registered_at": doc.registered_at.isoformat(),
        "criteria_first_committed_at": _git(
            repo_root, "log", "--diff-filter=A", "--format=%cI", "-1", "--", str(criteria_path)
        ),
    }


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _fmt_ci(ci: Any) -> str:
    if not ci:
        return "—"
    return f"[{_fmt(ci[0])}, {_fmt(ci[1])}]"


def counts(results: list[Result]) -> dict[str, int]:
    c = {k: 0 for k in _ORDER}
    for r in results:
        key = r.status or "pending"
        c[key] = c.get(key, 0) + 1
    return c


def verdict(results: list[Result], strict: bool) -> str:
    bad = {"fail", "error"} | ({"warn", "pending"} if strict else set())
    if any(r.status in bad for r in results):
        return "FAIL"
    if any(r.status == "pending" for r in results):
        return "PASS (with pending runners — not yet the G7 gate)"
    return "PASS"


# ---------------------------------------------------------------------------
def render_markdown(doc: CriteriaDoc, results: list[Result], out_dir: Path, strict: bool) -> str:
    by_id = {r.criterion_id: r for r in results}
    prov = _provenance(doc, out_dir)
    c = counts(results)
    L: list[str] = []

    L.append(f"# {doc.product} — validation report")
    L.append("")
    L.append(f"**Verdict: {verdict(results, strict)}**  ·  "
             f"{c['pass']} pass · {c['fail']} fail · {c['warn']} warn · "
             f"{c['pending']} pending · {c['skipped_low_n']} skipped · {c['report']} reported"
             + (f" · {c['error']} error" if c["error"] else ""))
    L.append("")
    L.append("## Pre-registration")
    L.append("")
    L.append(f"These {len(doc.criteria)} acceptance bands were registered at "
             f"**{doc.registered_at.isoformat()}** by {doc.registered_by}, before any model "
             f"result for {doc.product} existed.")
    if prov["criteria_first_committed_at"]:
        L.append("")
        L.append(f"`validation/criteria.yaml` first entered git at "
                 f"**{prov['criteria_first_committed_at']}** — that commit timestamp, not this "
                 f"file, is the evidence. This report was generated at {prov['generated_at']}"
                 + (f" from commit `{prov['git_commit'][:12]}`." if prov["git_commit"] else "."))
    if doc.rulings:
        L.append("")
        L.append("Clarifications issued during pre-registration (no band was loosened):")
        for r in doc.rulings:
            L.append(f"- *{r.at.isoformat()}* — {r.ruling.strip()}")
    if doc.amendments:
        L.append("")
        L.append("**Amendments after registration:**")
        for a in doc.amendments:
            flag = " ⚠️ LOOSENING" if a.loosening else ""
            L.append(f"- *{a.at.isoformat()}* ({a.by}){flag} — {a.change.strip()} "
                     f"Rationale: {a.rationale.strip()}")
    else:
        L.append("")
        L.append("No amendments. Every band below is as first registered.")

    # -- failures first ----------------------------------------------------
    failures = [r for r in results if r.status in ("fail", "error")]
    if failures:
        L.append("")
        L.append("## Failures")
        L.append("")
        L.append("| Criterion | Metric | Band | Observed | 95% CI | n | Detail |")
        L.append("|---|---|---|---|---|---|---|")
        for r in failures:
            cr = doc.get(r.criterion_id)
            L.append(f"| **{cr.id}** | {cr.metric} | {cr.band_text()} | {_fmt(r.value)} | "
                     f"{_fmt_ci(r.ci)} | {_fmt(r.n)} | {r.detail or ''} |")

    pending = [r for r in results if r.status == "pending"]
    if pending:
        L.append("")
        L.append("## Pending")
        L.append("")
        L.append("These criteria have no result yet. **Pending is not a pass.** "
                 "`--strict` (the G7 gate form) treats them as failures.")
        L.append("")
        for r in pending:
            cr = doc.get(r.criterion_id)
            L.append(f"- `{cr.id}` {cr.metric} — {r.detail or 'no runner'}")

    # -- everything, by runner --------------------------------------------
    L.append("")
    L.append("## All criteria")
    for runner in RUNNERS:
        crits = doc.by_runner(runner)
        if not crits:
            continue
        L.append("")
        L.append(f"### {runner}")
        L.append("")
        L.append("| ID | Metric | Scope | Band | Observed | 95% CI | n | Severity | Status |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for cr in crits:
            r = by_id.get(cr.id) or Result(cr.id, status="pending")
            scope = cr.scope + (f" ({cr.cut})" if cr.cut else "")
            L.append(
                f"| {cr.id} | {cr.metric} | {scope} | {cr.band_text()} | {_fmt(r.value)} | "
                f"{_fmt_ci(r.ci)} | {_fmt(r.n)} | {cr.severity} | {_BADGE.get(r.status or 'pending', '?')} |"
            )
        for cr in crits:
            r = by_id.get(cr.id)
            if r and r.breakdown:
                L.append("")
                L.append(f"<details><summary>{cr.id} — per-cell breakdown "
                         f"({len(r.breakdown)} cells)</summary>")
                L.append("")
                L.append("| Cell | Observed | 95% CI | n | Status |")
                L.append("|---|---|---|---|---|")
                for cell in r.breakdown:
                    L.append(f"| {cell.get('level')} | {_fmt(cell.get('value'))} | "
                             f"{_fmt_ci(cell.get('ci'))} | {_fmt(cell.get('n'))} | "
                             f"{_BADGE.get(cell.get('status', 'report'), '')} |")
                L.append("")
                L.append("</details>")

    # -- the bands in prose ------------------------------------------------
    L.append("")
    L.append("## Why each band is what it is")
    L.append("")
    L.append("Registered rationale, verbatim from `criteria.yaml`. Notes record where a "
             "band's wording admitted more than one reading and which reading we took.")
    for cr in doc.criteria:
        L.append("")
        L.append(f"**{cr.id} — {cr.metric}** ({cr.band_text()}, severity `{cr.severity}`)  ")
        L.append(f"{cr.rationale.strip()}  ")
        L.append(f"*Source:* {cr.source.strip()}")
        if cr.note:
            L.append(f"  \n*Note:* {cr.note.strip()}")

    figs = sorted(p.name for p in (out_dir / "figures").glob("*") if p.is_file())
    L.append("")
    L.append("## Figures")
    L.append("")
    L.append("\n".join(f"- `figures/{f}`" for f in figs) if figs else "None produced yet.")
    L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
def write(doc: CriteriaDoc, results: list[Result], out_dir: Path, strict: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)

    payload = {
        "product": doc.product,
        "schema_version": doc.schema_version,
        "registered_at": doc.registered_at.isoformat(),
        "registered_by": doc.registered_by,
        "provenance": _provenance(doc, out_dir),
        "verdict": verdict(results, strict),
        "strict": strict,
        "counts": counts(results),
        "criteria": [
            {
                **doc.get(r.criterion_id).model_dump(mode="json"),
                "result": r.to_dict(),
            }
            for r in results
        ],
        "amendments": [a.model_dump(mode="json") for a in doc.amendments],
        "rulings": [r.model_dump(mode="json") for r in doc.rulings],
    }
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (out_dir / "REPORT.md").write_text(
        render_markdown(doc, results, out_dir, strict), encoding="utf-8"
    )


def print_summary(doc: CriteriaDoc, results: list[Result], out_dir: Path, strict: bool = False) -> None:
    c = counts(results)
    print(f"{doc.product}: {verdict(results, strict)}  "
          f"({c['pass']} pass, {c['fail']} fail, {c['warn']} warn, {c['pending']} pending, "
          f"{c['skipped_low_n']} skipped, {c['report']} reported"
          + (f", {c['error']} error" if c["error"] else "") + ")")
    for r in results:
        if r.status in ("fail", "error"):
            cr = doc.get(r.criterion_id)
            print(f"  {r.status.upper():<6} {cr.id}  {cr.metric} {cr.band_text()}  "
                  f"observed {_fmt(r.value)}  {r.detail or ''}")
    print(f"  -> {out_dir / 'REPORT.md'}")
    print(f"  -> {out_dir / 'report.json'}")
