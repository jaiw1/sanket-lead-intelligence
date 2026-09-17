# -*- coding: utf-8 -*-
"""SM-4 — the RM roster: who a lead's ``rm_id`` points to.

Source order, high to low, matching ``data/bank/SCHEMA.md``'s trust order
(``BANK_API > SIMULATED > FIXTURE``, with ``FIXTURE`` out of scope here — a
roster is a directory, not a customer column, so there is nothing for
``data/bank/fixture.json`` to stand in for):

1. **``data/bank/pulled.json``** — API 442's ``customerSummary.accountManager``,
   if the pull answered.  Tagged ``BANK_API``.  Checked unconditionally (not gated
   behind ``--bank``): who services a customer is directory data, not the
   customer-column enrichment SM-6 gates.
2. **``data/roster.yaml``** — a small seeded roster (fabricated names,
   branches and EINs, structurally plausible per ``data/bank/SCHEMA.md``'s
   ``ein`` id space).  Tagged ``SIMULATED``.

**API 508 (HRMS) is gone from that list, and the bank is why.** It was the
endpoint that would have given this roster real people — names, grades, branch,
reporting line — and the bank **rejected** it. ``rrsquad-platform``'s
``app/atlas/policy.py`` refuses it to both products, so no pull can ever put a 508
record in ``pulled.json`` and there is no 508 branch here to be unreachable.

**What 442 actually returns, and why the roster is still simulated.** A live pull
on 2026-09-17 walked all five documented CIFs. One answered — ``SANDBOX-CIF-2``
(SAMPLE CUSTOMER) — and its ``accountManager`` reads ``"SYSCODE"``: a bank system code,
with **no manager name and no branch beside it**. That is genuine bank data and it
is carried through to :func:`roster_block` as evidence, but it is not a person, and
putting ``RM: SYSCODE`` with a blank branch in front of a relationship manager would
be a worse claim than an honestly-labelled seeded roster, not a better one. So the
442 source is wired, ranked first, and reports what it found — and
:func:`usable_managers` admits an entry to the roster only once one carries a name.
Today none does, the roster is ``SIMULATED``, and :attr:`Roster.bank_reason` says
exactly that in one sentence a screen can render.

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

#: The only roster API left. `data/bank/SCHEMA.md` also names 508 (HRMS proper);
#: the bank rejected it, so it is not in this tuple and nothing calls it.
ROSTER_APIS: tuple[str, ...] = ("442",)

#: An ``accountManager`` value this short and this shaped is a bank system code, not a
#: person — ``SYSCODE`` is the migration user on the one CIF the sandbox answers for. Such a
#: value is still reported; it is just not promoted to an RM identity on its own.
def _looks_like_a_name(value: str) -> bool:
    """A manager name has a space or is long enough to be one. ``SYSCODE`` is neither."""
    text = str(value or "").strip()
    return bool(text) and (" " in text or len(text) >= 8)


@dataclass(frozen=True)
class RM:
    rm_id: str
    rm_name: str
    rm_branch: str
    active: bool = True
    #: Per RM, not per roster: a roster can hold a real account manager beside seeded ones,
    #: and a screen has to be able to badge them differently.
    source: str = "SIMULATED"


@dataclass(frozen=True)
class Roster:
    rms: tuple[RM, ...]
    source: str  # BANK_API | SIMULATED
    #: What API 442 actually returned, whether or not any of it became an RM. One dict per
    #: answered CIF: ``{cif_id, customer_id, customer_name, account_manager}``. This is the
    #: genuine bank field a disclosure screen shows beside the simulated roster.
    bank_managers: tuple[dict, ...] = ()
    #: Why :attr:`bank_managers` did or did not become the roster, in one sentence.
    bank_reason: str = ""

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


def account_managers(pulled: dict) -> list[dict]:
    """Every API 442 ``accountManager`` in ``pulled.json``, with the customer it belongs to.

    ``pulled.json``'s shape (``rrsquad-platform/batch/enrich.py::build_pulled``) is
    ``{"apis": {"<api_no>": {"provenance": "BANK_API"|"NOT_COLLECTED", "records": [...]}}}``.
    A 442 record is the live ``{customerSummary, exposureSummary, customerLimits}`` shape;
    the spreadsheet contract nested the same thing under ``customerLimitDetailsResponse``,
    so both spellings are read and neither is assumed.

    Returns what the bank said, unfiltered — including a manager that is a bare system code.
    Deciding what is usable is :func:`usable_managers`' job, and keeping the two apart is
    what lets a screen show "442 answered, and this is what it said" even when nothing in
    the answer is fit to name an RM.
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
            summary = rec.get("customerSummary")
            if not isinstance(summary, dict):
                nested = rec.get("customerLimitDetailsResponse")
                summary = nested if isinstance(nested, dict) else rec
            manager = str(summary.get("accountManager") or "").strip()
            if not manager:
                continue
            out.append(dict(
                api=str(api_no),
                cif_id=str(summary.get("custCifId") or summary.get("cifId") or ""),
                customer_id=str(summary.get("customerID") or summary.get("custId") or ""),
                customer_name=str(summary.get("customerName") or ""),
                account_manager=manager,
                manager_name=str(summary.get("accountManagerName") or ""),
                branch=str(summary.get("branchName") or summary.get("branch") or ""),
            ))
    return out


