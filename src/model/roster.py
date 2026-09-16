# -*- coding: utf-8 -*-
"""SM-4 — the RM roster: who a lead's ``rm_id`` points to.

Source order, high to low, matching ``data/bank/SCHEMA.md``'s trust order
(``BANK_API > SIMULATED > FIXTURE``, with ``FIXTURE`` out of scope here — a
roster is a directory, not a customer column, so there is nothing for
``data/bank/fixture.json`` to stand in for):

1. **``data/bank/pulled.json``** — API 442 ``accountManager`` / API 508 HRMS
   records, if the pull answered either.  Tagged ``BANK_API``.  Checked
   unconditionally (not gated behind ``--bank``): who services a customer is
   HRMS directory data, not the customer-column enrichment SM-6 gates.
2. **``data/roster.yaml``** — a small seeded roster (fabricated names,
   branches and EINs, structurally plausible per ``data/bank/SCHEMA.md``'s
   ``ein`` id space).  Tagged ``SIMULATED``.  This is what every run without a
   live Atlas pull uses — i.e. every run today.

Assignment is a deterministic **round-robin** over the *active* roster: leads
are sorted by ``cust_id`` — never by score, month or queue position — and
handed the roster in order, wrapping around.  Two runs over the same
population, on the same roster, produce the same ``rm_id`` for the same
customer, independent of the model seed: who services a customer is an
operational fact, not something that should reshuffle when a data scientist
reruns the model.

``data/journeys.csv`` carries an ``rm_id`` column of its own (an RM who
contacted a customer *during* their application); it is entirely null in this
generator's output (SD-S2 never populates it), so there is no pre-existing
assignment to preserve — every drop-off is "unassigned" in that sense, and the
round-robin covers the whole population uniformly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

ROSTER_YAML_NAME = "roster.yaml"
PULLED_NAME = "pulled.json"

SOURCE_BANK_API = "BANK_API"
SOURCE_SIMULATED = "SIMULATED"

#: API numbers `data/bank/SCHEMA.md` names for the roster: 508 is HRMS proper,
#: 442 carries `accountManager` on the CIF-exposure response as a cross-check.
ROSTER_APIS: tuple[str, ...] = ("508", "442")


@dataclass(frozen=True)
class RM:
    rm_id: str
    rm_name: str
    rm_branch: str
    active: bool = True


@dataclass(frozen=True)
class Roster:
    rms: tuple[RM, ...]
    source: str  # BANK_API | SIMULATED

    @property
    def active_rms(self) -> tuple[RM, ...]:
        return tuple(r for r in self.rms if r.active)


def _ein(raw: str) -> str:
    """Coerce whatever the API sent (``"SANDBOX-EIN-1"``, ``"EIN-SANDBOX-EIN-1"``) to ``EIN-######``."""
    s = str(raw).strip()
    if s.upper().startswith("EIN-"):
        digits = s.split("-", 1)[1]
    else:
        digits = s
    digits = "".join(ch for ch in digits if ch.isdigit())
    return f"EIN-{int(digits):06d}" if digits else f"EIN-{abs(hash(s)) % 1_000_000:06d}"


def _from_seeds(data_dir: Path) -> Roster:
    path = Path(data_dir) / ROSTER_YAML_NAME
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = doc.get("rms") or []
    rms = tuple(RM(rm_id=str(r["rm_id"]), rm_name=str(r["rm_name"]),
                   rm_branch=str(r["rm_branch"]), active=bool(r.get("active", True)))
                for r in rows)
    if not rms:
        raise ValueError(f"{path} carries no RMs")
    return Roster(rms=rms, source=SOURCE_SIMULATED)


def _hrms_records(pulled: dict) -> list[dict]:
    """API 508 HRMS rows, else API 442's ``accountManager`` field, from ``pulled.json``.

    ``pulled.json``'s shape (``rrsquad-platform/batch/enrich.py::build_pulled``)
    is ``{"apis": {"<api_no>": {"provenance": "BANK_API"|"NOT_COLLECTED",
    "records": [...]}}}``.  A record's field names follow whichever Atlas
    response shape that API returns — ``hrmsInfo`` on 442's blob, or a flat
    HRMS row on 508 — so several aliases are tried per field.
    """
    apis = pulled.get("apis", {}) if isinstance(pulled, dict) else {}
    out: list[dict] = []
    for api_no in ROSTER_APIS:
        entry = apis.get(api_no)
        if not isinstance(entry, dict) or entry.get("provenance") != "BANK_API":
            continue
        for rec in entry.get("records", []):
            if not isinstance(rec, dict):
                continue
            hrms = rec.get("hrmsInfo") if isinstance(rec.get("hrmsInfo"), dict) else {}
            ein = (rec.get("ein") or rec.get("rm_ein") or rec.get("accountManagerEin")
                   or rec.get("accountManager") or hrms.get("supEin") or rec.get("empId"))
            name = (rec.get("rm_name") or rec.get("empName") or hrms.get("fullNameTitle")
                    or rec.get("name"))
            branch = (rec.get("branch_name") or rec.get("branchName") or hrms.get("location")
                      or rec.get("branchId"))
            if not ein:
                continue
            out.append(dict(ein=str(ein), name=str(name or ein), branch=str(branch or "Unknown")))
    return out


def _from_pulled(bank_dir: Path) -> Roster | None:
    path = Path(bank_dir) / PULLED_NAME
    if not path.exists():
        return None
    try:
        pulled = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    recs = _hrms_records(pulled)
    if not recs:
        return None
    seen: dict[str, RM] = {}
    for r in recs:
        ein = _ein(r["ein"])
        seen.setdefault(ein, RM(rm_id=ein, rm_name=r["name"], rm_branch=r["branch"]))
    if not seen:
        return None
    return Roster(rms=tuple(seen.values()), source=SOURCE_BANK_API)


def load_roster(data_dir: Path) -> Roster:
    """``data/bank/pulled.json`` if it names at least one RM, else ``data/roster.yaml``."""
    data_dir = Path(data_dir)
    r = _from_pulled(data_dir / "bank")
    if r is not None:
        return r
    return _from_seeds(data_dir)


def assign(cust_ids: Iterable[str], roster: Roster) -> dict[str, RM]:
    """Deterministic round-robin: ``cust_id``\\ s sorted, then the active roster in order.

    Sorting by ``cust_id`` — never by score, blend rank or dict/set iteration
    order — is what makes this stable across reruns and across model seeds: the
    population of candidate customers does not depend on which seed scored them,
    and neither does their RM.
    """
    active = roster.active_rms
    if not active:
        raise ValueError("roster has no active RMs")
    ordered = sorted({str(c) for c in cust_ids})
    return {c: active[i % len(active)] for i, c in enumerate(ordered)}


def roster_block(roster: Roster) -> dict:
    """The ``roster`` block packed into the export, with provenance."""
    return dict(
        source=roster.source,
        n_rms=len(roster.rms),
        n_active=len(roster.active_rms),
        rms=[dict(rm_id=r.rm_id, rm_name=r.rm_name, rm_branch=r.rm_branch, active=r.active)
             for r in roster.rms],
    )


__all__ = ["RM", "Roster", "load_roster", "assign", "roster_block",
           "SOURCE_BANK_API", "SOURCE_SIMULATED"]
