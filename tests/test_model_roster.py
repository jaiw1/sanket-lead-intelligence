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

def _write_pulled(bank_dir: Path, api_508_records: list[dict] | None = None,
                  api_442_records: list[dict] | None = None) -> None:
    bank_dir.mkdir(parents=True, exist_ok=True)
    apis = {}
    if api_508_records is not None:
        apis["508"] = dict(api_id="508", provenance="BANK_API", records=api_508_records)
    if api_442_records is not None:
        apis["442"] = dict(api_id="442", provenance="BANK_API", records=api_442_records)
    (bank_dir / RO.PULLED_NAME).write_text(json.dumps(dict(apis=apis)), encoding="utf-8")


def test_pulled_json_508_hrms_wins_over_the_seeded_roster(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_pulled(data_dir / "bank", api_508_records=[
        dict(rm_ein="SANDBOX-EIN-1", rm_name="Sample Customer", branch_name="Pune"),
        dict(rm_ein="EIN-SANDBOX-BRANCH-1", rm_name="Pawan Sharma", branch_name="Mumbai"),
    ])
    r = RO.load_roster(data_dir)
    assert r.source == RO.SOURCE_BANK_API
    assert {rm.rm_id for rm in r.rms} == {"EIN-SANDBOX-EIN-1", "EIN-SANDBOX-BRANCH-1"}


def test_pulled_json_442_account_manager_is_a_fallback_reading(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_pulled(data_dir / "bank", api_442_records=[
        dict(hrmsInfo=dict(supEin="SANDBOX-BRANCH-1", fullNameTitle="Ms Sample Customer", location="Mumbai")),
    ])
    r = RO.load_roster(data_dir)
    assert r.source == RO.SOURCE_BANK_API
    assert len(r.rms) == 1 and r.rms[0].rm_id == "EIN-SANDBOX-BRANCH-1"


def test_pulled_json_present_but_empty_falls_back_to_seeds(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "roster.yaml").parent.mkdir(parents=True, exist_ok=True)
    (data_dir / "roster.yaml").write_text(
        "rms:\n  - rm_id: EIN-999999\n    rm_name: Test RM\n    rm_branch: Test Branch\n",
        encoding="utf-8")
    _write_pulled(data_dir / "bank", api_508_records=[])
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
