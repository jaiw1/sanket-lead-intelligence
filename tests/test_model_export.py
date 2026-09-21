"""SM-6 — ``data/export/sanket_export.json`` validates against the platform's
own ``rrsquad-platform/contracts/sanket_export.schema.json``.

The platform repo is a sibling checkout, not a dependency of this one; every
test here skips (rather than fails) if it is not present at the expected path,
so this repo's own suite never depends on another repo existing on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from model import emi as E

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT.parent / "rrsquad-platform"
SCHEMA_PATH = PLATFORM / "contracts" / "sanket_export.schema.json"

pytestmark = pytest.mark.skipif(
    not SCHEMA_PATH.exists(),
    reason=f"sibling repo not found: {SCHEMA_PATH} (this suite validates against it when present)")


def _validate(instance: dict) -> list:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))


#: The only three fields the brief excuses — filled by the platform's batch,
#: never by this script. Any OTHER error is real.
ALLOWED_GAP_PATHS = {".meta.model_run_id", ".meta.git_sha", ".meta.criteria_sha"}


def _where(err) -> str:
    parts = []
    for token in err.absolute_path:
        parts.append(f"[{token}]" if isinstance(token, int) else f".{token}")
    return "".join(parts) or "<root>"


def test_the_export_is_written_when_bank_is_passed(packed_bank: SimpleNamespace) -> None:
    assert packed_bank.export_path.exists(), "src/model/export.py did not write the file"
    payload = json.loads(packed_bank.export_path.read_text())
    for key in ("meta", "counts", "metrics", "customers", "journeys", "leads",
               "amortisation_schedules", "gig_case_id"):
        assert key in payload, key
    assert payload["customers"], "customers[] must not be empty"
    assert payload["leads"], "leads[] must not be empty"
    assert len(payload["amortisation_schedules"]) == 6


def test_the_export_validates_against_the_platform_contract(packed_bank: SimpleNamespace) -> None:
    payload = json.loads(packed_bank.export_path.read_text())
    errors = _validate(payload)
    unexpected = [e for e in errors if _where(e) not in ALLOWED_GAP_PATHS]
    if unexpected:
        detail = "\n".join(f"  {_where(e)}: {e.message}" for e in unexpected[:25])
        pytest.fail(f"{len(unexpected)} unexpected schema violation(s):\n{detail}")
    seen_gap_paths = {_where(e) for e in errors}
    assert seen_gap_paths <= ALLOWED_GAP_PATHS


def test_the_three_meta_gaps_are_valid_shaped_placeholders(packed_bank: SimpleNamespace) -> None:
    """Even the excused fields must be the RIGHT SHAPE — a batch that reads a
    malformed placeholder should fail loudly, not silently accept garbage.
    """
    import re

    payload = json.loads(packed_bank.export_path.read_text())
    meta = payload["meta"]
    assert re.fullmatch(r"[0-9a-fA-F-]{36}", meta["model_run_id"])
    assert re.fullmatch(r"[0-9a-f]{40}", meta["git_sha"])
    assert re.fullmatch(r"[0-9a-f]{64}", meta["criteria_sha"])


def test_amortisation_schedule_provenance_matches_where_the_rows_came_from(
        packed_bank: SimpleNamespace) -> None:
    """`schedule: BANK_API` if and only if API 473 actually amortised that ticket.

    473 does answer — it is an amortisation engine, and the batch asks it once per
    reference ticket — but `data/bank/pulled.json` is gitignored, so a checkout that has
    never run a pull derives the rows instead. Either is fine; claiming BANK_API for rows
    we computed ourselves is not, and that is the direction this test guards.
    """
    payload = json.loads(packed_bank.export_path.read_text())
    for ref, sched in payload["amortisation_schedules"].items():
        assert sched["provenance"]["rate"] == "BANK_API", ref
        product = sched["product"]
        fetched = E.bank_schedule(product) is not None
        assert sched["provenance"]["schedule"] == ("BANK_API" if fetched else "SIMULATED"), ref


def test_suppressed_leads_have_no_assigned_rm_and_empty_menu(packed_bank: SimpleNamespace) -> None:
    payload = json.loads(packed_bank.export_path.read_text())
    for lead in payload["leads"]:
        if lead["suppressed"]:
            assert lead["assigned_rm_id"] is None
            assert lead["suppression_reasons"]
        else:
            assert lead["suppression_reasons"] == []


def test_gig_case_id_appears_in_leads(packed_bank: SimpleNamespace) -> None:
    payload = json.loads(packed_bank.export_path.read_text())
    ids = {lead["id"] for lead in payload["leads"]}
    assert payload["gig_case_id"] in ids


# --------------------------------------------------------------------------- #
# SM-7 — meanings survive the contract  (third-party review §13)
# --------------------------------------------------------------------------- #

def _enum_at(*path) -> list:
    node = json.loads(SCHEMA_PATH.read_text())
    for key in path:
        node = node[key]
    return node


def test_the_suppression_map_is_total_over_every_reason_a_row_can_carry() -> None:
    """No reason may reach the `.get` fallback, because a fallback is a substitution."""
    from model import SUPPRESSION_REASONS
    from model.export import _SUPPRESSION_REASON

    # `none` and `not_in_population` never appear on a SUPPRESSED row: the first
    # means the row was not suppressed, the second that it is not in the pool at all.
    must_map = set(SUPPRESSION_REASONS) - {"none", "not_in_population"}
    missing = must_map - set(_SUPPRESSION_REASON)
    assert not missing, f"these suppression reasons would be silently substituted: {sorted(missing)}"


def test_every_suppression_reason_keeps_its_own_meaning() -> None:
    """The round trip, not just the validity.

    `deceased` and `account_dormant` both used to export as `kyc_expired`, which
    passed the schema and told an RM to go and re-KYC a customer who had died.
    The mapping must be injective, and each contract value must be in the enum.
    """
    from model.export import _SUPPRESSION_REASON

    enum = set(_enum_at("$defs", "lead", "properties", "suppression_reasons", "items", "enum"))
    for internal, contract in _SUPPRESSION_REASON.items():
        assert contract in enum, f"{internal} -> {contract} is not a contract value"

    assert _SUPPRESSION_REASON["deceased"] == "deceased"
    assert _SUPPRESSION_REASON["account_dormant"] == "dormant"
    assert _SUPPRESSION_REASON["deceased"] != _SUPPRESSION_REASON["account_dormant"]

    collisions = [v for v in set(_SUPPRESSION_REASON.values())
                  if list(_SUPPRESSION_REASON.values()).count(v) > 1]
    assert not collisions, f"two distinct reasons collapse onto {collisions}"


def test_contact_fatigue_is_not_reported_as_a_vague_answer() -> None:
    """"Contacted five times this month" and "gave vague answers" are different
    accusations about different people."""
    from model.export import _NEGATIVE_SIGNAL

    enum = set(_enum_at("$defs", "lead", "properties", "negative_signals",
                        "items", "properties", "signal", "enum"))
    for chip, signal in _NEGATIVE_SIGNAL.items():
        assert signal in enum, f"{chip} -> {signal} is not a contract value"
    assert _NEGATIVE_SIGNAL["contacts_30d"] == "contact_fatigue"

    # Two chips knowingly still collapse; the list is asserted so the loss stays
    # deliberate and a third one cannot be added without this test noticing.
    collapsed = sorted(c for c, s in _NEGATIVE_SIGNAL.items() if s == "vague_answers")
    assert collapsed == ["journey_open_now", "journey_stated_income_ratio"]


def test_every_chip_the_generator_can_emit_has_a_mapping() -> None:
    from model.copy import NEGATIVE
    from model.export import _NEGATIVE_SIGNAL

    missing = set(NEGATIVE) - set(_NEGATIVE_SIGNAL)
    assert not missing, f"these chips would be substituted at export: {sorted(missing)}"


def test_the_export_does_not_rename_hanley_mcneil_to_delong(
        packed_bank: SimpleNamespace) -> None:
    """Review §10: they are different methods, and `method` is a claim about how
    the number was computed."""
    payload = json.loads(packed_bank.export_path.read_text())
    methods = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("method"), str):
                methods.add(node["method"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload["metrics"])
    assert "delong" not in methods, "a Hanley-McNeil interval is being labelled DeLong"
    assert "hanley-mcneil" in methods, "the AUC intervals lost their method name"
    assert methods <= set(_enum_at("$defs", "confidence_interval", "properties",
                                   "method", "enum"))


def test_every_lead_states_its_three_clocks(packed_bank: SimpleNamespace) -> None:
    """Review §5: abandonment, scoring and the contact deadline are three
    different instants, and `contact_by` runs from the first of them — the same
    rule the platform backend applies to `journeys.abandon_ts`."""
    import datetime as _dt

    payload = json.loads(packed_bank.export_path.read_text())
    windows = payload["meta"]["contact_windows_days"]
    for lead in payload["leads"]:
        abandoned = _dt.date.fromisoformat(lead["abandoned_at"])
        scored = _dt.date.fromisoformat(lead["scored_at"])
        due = _dt.date.fromisoformat(lead["contact_by"])
        assert abandoned <= scored, lead["id"]
        assert due == abandoned + _dt.timedelta(days=windows[lead["product"]]), lead["id"]
        assert lead["outcome_horizon_days"] == windows[lead["product"]]
        for item in lead["product_menu"]:
            item_due = _dt.date.fromisoformat(item["contact_by"])
            assert item_due == abandoned + _dt.timedelta(days=item["window_days"])