def usable_managers(managers: list[dict]) -> list[dict]:
    """The subset fit to name an RM: one that came with a manager *name*, not just a code.

    ``accountManager: "SYSCODE"`` is a real value from a real bank endpoint and it is still
    reported — it is simply not somebody a relationship manager can be told they are. An
    entry qualifies once ``accountManagerName`` arrives, or once ``accountManager`` itself
    reads like a name rather than a code.
    """
    return [m for m in managers
            if _looks_like_a_name(m.get("manager_name") or "")
            or _looks_like_a_name(m.get("account_manager") or "")]


def _from_pulled(bank_dir: Path) -> tuple[Roster | None, tuple[dict, ...], str]:
    """``(roster_or_None, what_442_said, why)``.

    A ``None`` roster with a non-empty second element is the interesting case and the one
    that holds today: the bank answered, and what it answered cannot name an RM.
    """
    path = Path(bank_dir) / PULLED_NAME
    if not path.exists():
        return None, (), "no data/bank/pulled.json: no Atlas pull has run on this checkout."
    try:
        pulled = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, (), f"{path.name} could not be read; fell back to the seeded roster."
    managers = account_managers(pulled)
    if not managers:
        return None, (), ("API 442 answered for no customer in this pull, so it named no "
                          "account manager; API 508 (HRMS) was rejected by the bank and is "
                          "never called.")
    usable = usable_managers(managers)
    if not usable:
        shown = ", ".join(sorted({m["account_manager"] for m in managers}))
        return None, tuple(managers), (
            f"API 442 answered for {len(managers)} customer(s) and gave "
            f"accountManager {shown} — a bank system code with no manager name and no "
            "branch beside it, which cannot name an RM. The roster stays SIMULATED; the "
            "code itself is reported above rather than dressed up as a person.")
    seen: dict[str, RM] = {}
    for m in usable:
        name = m.get("manager_name") or m["account_manager"]
        rm_id = _ein(m["account_manager"])
        seen.setdefault(rm_id, RM(rm_id=rm_id, rm_name=name,
                                  rm_branch=m.get("branch") or "Unknown",
                                  source=SOURCE_BANK_API))
    return (Roster(rms=tuple(seen.values()), source=SOURCE_BANK_API,
                   bank_managers=tuple(managers),
                   bank_reason=f"API 442 named {len(seen)} account manager(s); "
                               "they rank above data/roster.yaml and are tagged BANK_API."),
            tuple(managers), "")


def load_roster(data_dir: Path) -> Roster:
    """``data/bank/pulled.json`` if API 442 named at least one RM, else ``data/roster.yaml``.

    Either way the roster carries what 442 said and why it was or was not used, so the
    fallback is a stated finding rather than a silent default.
    """
    data_dir = Path(data_dir)
    roster, managers, reason = _from_pulled(data_dir / "bank")
    if roster is not None:
        return roster
    seeded = _from_seeds(data_dir)
    return Roster(rms=seeded.rms, source=seeded.source,
                  bank_managers=managers, bank_reason=reason)


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
        rms=[dict(rm_id=r.rm_id, rm_name=r.rm_name, rm_branch=r.rm_branch, active=r.active,
                  source=r.source)
             for r in roster.rms],
        # The genuine bank field, shown whether or not it became an RM. A screen that can
        # only render the roster would never be able to say "we asked, and here is what
        # came back"; this is what lets it.
        bank_account_managers=[dict(m) for m in roster.bank_managers],
        bank_source_note=roster.bank_reason,
    )


__all__ = ["RM", "Roster", "load_roster", "assign", "roster_block", "account_managers",
           "usable_managers", "ROSTER_APIS", "SOURCE_BANK_API", "SOURCE_SIMULATED"]
