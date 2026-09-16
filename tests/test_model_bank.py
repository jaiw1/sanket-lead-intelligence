"""SM-6 — the ``--bank`` overlay: the fallback chain and provenance precedence."""

from __future__ import annotations

import json
from pathlib import Path

from model import bank as B

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# --bank not passed: untouched, every family SIMULATED
# --------------------------------------------------------------------------- #

def test_disabled_is_the_pre_sm6_pipeline(tmp_path: Path) -> None:
    ctx = B.build_context(tmp_path, enabled=False)
    assert ctx.enabled is False
    assert set(ctx.families.values()) == {"SIMULATED"}
    assert ctx.fixture_by_cust == {}
    assert ctx.overlay_for("LB-2000001") == {}
    assert ctx.provenance_for("LB-2000001") == {f: "SIMULATED" for f in B.FAMILIES}


# --------------------------------------------------------------------------- #
# --bank passed, nothing on disk at all: degrades to SIMULATED, does not raise
# --------------------------------------------------------------------------- #

def test_enabled_with_nothing_on_disk_degrades_to_simulated(tmp_path: Path) -> None:
    ctx = B.build_context(tmp_path / "does-not-exist", enabled=True)
    assert ctx.enabled is True
    assert set(ctx.families.values()) == {"SIMULATED"}
    assert ctx.mode == "simulated"


# --------------------------------------------------------------------------- #
# --bank passed, no pulled.json, the committed fixture.json present: whole-
# fixture fallback, honestly partial per customer
# --------------------------------------------------------------------------- #

def test_the_real_fixture_covers_120_customers_by_cust_id(tmp_path: Path) -> None:
    ctx = B.build_context(ROOT / "data", enabled=True)
    assert ctx.pulled is None
    assert ctx.mode == "fixture"
    assert len(ctx.fixture_by_cust) == 120
    for fam in B.FAMILY_APIS:
        assert ctx.families[fam] == "FIXTURE"
    for fam in B.ALWAYS_SIMULATED:
        assert ctx.families[fam] == "SIMULATED"
    assert ctx.families["model"] == "FIXTURE"  # weakest of {FIXTURE, SIMULATED}


def test_a_fixture_covered_customer_reads_fixture_a_stranger_reads_simulated() -> None:
    """The aggregate says FIXTURE; a specific customer only reads FIXTURE if the
    fixture actually has a row for them — this is the honesty check the
    ``--bank`` overlay has to pass.
    """
    ctx = B.build_context(ROOT / "data", enabled=True)
    covered = "LB-2000001"  # first fixture row, per data/bank/fixture.json
    stranger = "LB-2059999"  # last id in the 60,000-row book, never in the fixture
    assert covered in ctx.fixture_by_cust
    assert stranger not in ctx.fixture_by_cust

    p_covered = ctx.provenance_for(covered)
    p_stranger = ctx.provenance_for(stranger)
    for fam in B.FAMILY_APIS:
        assert p_covered[fam] == "FIXTURE"
        assert p_stranger[fam] == "SIMULATED"
    assert p_covered["model"] == "FIXTURE"
    assert p_stranger["model"] == "SIMULATED"
    assert ctx.overlay_for(covered)["cust_id"] == covered
    assert ctx.overlay_for(stranger) == {}


# --------------------------------------------------------------------------- #
# --bank passed, pulled.json present: BANK_API where it answered, FIXTURE where
# it did not
# --------------------------------------------------------------------------- #

def _write_pulled(bank_dir: Path, answered: dict[str, list]) -> None:
    bank_dir.mkdir(parents=True, exist_ok=True)
    apis = {api: dict(api_id=api, provenance="BANK_API", records=recs)
           for api, recs in answered.items()}
    (bank_dir / B.PULLED_NAME).write_text(json.dumps(dict(apis=apis)), encoding="utf-8")


def test_pulled_json_answers_some_apis_mixed_mode(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_pulled(data_dir / "bank", {"365": [{"balance": 1}], "393": [{"txn": 1}]})
    fixture_src = json.loads((ROOT / "data" / "bank" / "fixture.json").read_text())
    (data_dir / "bank" / "fixture.json").write_text(json.dumps(fixture_src), encoding="utf-8")

    ctx = B.build_context(data_dir, enabled=True)
    assert ctx.families["casa_behaviour"] == "BANK_API"    # 365 + 393 answered
    assert ctx.families["identity"] == "FIXTURE"           # 442/394/456/508 did not
    assert ctx.families["holdings"] == "FIXTURE"           # 394 did not
    assert ctx.families["cross_bank"] == "FIXTURE"         # 595/739 did not
    assert ctx.mode == "mixed"
    assert ctx.families["model"] == "FIXTURE"              # weakest wins


def test_pulled_json_answers_everything_is_live_mode(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    all_apis = ["365", "393", "394", "442", "456", "508", "595", "739"]
    _write_pulled(data_dir / "bank", {a: [{"x": 1}] for a in all_apis})
    ctx = B.build_context(data_dir, enabled=True)
    for fam in B.FAMILY_APIS:
        assert ctx.families[fam] == "BANK_API"
    for fam in B.ALWAYS_SIMULATED:
        assert ctx.families[fam] == "SIMULATED"
    assert ctx.families["model"] == "SIMULATED"  # weakest of {BANK_API, SIMULATED}
    assert ctx.mode == "mixed"  # digital/consent/journey are still SIMULATED, never "live"


# --------------------------------------------------------------------------- #
# provenance precedence: BANK_API > SIMULATED > FIXTURE
# --------------------------------------------------------------------------- #

def test_weakest_respects_the_documented_trust_order() -> None:
    assert B.weakest(["BANK_API"]) == "BANK_API"
    assert B.weakest(["BANK_API", "SIMULATED"]) == "SIMULATED"
    assert B.weakest(["BANK_API", "FIXTURE"]) == "FIXTURE"
    assert B.weakest(["SIMULATED", "FIXTURE"]) == "FIXTURE"
    assert B.weakest(["BANK_API", "SIMULATED", "FIXTURE"]) == "FIXTURE"
    assert B.weakest([]) == "SIMULATED"


def test_the_model_family_is_always_the_weakest_of_the_other_seven() -> None:
    for enabled, data_dir in ((False, ROOT / "data"), (True, ROOT / "data")):
        ctx = B.build_context(data_dir, enabled=enabled)
        others = [v for k, v in ctx.families.items() if k != "model"]
        assert ctx.families["model"] == B.weakest(others)
