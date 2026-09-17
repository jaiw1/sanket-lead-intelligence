"""SM-1/SM-2 — the export: what the cockpit reads, and what the headline says.

Four things this file exists to stop:

* **a suppressed customer reaching the queue.** The mentors' rule is "scored and
  shown, never called"; a regression here is a compliance incident, not a bug.
* **a hard-coded headline.** "9 → 30 disbursements per 100 RM calls" must be two
  measured numbers in a format string. The test moves the inputs and demands the
  sentence move with them, and greps the whole export for the retired claims.
* **a JSON the front end cannot load.** Strict JSON, no ``NaN``, every key
  ``app/src`` reads still present.
* **a metrics block that has drifted from the fields the platform contracts**
  (``data/bank/SCHEMA.md``) or from the bands ``validation/criteria.yaml``
  registered.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from model import PRODUCTS
from model import emi as EMI
from model import roster as RO
from model.metrics import headline

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# suppression
# --------------------------------------------------------------------------- #

def test_a_suppressed_row_is_never_queued(packed: SimpleNamespace) -> None:
    for lead in packed.out["leads"]:
        assert lead["queued"] is not lead["suppressed"]
        if lead["suppressed"]:
            assert lead["consent"] is False, lead["id"]
            assert lead["suppression_reason"] != "none"
            assert lead["nba"] == ""
        else:
            assert lead["suppression_reason"] == "none"


def test_suppressed_rows_are_still_scored_and_shown(packed: SimpleNamespace) -> None:
    """"Never called" is not "never looked at": the cockpit has to say *why*."""
    held = [x for x in packed.out["leads"] if x["suppressed"]]
    assert held, "the export carries no excluded rows at all"
    for lead in held:
        assert len(lead["product_menu"]) == 4
        assert lead["probability"] >= 0.0


def test_the_suppressed_count_is_a_kpi(packed: SimpleNamespace) -> None:
    s = packed.out["metrics"]["suppression"]
    assert s["suppressed_count"] >= 0
    assert s["pool_at_snapshot"] == s["suppressed_count"] + s["contactable_at_snapshot"]
    assert sum(s["reasons"].values()) == s["suppressed_count"]
    assert "none" not in s["reasons"]


def test_no_suppressed_row_is_in_training_or_in_a_metric(model_run: SimpleNamespace) -> None:
    """Eligibility gates the fit and the measurement, not just the display."""
    from model.train import fit_ranker

    st = model_run.stacked
    tr = st["cust_id"].isin(model_run.split.fit).to_numpy()
    assert (st.loc[tr & (st["eligible_for_contact"] == 0), "y"] == 0).all()
    # the ranker's own mask
    used = tr & (st["eligible_for_contact"].to_numpy() == 1)
    assert used.sum() < tr.sum(), "the small book has no suppressed training rows to exclude"
    assert callable(fit_ranker)


# --------------------------------------------------------------------------- #
# the headline  (SM-2)
# --------------------------------------------------------------------------- #

def test_the_headline_is_derived_not_typed() -> None:
    assert headline(0.09, 0.30) == "9 → 30 disbursements per 100 RM calls"
    assert headline(0.12, 0.41) == "12 → 41 disbursements per 100 RM calls"
    assert headline(0.09, 0.30) != headline(0.09, 0.25)


def test_the_packed_headline_matches_the_packed_numbers(packed: SimpleNamespace) -> None:
    m = packed.out["metrics"]
    assert m["headline"] == headline(m["headline_parts"]["baseline"],
                                     m["headline_parts"]["precision"])
    assert m["headline_parts"]["baseline"] == m["blended"]["baseline"]
    assert m["headline_parts"]["precision"] == m["blended"]["precision_at_budget"]
    assert m["headline_parts"]["budget"] == m["blended"]["budget"]


def test_the_baseline_is_the_random_contact_rate_over_the_same_population(
        packed: SimpleNamespace) -> None:
    """Both halves of the headline price the *same* hundred calls."""
    m = packed.out["metrics"]
    assert m["registered"]["random_contact_disbursement_rate"] == m["blended"]["baseline"]
    assert (m["registered"]["precision_at_10pct_budget"]
            == m["blended"]["precision_at_budget"])
    assert m["headline_parts"]["population"].startswith("drop-off")


RETIRED = [
    r"28\s*[x×]\b", r"\b1%\s*(?:->|→|to)\s*36", r"\b36\.0%", r"three product models",
]


def test_the_retired_claims_are_nowhere_in_the_export(packed: SimpleNamespace) -> None:
    """``1% → 36%`` and the ``28×`` that went with it ranked the whole book."""
    blob = json.dumps(packed.out, ensure_ascii=False)
    for pat in RETIRED:
        assert not re.search(pat, blob, re.I), pat


def test_the_retired_claims_are_nowhere_in_the_customer_facing_copy() -> None:
    """Prose *explaining* the retirement is fine; copy that ships is not.

    ``src/model/copy.py`` is everything an RM or a judge reads on screen, so it is
    the file the grep has to be clean on. The module docstrings elsewhere name the
    old claim on purpose — a number you retire without saying what it was is a
    number you have hidden.
    """
    text = (ROOT / "src" / "model" / "copy.py").read_text(encoding="utf-8")
    for pat in RETIRED:
        assert not re.search(pat, text, re.I), pat


def test_the_headline_has_exactly_one_producer() -> None:
    """Nothing else may assemble the sentence, or the two would drift."""
    hits = [p.name for p in sorted((ROOT / "src").rglob("*.py"))
            if "per 100 RM calls" in p.read_text(encoding="utf-8")
            and "f\"" in p.read_text(encoding="utf-8").split("per 100 RM calls")[0][-400:]]
    assert hits == ["metrics.py"], hits


# --------------------------------------------------------------------------- #
# the JSON contract
# --------------------------------------------------------------------------- #

def test_the_export_is_strict_json_with_no_nan(packed: SimpleNamespace) -> None:
    raw = packed.json_path.read_text(encoding="utf-8")
    assert "NaN" not in raw and "Infinity" not in raw
    reloaded = json.loads(raw, parse_constant=_no_constants)
    assert reloaded["metrics"]["headline"] == packed.out["metrics"]["headline"]


def _no_constants(name: str):
    raise AssertionError(f"non-finite value {name!r} in the export")


#: Exactly what ``app/src`` dereferences today.  Additive changes are fine;
#: losing one of these is a broken cockpit.
UI_KEYS = {
    "meta": ("n_customers", "n_consented", "ref_month", "generated_from"),
    "counts": ("hot", "warm", "green", "cold", "no_consent"),
    "lead": ("id", "segment", "age", "city_tier", "tenure_m", "consent", "product", "tier",
             "lang", "uplift_tag", "uplift_pct", "intent", "capacity", "score", "salary_m",
             "retained_income", "safe_emi", "reasons", "pitch", "objection", "nba", "spark"),
}


def test_every_key_the_cockpit_reads_is_still_there(packed: SimpleNamespace) -> None:
    out = packed.out
    for k in UI_KEYS["meta"]:
        assert k in out["meta"], k
    for k in UI_KEYS["counts"]:
        assert k in out["counts"], k
    assert "gig_case_id" in out
    m = out["metrics"]
    for k in ("per_product", "blended", "calibration", "uplift", "fairness",
              "income_acc", "excluded_features"):
        assert k in m, k
    for k in ("baseline", "auc_macro", "prec_curve"):
        assert k in m["blended"], k
    for k in ("inc_per_1000_top20", "inc_per_1000_all", "persuadable_share_top20",
              "curve", "inc_total"):
        assert k in m["uplift"], k
    for k in ("within10", "within15", "gig_within15", "median_err"):
        assert k in m["income_acc"], k
    for f in m["fairness"]:
        assert {"dim", "group", "sel_rate", "ratio", "passes"} <= set(f)
    for lead in out["leads"]:
        for k in UI_KEYS["lead"]:
            assert k in lead, (lead["id"], k)


def test_the_precision_curve_still_has_the_budgets_the_ui_pins(
        packed: SimpleNamespace) -> None:
    """``MissionControl`` opens at 2% and ``ModelTrust`` looks up 1/2/5/10/20/30%."""
    budgets = {round(p["budget"], 2) for p in packed.out["metrics"]["blended"]["prec_curve"]}
    assert {0.01, 0.02, 0.05, 0.10, 0.20, 0.30} <= budgets
    for p in packed.out["metrics"]["blended"]["prec_curve"]:
        assert {"budget", "precision", "lift", "contacts", "expected_conversions"} <= set(p)


#: The two tags a normal run may carry. `TYPICAL_EMI` is the reachable fallback below both
#: and is deliberately not in this set: a run that lands there has lost the bank rate.
_BANK_EMI_SOURCES = {EMI.EMI_SOURCE_SCHEDULE, EMI.EMI_SOURCE_BANK}


def test_the_new_lead_keys_are_all_present(packed: SimpleNamespace) -> None:
    """SM-4 fills ``rm_id`` (queued leads only); SM-5 replaces the EMI source tag."""
    seen_rm = False
    for lead in packed.out["leads"]:
        for k in ("product_menu", "negative_chips", "suppressed", "suppression_reason",
                  "contact_by", "window_days", "provenance", "rm_id", "rm_name", "rm_branch",
                  "rm_source", "emi_source", "queued", "consent_marketing", "shopper_score",
                  "probability"):
            assert k in lead, (lead["id"], k)
        if lead["suppressed"]:
            assert lead["rm_id"] is None, "a suppressed lead is never assigned an RM"
            assert lead["rm_name"] is None and lead["rm_branch"] is None
            assert lead["rm_source"] is None
        else:
            assert re.fullmatch(r"EIN-\d{6}", lead["rm_id"]), lead["rm_id"]
            assert lead["rm_name"] and lead["rm_branch"]
            assert lead["rm_source"] in (RO.SOURCE_BANK_API, RO.SOURCE_SIMULATED)
            seen_rm = True
        # SM-5's ladder: a fetched 473 schedule, else the 433 rate. Which one depends on
        # whether a pull has run on this checkout (`data/bank/pulled.json` is gitignored),
        # so the test pins the set, not the member — and never allows TYPICAL_EMI.
        assert lead["emi_source"] in _BANK_EMI_SOURCES, "SM-5 owns the 433/473 EMI"
        for item in lead["product_menu"]:
            assert item["emi_source"] in _BANK_EMI_SOURCES
            assert isinstance(item["emi"], int) and item["emi"] > 0
            assert isinstance(item["indicative_emi"], str) and item["indicative_emi"]
    assert seen_rm, "no queued lead in the export at all"


# --------------------------------------------------------------------------- #
# the platform export contract  (data/bank/SCHEMA.md)
# --------------------------------------------------------------------------- #

def test_the_fields_that_overlap_schema_md_are_spelled_the_same() -> None:
    """Where the model and the bank-enrichment contract name the same thing."""
    schema = (ROOT / "data" / "bank" / "SCHEMA.md").read_text(encoding="utf-8")
    from journeys.features import CONTRACT_COLUMNS
    from model.frame import FEATURES, JOURNEY_KEEP

    for c in CONTRACT_COLUMNS:
        assert c in schema, c
    # the model consumes five of the six verbatim; `journey_stage_reached` is a
    # string the model takes as the ordinal `journey_stage_idx` and the cockpit
    # takes as `dropoff_stage`, so the contract spelling survives in the export
    # rather than in the feature list.
    for c in CONTRACT_COLUMNS:
        assert (c in JOURNEY_KEEP) or c == "journey_stage_reached", c
    assert "journey_stage_idx" in FEATURES
    for c in ("campaign_contacts_6m", "contact_window_days", "consent_marketing", "dnd"):
        assert c in schema, c
    assert "campaign_contacts_6m" in FEATURES
    # six dwell columns, canonical spelling, no `dwell_pl`
    for p in PRODUCTS:
        assert f"dwell_{p}" in schema, p
    assert "dwell_pl" not in schema


def test_the_provenance_block_matches_the_eight_families(packed: SimpleNamespace) -> None:
    """Without ``--bank`` every family is still ``SIMULATED`` — SM-6 only kicks in
    behind the flag; SM-4/SM-5 (the roster and the EMI source) are unconditional,
    and the ``hooks`` text now says so instead of pointing at a null.
    """
    p = packed.out["provenance"]
    assert p["provenance_version"] == 1 and p["product"] == "sanket"
    assert p["mode"] == "simulated"
    assert set(p["families"]) == {"identity", "casa_behaviour", "cross_bank", "holdings",
                                  "digital", "consent", "journey", "model"}
    assert set(p["families"].values()) == {"SIMULATED"}
    assert "SM-4" in p["hooks"]["rm_id"] and "roster" in p["hooks"]["rm_id"]
    # One tag per product, not one tag: the ladder can land differently per product and a
    # single string would hide which took which step.
    assert set(p["hooks"]["emi_source"]) == set(EMI.EMI_SOURCE)
    assert set(p["hooks"]["emi_source"].values()) <= _BANK_EMI_SOURCES
    assert any("sanket_export.json" in x for x in p["hooks"]["pending"])

    r = packed.out["roster"]
    seeded = RO.load_roster(Path(__file__).resolve().parents[1] / "data")
    assert r["source"] == "SIMULATED" and r["n_rms"] >= 1 and r["n_active"] <= r["n_rms"]
    assert {rm["rm_id"] for rm in r["rms"]} == {rm.rm_id for rm in seeded.rms}


# --------------------------------------------------------------------------- #
# reproducibility
# --------------------------------------------------------------------------- #

def test_the_same_seed_gives_the_same_split(model_run: SimpleNamespace) -> None:
    from model.train import split_customers

    a = split_customers(model_run.base["cust_id"].unique(), model_run.cfg, 7)
    b = split_customers(model_run.base["cust_id"].unique(), model_run.cfg, 7)
    c = split_customers(model_run.base["cust_id"].unique(), model_run.cfg, 8)
    assert a.held == b.held and a.fit == b.fit and a.calib == b.calib
    assert a.held != c.held
    assert not (a.fit & a.calib) and not (a.fit & a.held) and not (a.calib & a.held)


def test_the_same_seed_gives_the_same_scores(model_run: SimpleNamespace) -> None:
    from model.train import fit_ranker

    again = fit_ranker(model_run.stacked, model_run.split, model_run.cfg)
    np.testing.assert_allclose(again.matrix(model_run.stacked), model_run.P, rtol=0, atol=1e-12)


def test_the_stacked_frame_is_in_product_block_order(model_run: SimpleNamespace) -> None:
    """``Ranker.matrix`` reshapes on this; it asserts rather than assumes it."""
    st = model_run.stacked
    n = len(st) // len(PRODUCTS)
    assert list(st["product"].astype(str)[::n]) == list(PRODUCTS)
    np.testing.assert_array_equal(st["_row"].to_numpy(),
                                  np.tile(np.arange(n), len(PRODUCTS)))
