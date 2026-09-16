"""Smoke test: python3 data/bank/check_fixture.py  -> exits non-zero if the fixture is unusable."""
import json, pathlib
REQUIRED = {"cust_id", "cif_id", "credits_med_6m", "salary_credit_day", "holdings", "narration_samples",
            "consent_marketing", "dnd", "segment", "occupation", "income_band", "card_rate_pa", "_provenance"}
doc = json.loads((pathlib.Path(__file__).parent / "fixture.json").read_text())
rows = doc["customers"]
assert rows and doc["_meta"]["mode"] == "fixture", "fixture.json is empty or not marked as a fixture"
assert all(REQUIRED <= set(r) for r in rows), f"missing required keys: {REQUIRED - set(rows[0])}"
assert all(r["_provenance"] == "FIXTURE" for r in rows), "every record must be tagged FIXTURE"
assert any(r["ext_emi_narration"] for r in rows) and any(r["ext_salary_narration"] for r in rows), \
    "cross-bank EMI and salary-elsewhere narrations (APIs 595/739) must both be present"
print(f"OK  {len(rows)} fixture customers, {len(rows[0])} columns, cross-bank narrations present, all tagged FIXTURE")
