# -*- coding: utf-8 -*-
"""SM-6 — the demo identity binding, and everything it is not allowed to touch.

One customer's identity fields are bound to the Atlas sandbox's sample master
record so the platform's API 456 dedupe path has a PAN to search on (it refuses a
request without one). That is a deliberate hole in "every value here is
generated", so it gets the tests a deliberate hole needs: it applies to exactly
one named customer, it moves exactly one provenance family, it carries its own
declaration, and it does not exist at all without a pull that really answered
about that record.

Everything here is unit-level against a crafted `data/bank/pulled.json` rather
than the real one: `pulled.json` is gitignored, so a fresh checkout has none, and
a test that silently skips is a test that is not run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from model import bank as B
from model import export as EXP

#: The sandbox record the committed binding names.
BOUND_CUST = next(iter(EXP.DEMO_BINDINGS))
BOUND_CIF = EXP.DEMO_BINDINGS[BOUND_CUST]


def _pulled(*, pan: str | None = "FGHPP4567T", cust_id: str = BOUND_CIF) -> dict:
    """A minimal `pulled.json`: API 456 answering about one master record, 365 beside it."""
    master = {"custId": cust_id, "custName": "PRIYAPATIL", "custPagerNo": "9988776655",
              "gstReagistration": "07ABCDE1234F1Z5"}
    if pan is not None:
        master["panGirNum"] = pan
    return {
        "product": "sanket",
        "generated_at": "2026-09-22T02:00:00+05:30",
        "apis": {
            "456": {"api_id": "456", "provenance": "BANK_API", "http_status": 200,
                    "n_records": 1, "records": [master]},
            "365": {"api_id": "365", "provenance": "BANK_API", "http_status": 200,
                    "n_records": 1, "records": [{
                        "acctId": "660100100003", "custId": cust_id,
                        "personName": {"firstName": "PRIYA", "lastName": "PATIL",
                                       "name": "PRIYAPATIL"}}]},
        },
    }


def _context(tmp_path: Path, pulled: dict | None, enabled: bool = True) -> B.BankContext:
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir(parents=True, exist_ok=True)
    if pulled is not None:
        (bank_dir / B.PULLED_NAME).write_text(json.dumps(pulled), encoding="utf-8")
    return B.build_context(tmp_path, enabled)


# --------------------------------------------------------------------------- #
# the binding itself
# --------------------------------------------------------------------------- #

def test_exactly_one_customer_is_bound() -> None:
    """A table, not a rule. If this ever grows, it should grow visibly."""
    assert len(EXP.DEMO_BINDINGS) == 1
    assert BOUND_CUST.startswith("LB-")
    assert BOUND_CIF.isdigit() and 6 <= len(BOUND_CIF) <= 12, \
        "the bound id has to satisfy the contract's cif_id pattern"


def test_the_bound_fields_come_from_the_pull_not_from_this_repo(tmp_path: Path) -> None:
    ctx = _context(tmp_path, _pulled())
    bound = EXP.demo_binding_for(BOUND_CUST, ctx)
    assert bound is not None
    assert bound["cif_id"] == BOUND_CIF
    assert bound["pan"] == "FGHPP4567T"
    assert bound["entity_name"] == "PRIYAPATIL"
    assert bound["mobile"] == "9988776655"
    assert bound["demo_binding"] is True
    assert bound["demo_binding_note"] == EXP.DEMO_BINDING_NOTE
    assert "synthetic" in bound["demo_binding_note"], \
        "the note's whole job is to say what is NOT from the bank"

    # Not typed here: change what the bank answered and the binding follows it.
    other = EXP.demo_binding_for(BOUND_CUST, _context(tmp_path / "b", _pulled(pan="ZZZPZ9999Z")))
    assert other["pan"] == "ZZZPZ9999Z"


def test_no_other_customer_is_bound(tmp_path: Path) -> None:
    ctx = _context(tmp_path, _pulled())
    for cust_id in ("LB-2000001", "LB-9999999", BOUND_CUST[:-1] + "0"):
        if cust_id in EXP.DEMO_BINDINGS:
            continue
        assert EXP.demo_binding_for(cust_id, ctx) is None, cust_id


@pytest.mark.parametrize("make, why", [
    (lambda t: _context(t, _pulled(), enabled=False), "--bank was not passed"),
    (lambda t: _context(t, None), "no pull on this checkout"),
    (lambda t: _context(t, _pulled(cust_id="11112222")), "the pull answered about someone else"),
    (lambda t: _context(t, _pulled(pan=None)), "the answer carried no PAN"),
])
def test_nothing_binds_without_an_answer_about_that_record(tmp_path: Path, make, why) -> None:
    """The binding is a fact about a pull, not a decoration applied regardless."""
    assert EXP.demo_binding_for(BOUND_CUST, make(tmp_path)) is None, why


# --------------------------------------------------------------------------- #
# what it is allowed to change in customers[]
# --------------------------------------------------------------------------- #

def _snap_rows() -> pd.DataFrame:
    return pd.DataFrame([
        dict(cust_id=BOUND_CUST, segment="salaried", age=38, city_tier=1, tenure_m=116,
             consent_marketing=1, dnd=0, credits_med_6m=144793.0, t_income_at_month=150000.0),
        dict(cust_id="LB-2000001", segment="gig", age=29, city_tier=2, tenure_m=14,
             consent_marketing=1, dnd=0, credits_med_6m=41000.0, t_income_at_month=39000.0),
    ])


def test_only_the_identity_family_moves_and_only_on_the_bound_row(tmp_path: Path) -> None:
    """The trap this guards.

    `BankContext.provenance_for` badges a customer BANK_API for every family the
    pull answered about them, and the bound sandbox id IS one the pull answered
    about — so writing the bound cif_id and then asking for provenance would
    quietly promote casa_behaviour and holdings too, and put a bank badge on a
    generated balance. The families must read exactly what they read with no
    binding at all.
    """
    ctx = _context(tmp_path, _pulled())
    rows = {c["cust_id"]: c for c in EXP.build_customers(_snap_rows(), {}, ctx)}
    bound, other = rows[BOUND_CUST], rows["LB-2000001"]

    baseline = ctx.provenance_for(BOUND_CUST, EXP._cif_id(BOUND_CUST))
    assert bound["provenance"]["identity"] == "BANK_API"
    assert {k: v for k, v in bound["provenance"].items() if k != "identity"} == \
           {k: v for k, v in baseline.items() if k != "identity"}
    assert set(bound["provenance"]) == set(B.FAMILIES)


def test_the_bound_row_declares_itself_and_the_others_are_untouched(tmp_path: Path) -> None:
    ctx = _context(tmp_path, _pulled())
    rows = {c["cust_id"]: c for c in EXP.build_customers(_snap_rows(), {}, ctx)}
    bound, other = rows[BOUND_CUST], rows["LB-2000001"]

    assert bound["cif_id"] == BOUND_CIF
    assert bound["demo_binding"] is True
    assert bound["demo_binding_note"] == EXP.DEMO_BINDING_NOTE
    assert (bound["pan"], bound["entity_name"], bound["mobile"]) == \
           ("FGHPP4567T", "PRIYAPATIL", "9988776655")
    # Nothing but identity: the generator's own numbers travel unchanged.
    assert bound["estimated_income_monthly"] == 144793.0
    assert bound["segment"] == "salaried" and bound["age"] == 38

    # ... and the customer beside it is exactly what it was before any of this.
    assert other["cif_id"] == EXP._cif_id("LB-2000001")
    for key in ("pan", "entity_name", "mobile", "demo_binding", "demo_binding_note"):
        assert key not in other, f"{key} leaked onto an unbound customer"
    assert other["provenance"] == ctx.provenance_for("LB-2000001", other["cif_id"])


def test_without_a_pull_the_bound_customer_is_an_ordinary_customer(tmp_path: Path) -> None:
    ctx = _context(tmp_path, None, enabled=False)
    rows = {c["cust_id"]: c for c in EXP.build_customers(_snap_rows(), {}, ctx)}
    bound = rows[BOUND_CUST]
    assert bound["cif_id"] == EXP._cif_id(BOUND_CUST)
    assert bound["provenance"]["identity"] == "SIMULATED"
    for key in ("pan", "entity_name", "mobile", "demo_binding", "demo_binding_note"):
        assert key not in bound


# --------------------------------------------------------------------------- #
# leads[] has to agree with customers[]
# --------------------------------------------------------------------------- #

def _lead_internal(cust_id: str) -> dict:
    return dict(
        id=cust_id, suppressed=False, segment="salaried", age=38, city_tier=1, tenure_m=116,
        consent=True, product="personal", tier="warm", lang="en",
        product_menu=[dict(product="personal", p=0.2593, reason="r", emi=10100.0,
                           window_days=1, contact_by="2025-09-15")],
        score=0.2593, intent=0.97, capacity=1.0, blend=0.98,
        abandoned_at="2025-09-14", scored_at="2026-09-01", contact_by="2025-09-15",
        window_days=1, outcome_horizon_days=1, salary_m=144793.0, retained_income=56241.0,
        safe_emi=22500.0, reasons=["a"], negative_chips=[],
        pitch=dict(opener="o", why_now="w", proof=["p"]), objection=dict(q="q", a="a"),
        nba="call", suppression_reason="none", journey_ref="AP-0009355", spark=[1, 2, 3],
    )


def test_the_lead_carries_the_same_cif_as_its_customer(tmp_path: Path) -> None:
    """`leads[].id` must appear in `customers[]`, and the platform sends
    `lead.cif_id` to the 456 gateway. Two CIFs for one customer would ask the
    bank about somebody who does not exist."""
    ctx = _context(tmp_path, _pulled())
    refs = {"personal": "AMT-PERSONAL-300K-36M"}
    leads = EXP.build_leads([_lead_internal(BOUND_CUST), _lead_internal("LB-2000001")], {}, refs, ctx)
    bound, other = leads[0], leads[1]

    customers = {c["cust_id"]: c for c in EXP.build_customers(_snap_rows(), {}, ctx)}
    assert bound["cif_id"] == customers[BOUND_CUST]["cif_id"] == BOUND_CIF
    assert other["cif_id"] == customers["LB-2000001"]["cif_id"]

    assert bound["provenance"]["identity"] == "BANK_API"
    assert other["provenance"]["identity"] == "SIMULATED"
    # Only identity. Every other family on a lead is SIMULATED and stays so.
    assert set(v for k, v in bound["provenance"].items() if k != "identity") == {"SIMULATED"}


def test_a_lead_is_unbound_when_the_export_has_no_bank_context() -> None:
    """`build_leads` without a context is the pre-SM-6 call, and must behave like it."""
    refs = {"personal": "AMT-PERSONAL-300K-36M"}
    lead = EXP.build_leads([_lead_internal(BOUND_CUST)], {}, refs)[0]
    assert lead["cif_id"] == EXP._cif_id(BOUND_CUST)
    assert lead["provenance"]["identity"] == "SIMULATED"
