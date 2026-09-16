"""
Schema tests for `validation/criteria.yaml`.

These do not test a model. They test the CONTRACT: that the pre-registered file
parses, that every band is well-formed, that nothing is duplicated, and that the
registration timestamp is a real timestamp. If this file goes red, the evidence
of pre-registration is what is broken, which matters more than any metric.

Run with pytest, or standalone:

    pytest validation/tests
    python3 -m validation.tests.test_criteria
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
import yaml

from validation.criteria import RUNNERS, CriteriaDoc, CriteriaError, load

CRITERIA_PATH = Path(__file__).resolve().parents[1] / "criteria.yaml"

#: Ops that legitimately carry no numeric threshold.
THRESHOLDLESS = {"monotone_increasing", "exists", "report"}


@pytest.fixture(scope="module")
def doc() -> CriteriaDoc:
    return load(CRITERIA_PATH)


# ---------------------------------------------------------------------------
def test_criteria_file_exists():
    assert CRITERIA_PATH.is_file(), f"{CRITERIA_PATH} is missing — there is no pre-registration"


def test_yaml_loads_as_a_mapping():
    raw = yaml.safe_load(CRITERIA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert raw.get("criteria"), "criteria.yaml declares no criteria"


def test_loads_against_the_schema(doc: CriteriaDoc):
    assert doc.product
    assert doc.schema_version
    assert doc.registered_by == "RR Squad"
    assert len(doc.criteria) > 0


def test_registered_at_parses(doc: CriteriaDoc):
    assert isinstance(doc.registered_at, _dt.datetime)
    assert doc.registered_at.tzinfo is not None, "registered_at must carry a timezone offset"
    assert doc.registered_at.year >= 2026


def test_every_runner_is_one_of_the_twelve(doc: CriteriaDoc):
    for c in doc.criteria:
        assert c.runner in RUNNERS, f"{c.id}: unknown runner {c.runner!r}"


def test_runner_names_span_01_to_12():
    assert len(RUNNERS) == 12
    assert [r.split("_", 1)[0] for r in RUNNERS] == [f"{i:02d}" for i in range(1, 13)]


def test_no_duplicate_criterion_ids(doc: CriteriaDoc):
    ids = [c.id for c in doc.criteria]
    assert len(ids) == len(set(ids)), f"duplicate ids: {sorted({i for i in ids if ids.count(i) > 1})}"


def test_no_duplicate_cut_ids(doc: CriteriaDoc):
    ids = [c.id for c in doc.cuts]
    assert len(ids) == len(set(ids))


def test_thresholds_are_numeric(doc: CriteriaDoc):
    for c in doc.criteria:
        if c.op in THRESHOLDLESS:
            assert c.threshold is None, f"{c.id}: op {c.op!r} must not carry a threshold"
            continue
        if c.op == "between":
            assert isinstance(c.threshold, list) and len(c.threshold) == 2, f"{c.id}: need [lo, hi]"
            lo, hi = c.threshold
            assert isinstance(lo, (int, float)) and not isinstance(lo, bool), f"{c.id}: lo not numeric"
            assert isinstance(hi, (int, float)) and not isinstance(hi, bool), f"{c.id}: hi not numeric"
            assert lo < hi, f"{c.id}: lo must be below hi"
        else:
            assert isinstance(c.threshold, (int, float)) and not isinstance(c.threshold, bool), \
                f"{c.id}: threshold {c.threshold!r} is not numeric"


def test_every_criterion_has_a_rationale_and_a_source(doc: CriteriaDoc):
    for c in doc.criteria:
        assert c.rationale.strip(), f"{c.id}: no rationale"
        assert c.source.strip(), f"{c.id}: no source — a band with no plan reference is not pre-registered"


def test_severities_are_valid_and_reported_items_are_marked(doc: CriteriaDoc):
    for c in doc.criteria:
        assert c.severity in ("fail", "warn", "report"), f"{c.id}: bad severity"
    assert any(c.severity == "report" for c in doc.criteria), \
        "no criterion is marked `report` — the 'reported, no target' items are missing"
    assert any(c.severity == "fail" for c in doc.criteria), "no criterion actually gates"


def test_per_cut_criteria_name_a_declared_cut(doc: CriteriaDoc):
    known = {c.id for c in doc.cuts} | {"all", "protected_proxies"}
    for c in doc.criteria:
        if c.scope == "per_cut":
            assert c.cut in known, f"{c.id}: cut {c.cut!r} is not declared"


def test_seeds_meet_the_registered_minimum(doc: CriteriaDoc):
    assert doc.seeds.n_min >= 5, "the plan pre-registers at least 5 seeds"
    if doc.seeds.seed_list is not None:
        assert len(doc.seeds.seed_list) >= doc.seeds.n_min


def test_both_splits_are_declared(doc: CriteriaDoc):
    assert "holdout" in doc.splits and "oot" in doc.splits


def test_amendments_are_dated_and_reasoned(doc: CriteriaDoc):
    for a in doc.amendments:
        assert isinstance(a.at, _dt.datetime)
        assert a.rationale.strip(), "an amendment without a rationale is not an amendment"


def test_bad_criteria_are_rejected(tmp_path: Path):
    """The loader must actually refuse a broken file, not shrug at it."""
    bad = tmp_path / "criteria.yaml"
    bad.write_text("product: X\ncriteria: []\n", encoding="utf-8")
    with pytest.raises(CriteriaError):
        load(bad)


# ---------------------------------------------------------------------------
def _main() -> int:
    """Standalone runner, so this file works without pytest installed."""
    d = load(CRITERIA_PATH)
    checks = [
        ("yaml loads as a mapping", lambda: test_yaml_loads_as_a_mapping()),
        ("loads against the schema", lambda: test_loads_against_the_schema(d)),
        ("registered_at parses", lambda: test_registered_at_parses(d)),
        ("runners are 01-12", lambda: (test_runner_names_span_01_to_12(),
                                       test_every_runner_is_one_of_the_twelve(d))),
        ("no duplicate criterion ids", lambda: test_no_duplicate_criterion_ids(d)),
        ("no duplicate cut ids", lambda: test_no_duplicate_cut_ids(d)),
        ("thresholds are numeric", lambda: test_thresholds_are_numeric(d)),
        ("rationale + source present", lambda: test_every_criterion_has_a_rationale_and_a_source(d)),
        ("severities valid", lambda: test_severities_are_valid_and_reported_items_are_marked(d)),
        ("per-cut criteria name a cut", lambda: test_per_cut_criteria_name_a_declared_cut(d)),
        ("seeds >= 5", lambda: test_seeds_meet_the_registered_minimum(d)),
        ("splits declared", lambda: test_both_splits_are_declared(d)),
        ("amendments dated", lambda: test_amendments_are_dated_and_reasoned(d)),
    ]
    failed = 0
    for name, fn in checks:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
    sev = {}
    for c in d.criteria:
        sev[c.severity] = sev.get(c.severity, 0) + 1
    print(f"\n{d.product}: {len(d.criteria)} criteria "
          f"({', '.join(f'{v} {k}' for k, v in sorted(sev.items()))}) "
          f"across {len(set(c.runner for c in d.criteria))} runners; "
          f"{len(d.cuts)} cuts; registered {d.registered_at.isoformat()}")
    print("PASS" if not failed else f"{failed} CHECK(S) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
