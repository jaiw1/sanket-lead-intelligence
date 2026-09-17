# -*- coding: utf-8 -*-
"""SM-6 — the ``--bank`` enrichment path.

``data/bank/SCHEMA.md`` states the fallback rule this module implements exactly:

    credentials present AND endpoint approved  ->  live pull      -> BANK_API
    credentials present BUT endpoint pending   ->  fixture column -> FIXTURE
    no credentials / no endpoints at all       ->  whole fixture  -> FIXTURE
    no bank API supplies this field at all     ->  generator      -> SIMULATED
    the `model` family                         ->  the weakest of the other seven

Without ``--bank`` the pipeline is untouched: every family stays ``SIMULATED``,
exactly as SM-1 through SM-3 left it (``data/bank/SCHEMA.md``: "without it the
pipeline runs purely synthetic, exactly as it did in July 2026").

With ``--bank``, this module reads two files the platform's batch writes into
this repo (``rrsquad-platform/batch/enrich.py``) and one committed offline
stand-in:

* ``data/bank/pulled.json``     — what each Atlas API answered, per API.
* ``data/bank/provenance.json`` — the platform's own family/endpoint summary
  (its ``columns`` block is deliberately empty: "the enriching pipeline['s] to
  write" — that enriching pipeline is this module).
* ``data/bank/fixture.json``    — 120 committed customers, the offline stand-in
  used whenever a live pull is unavailable or incomplete.

None of the three is required to exist. All three are gitignored except the
fixture (``data/bank/SCHEMA.md`` rule 1); this module degrades to whichever
subset is present rather than failing.

**Coverage is honestly partial, on purpose.** ``fixture.json`` covers 120 of
the book's 60,000 customers (``cust_id`` overlaps by construction — see
``tests/test_model_bank.py``); the other ~59,880 get no fixture row.  Per-
customer provenance (:meth:`BankContext.provenance_for`) reflects that: a
customer outside the fixture reads ``SIMULATED`` for a family the *aggregate*
run reports as ``FIXTURE``, because nothing was actually substituted for them.
This mirrors the real AA-consent situation ``data/bank/SCHEMA.md`` documents as
normal: "a book with approved 595/739 endpoints and no consents still yields
`cross_bank: FIXTURE`... consent is per customer and the customer may say no."

**An endpoint answering is not the same as it answering about you.** The two are
easy to conflate and the conflation is the dishonest one: the sandbox holds a
*handful* of sample customers, so a family whose API answered is ``BANK_API`` at
**run** level — the call was made, the shape came back — while almost every
customer in the book had nothing fetched for them at all. :attr:`bank_keys`
records the customer and account ids the pull actually came back with, and
:meth:`provenance_for` hands a customer ``BANK_API`` only if they are one of
them; everyone else degrades to ``FIXTURE`` or ``SIMULATED`` exactly as they did
before any pull existed. Today the sandbox's sample ids and this book's
generated ids are disjoint, so *no* customer row claims ``BANK_API`` — the real
bank data in this export is the run-level block, the fetched amortisation
schedules and what API 442 returned, all of which are carried separately and
badged where they are.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PULLED_NAME = "pulled.json"
PROVENANCE_NAME = "provenance.json"
FIXTURE_NAME = "fixture.json"

#: The eight-family vocabulary ``data/bank/SCHEMA.md`` and the platform contract
#: both use.
FAMILIES: tuple[str, ...] = ("identity", "casa_behaviour", "cross_bank", "holdings",
                             "digital", "consent", "journey", "model")

#: Families no Atlas API supplies at all (`data/bank/SCHEMA.md`, "Fields no API
#: supplies — always SIMULATED"). Always this value, `--bank` or not.
ALWAYS_SIMULATED: tuple[str, ...] = ("digital", "consent", "journey")

#: `data/bank/SCHEMA.md`'s API -> family map, for the families a bank pull can
#: actually fill (the four left once :data:`ALWAYS_SIMULATED` is set aside).
FAMILY_APIS: dict[str, tuple[str, ...]] = {
    "identity": ("442", "394", "456", "508"),
    "casa_behaviour": ("365", "393"),
    "holdings": ("394",),
    "cross_bank": ("595", "739"),
}

#: Trust order, worst first — `weakest` walks it in this direction so ties fall
#: to the least-trusted source, matching `data/bank/SCHEMA.md`'s stated rule
#: (`BANK_API > SIMULATED > FIXTURE`) and the platform's own
#: `app/fixtures/common.py::weakest`.
_WORST_FIRST: tuple[str, ...] = ("FIXTURE", "SIMULATED", "BANK_API")


def weakest(sources: list[str]) -> str:
    """The ``model`` family's rule: the WEAKEST of the sources that fed it."""
    present = set(sources)
    for s in _WORST_FIRST:
        if s in present:
            return s
    return "SIMULATED"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _answered_apis(pulled: dict) -> set[str]:
    apis = pulled.get("apis", {})
    if not isinstance(apis, dict):
        return set()
    return {str(k) for k, v in apis.items() if isinstance(v, dict) and v.get("provenance") == "BANK_API"}


