"""SM-4 — the RM roster: deterministic round-robin, and the pulled.json override."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from model import roster as RO

ROOT = Path(__file__).resolve().parents[1]


def _ids(n: int, start: int = 2_000_000) -> list[str]:
    return [f"LB-{start + i:07d}" for i in range(n)]


# --------------------------------------------------------------------------- #
# the seeded roster (data/roster.yaml)
# --------------------------------------------------------------------------- #

def test_the_committed_roster_loads_and_is_simulated() -> None:
    r = RO.load_roster(ROOT / "data")
    assert r.source == RO.SOURCE_SIMULATED
    assert len(r.rms) >= 1
    for rm in r.rms:
        assert rm.rm_id.startswith("EIN-") and rm.rm_id[4:].isdigit() and len(rm.rm_id) == 10
        assert rm.rm_name and rm.rm_branch


def test_assignment_is_deterministic_across_runs() -> None:
    r = RO.load_roster(ROOT / "data")
    ids = _ids(37)
    a = RO.assign(ids, r)
    b = RO.assign(ids, r)
    assert {c: rm.rm_id for c, rm in a.items()} == {c: rm.rm_id for c, rm in b.items()}


def test_assignment_is_balanced_round_robin() -> None:
    """Every RM gets floor(n/k) or ceil(n/k) customers — a real round-robin,
    not a hash that happens to spread out."""
    r = RO.load_roster(ROOT / "data")
    n_rms = len(r.active_rms)
    ids = _ids(4 * n_rms + 3)
    m = RO.assign(ids, r)
    counts = {}
    for rm in m.values():
        counts[rm.rm_id] = counts.get(rm.rm_id, 0) + 1
    assert set(counts) == {rm.rm_id for rm in r.active_rms}
    lo, hi = min(counts.values()), max(counts.values())
    assert hi - lo <= 1


def test_assignment_does_not_depend_on_input_order() -> None:
    """Sorted by cust_id internally — a shuffled call list gives the same map."""
    r = RO.load_roster(ROOT / "data")
    ids = _ids(23)
    a = RO.assign(ids, r)
    b = RO.assign(list(reversed(ids)), r)
    assert {c: rm.rm_id for c, rm in a.items()} == {c: rm.rm_id for c, rm in b.items()}


def test_inactive_rms_are_skipped() -> None:
    active = RO.RM(rm_id="EIN-100001", rm_name="A", rm_branch="X", active=True)
    inactive = RO.RM(rm_id="EIN-100002", rm_name="B", rm_branch="Y", active=False)
    r = RO.Roster(rms=(active, inactive), source=RO.SOURCE_SIMULATED)
    m = RO.assign(_ids(5), r)
    assert set(rm.rm_id for rm in m.values()) == {"EIN-100001"}


def test_an_empty_active_roster_raises() -> None:
    r = RO.Roster(rms=(RO.RM(rm_id="EIN-1", rm_name="A", rm_branch="X", active=False),),
                 source=RO.SOURCE_SIMULATED)
    with pytest.raises(ValueError):
        RO.assign(_ids(2), r)


def test_roster_block_carries_provenance(tmp_path: Path) -> None:
    r = RO.load_roster(ROOT / "data")
    block = RO.roster_block(r)
    assert block["source"] == "SIMULATED"
    assert block["n_active"] <= block["n_rms"] == len(block["rms"])
    for rm in block["rms"]:
        assert {"rm_id", "rm_name", "rm_branch", "active"} <= set(rm)


# --------------------------------------------------------------------------- #
# data/bank/pulled.json — the BANK_API path (SM-4 checks this first)
# --------------------------------------------------------------------------- #

def _write_pulled(bank_dir: Path, api_442_records: list[dict] | None = None) -> None:
    bank_dir.mkdir(parents=True, exist_ok=True)
    apis = {}
    if api_442_records is not None:
        apis["442"] = dict(api_id="442", provenance="BANK_API", records=api_442_records)
    (bank_dir / RO.PULLED_NAME).write_text(json.dumps(dict(apis=apis)), encoding="utf-8")


def _seed(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "roster.yaml").write_text(
        "rms:\n  - rm_id: EIN-999999\n    rm_name: Test RM\n    rm_branch: Test Branch\n",
        encoding="utf-8")


def test_508_is_not_a_roster_source_because_the_bank_rejected_it() -> None:
    """The refusal is a fact about the catalogue, so it is asserted, not described."""
    assert "508" not in RO.ROSTER_APIS
    assert RO.ROSTER_APIS == ("442",)


def test_the_live_442_shape_is_read_and_reported(tmp_path: Path) -> None:
    """Verbatim from the 2026-09-17 pull: the one CIF the sandbox answers for."""
    data_dir = tmp_path / "data"
    _seed(data_dir)
    _write_pulled(data_dir / "bank", api_442_records=[dict(
        customerSummary=dict(customerName="SAMPLE CUSTOMER", custCifId="SANDBOX-CIF-2",
                             accountManager="SYSCODE", customerID="SANDBOX-CIF-1", custRating="NA"),
        exposureSummary=dict(totalLimit=dict(amount="11821212.00", currency="INR")),
    )])
    found = RO.account_managers(json.loads((data_dir / "bank" / RO.PULLED_NAME).read_text()))
    assert len(found) == 1
    assert found[0]["cif_id"] == "SANDBOX-CIF-2"
    assert found[0]["customer_id"] == "SANDBOX-CIF-1"
    assert found[0]["customer_name"] == "SAMPLE CUSTOMER"
    assert found[0]["account_manager"] == "SYSCODE"


def test_a_bare_account_manager_code_does_not_become_an_rm(tmp_path: Path) -> None:
    """`SYSCODE` is a bank system code with no name and no branch. It is reported as what
    442 returned and the roster stays SIMULATED — a blank-branch "RM: SYSCODE" in front of a
    relationship manager would be a worse claim than an honestly-labelled seed."""
    data_dir = tmp_path / "data"
    _seed(data_dir)
    _write_pulled(data_dir / "bank", api_442_records=[dict(
        customerSummary=dict(customerName="SAMPLE CUSTOMER", custCifId="SANDBOX-CIF-2",
                             accountManager="SYSCODE", customerID="SANDBOX-CIF-1"))])
    r = RO.load_roster(data_dir)
    assert r.source == RO.SOURCE_SIMULATED
    assert r.rms[0].rm_id == "EIN-999999"
    assert len(r.bank_managers) == 1 and r.bank_managers[0]["account_manager"] == "SYSCODE"
    assert "SYSCODE" in r.bank_reason and "SIMULATED" in r.bank_reason
    block = RO.roster_block(r)
    assert block["bank_account_managers"][0]["cif_id"] == "SANDBOX-CIF-2"
    assert block["bank_source_note"] == r.bank_reason
    assert all(rm["source"] == RO.SOURCE_SIMULATED for rm in block["rms"])


def test_442_with_a_real_manager_name_wins_over_the_seeded_roster(tmp_path: Path) -> None:
    """The source really is ranked first — the moment 442 carries a name, it is used.
    This is not the shape the sandbox returns today; it is the shape the code is for."""
    data_dir = tmp_path / "data"
    _seed(data_dir)
    _write_pulled(data_dir / "bank", api_442_records=[dict(
        customerSummary=dict(customerName="SAMPLE CUSTOMER", custCifId="SANDBOX-CIF-2",
                             accountManager="SANDBOX-BRANCH-1", accountManagerName="Sample Customer",
                             branchName="Mumbai"))])
    r = RO.load_roster(data_dir)
    assert r.source == RO.SOURCE_BANK_API
    assert len(r.rms) == 1
    assert r.rms[0].rm_id == "EIN-SANDBOX-BRANCH-1"
    assert r.rms[0].rm_name == "Sample Customer"
    assert r.rms[0].rm_branch == "Mumbai"
    assert r.rms[0].source == RO.SOURCE_BANK_API


def test_pulled_json_present_but_empty_falls_back_to_seeds(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "roster.yaml").parent.mkdir(parents=True, exist_ok=True)
    (data_dir / "roster.yaml").write_text(
        "rms:\n  - rm_id: EIN-999999\n    rm_name: Test RM\n    rm_branch: Test Branch\n",
        encoding="utf-8")
    _write_pulled(data_dir / "bank", api_442_records=[])
    r = RO.load_roster(data_dir)
    assert r.source == RO.SOURCE_SIMULATED
    assert r.rms[0].rm_id == "EIN-999999"


def test_a_missing_pulled_json_falls_back_to_seeds(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "roster.yaml").write_text(
        "rms:\n  - rm_id: EIN-555555\n    rm_name: X\n    rm_branch: Y\n", encoding="utf-8")
    r = RO.load_roster(data_dir)
    assert r.source == RO.SOURCE_SIMULATED and r.rms[0].rm_id == "EIN-555555"
