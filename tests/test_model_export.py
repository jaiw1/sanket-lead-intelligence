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