#: Fields the bank echoes back naming *who* a record is about. A pull is keyed by these,
#: so they are what a book customer has to match to have genuinely been fetched.
_ID_FIELDS: tuple[str, ...] = ("custCifId", "cifId", "cif_id", "customerID", "custId",
                               "customerId", "acctId", "accountNumber", "accountNo",
                               "accountId")


def _ids_in(node: Any, out: set[str], depth: int = 0) -> None:
    """Every identifier value anywhere in one answered record, recursively."""
    if depth > 8:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _ID_FIELDS and isinstance(v, (str, int)) and str(v).strip():
                out.add(str(v).strip())
            else:
                _ids_in(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node[:200]:
            _ids_in(v, out, depth + 1)


def _answered_keys(pulled: dict) -> frozenset[str]:
    """The customer and account ids the sandbox actually returned records for.

    This is the difference between "API 442 answered" and "API 442 answered about this
    customer". Only the second earns a customer row a ``BANK_API`` badge.
    """
    apis = pulled.get("apis", {})
    if not isinstance(apis, dict):
        return frozenset()
    found: set[str] = set()
    for entry in apis.values():
        if not isinstance(entry, dict) or entry.get("provenance") != "BANK_API":
            continue
        for rec in entry.get("records") or []:
            _ids_in(rec, found)
    return frozenset(found)


def _fixture_by_cust(fixture: dict | None) -> dict[str, dict]:
    if not fixture:
        return {}
    rows = fixture.get("customers", [])
    if not isinstance(rows, list):
        return {}
    return {str(r["cust_id"]): r for r in rows if isinstance(r, dict) and "cust_id" in r}


@dataclass(frozen=True)
class BankContext:
    enabled: bool
    mode: str  # "simulated" | "fixture" | "mixed" | "live"
    families: dict[str, str]
    fixture_by_cust: dict[str, dict] = field(default_factory=dict)
    pulled: dict[str, Any] | None = None
    provenance_raw: dict[str, Any] | None = None
    fixture_meta: dict[str, Any] | None = None
    reason: str = ""
    #: The customer and account ids the pull actually came back with. A family can be
    #: ``BANK_API`` at run level while this is disjoint from the whole book — which is
    #: exactly the sandbox's situation — so it is held separately from :attr:`families`.
    bank_keys: frozenset[str] = frozenset()

    def overlay_for(self, cust_id: str) -> dict:
        """The fixture row for ``cust_id``, or ``{}`` if it is not covered."""
        return self.fixture_by_cust.get(str(cust_id), {})

    def fetched_for(self, cust_id: str, cif_id: str | None = None) -> bool:
        """Did the pull actually come back with a record about *this* customer?"""
        if not self.bank_keys:
            return False
        return (str(cust_id) in self.bank_keys
                or (cif_id is not None and str(cif_id) in self.bank_keys))

    def provenance_for(self, cust_id: str, cif_id: str | None = None) -> dict[str, str]:
        """Per-customer family provenance — honest about who was actually fetched.

        The aggregate :attr:`families` says what the *run* achieved: the endpoint was
        called and answered. A single customer only got substituted data if the pull came
        back about *them* (:meth:`fetched_for`), or if they are one of the fixture's 120.
        So a family the run reports as ``BANK_API`` reads, for a customer the bank never
        answered about, ``FIXTURE`` when the fixture covers them and ``SIMULATED`` when
        nothing does — because that is what is behind their columns. Anything else would
        put a bank badge on a generated number, which is the one thing this block exists
        to prevent.
        """
        if not self.enabled:
            return {f: "SIMULATED" for f in FAMILIES}
        covered = str(cust_id) in self.fixture_by_cust
        fetched = self.fetched_for(cust_id, cif_id)
        out: dict[str, str] = {}
        for fam in FAMILY_APIS:
            agg = self.families.get(fam, "SIMULATED")
            if agg == "BANK_API" and not fetched:
                agg = "FIXTURE" if covered else "SIMULATED"
            out[fam] = agg if (agg == "BANK_API" or covered) else "SIMULATED"
        for fam in ALWAYS_SIMULATED:
            out[fam] = "SIMULATED"
        out["model"] = weakest([v for k, v in out.items() if k != "model"])
        return out

    def coverage(self) -> dict[str, int]:
        return dict(fixture_customers=len(self.fixture_by_cust))


def build_context(data_dir: Path, enabled: bool) -> BankContext:
    """The one entry point. ``enabled=False`` is the pre-SM-6 pipeline, untouched."""
    data_dir = Path(data_dir)
    bank_dir = data_dir / "bank"

    if not enabled:
        return BankContext(enabled=False, mode="simulated",
                           families={f: "SIMULATED" for f in FAMILIES},
                           reason="--bank not passed: the pipeline runs purely synthetic, "
                                  "exactly as it did before SM-6.")

    pulled = _load_json(bank_dir / PULLED_NAME)
    provenance_raw = _load_json(bank_dir / PROVENANCE_NAME)
    fixture = _load_json(bank_dir / FIXTURE_NAME)
    fixture_by_cust = _fixture_by_cust(fixture)

    families: dict[str, str] = {}
    if pulled is not None:
        answered = _answered_apis(pulled)
        for fam, apis in FAMILY_APIS.items():
            if any(a in answered for a in apis):
                families[fam] = "BANK_API"
            elif fixture_by_cust:
                families[fam] = "FIXTURE"
            else:
                families[fam] = "SIMULATED"
        fell_back = sorted(f for f, s in families.items() if s == "FIXTURE")
        n_keys = len(_answered_keys(pulled))
        reason = (f"data/bank/pulled.json present; APIs answered: {sorted(answered) or 'none'}."
                  + (f" Families {', '.join(fell_back)} fell back to data/bank/fixture.json."
                     if fell_back else "")
                  + f" Those answers name {n_keys} bank identifier(s) between them; a customer"
                    " row is badged BANK_API only if it is one of them, so a family that is"
                    " BANK_API for the run can still be SIMULATED for almost every customer.")
    elif fixture_by_cust:
        for fam in FAMILY_APIS:
            families[fam] = "FIXTURE"
        reason = ("no data/bank/pulled.json: whole-fixture fallback from "
                  f"data/bank/fixture.json ({len(fixture_by_cust)} of the book's customers "
                  "covered by cust_id match; every other customer stays SIMULATED for these "
                  "families — see BankContext.provenance_for).")
    else:
        for fam in FAMILY_APIS:
            families[fam] = "SIMULATED"
        reason = "no data/bank/pulled.json and no usable data/bank/fixture.json: fell all " \
                 "the way back to SIMULATED, same as --bank not being passed at all."

    for fam in ALWAYS_SIMULATED:
        families[fam] = "SIMULATED"
    families["model"] = weakest([v for k, v in families.items() if k != "model"])

    if pulled is not None:
        non_model = {v for k, v in families.items() if k != "model"}
        mode = "live" if non_model == {"BANK_API"} else ("mixed" if "BANK_API" in non_model else "fixture")
    else:
        mode = "fixture" if fixture_by_cust else "simulated"

    return BankContext(enabled=True, mode=mode, families=families,
                       fixture_by_cust=fixture_by_cust, pulled=pulled,
                       provenance_raw=provenance_raw,
                       fixture_meta=(fixture or {}).get("_meta"), reason=reason,
                       bank_keys=_answered_keys(pulled) if pulled is not None else frozenset())


__all__ = ["BankContext", "build_context", "weakest", "FAMILIES", "ALWAYS_SIMULATED",
           "FAMILY_APIS", "PULLED_NAME", "PROVENANCE_NAME", "FIXTURE_NAME"]
