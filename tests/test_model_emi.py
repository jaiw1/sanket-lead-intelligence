"""SM-5 — the fetched 473 schedule, the 433 rate through the annuity formula, and the
fallback below both."""

from __future__ import annotations

import json

import pytest

from model import PRODUCTS
from model import emi as E


# --------------------------------------------------------------------------- #
# the formula on known values
# --------------------------------------------------------------------------- #

def test_annuity_emi_matches_the_textbook_value() -> None:
    """P=100,000, 12% p.a., 12 months -> 8,884.88 (a standard worked example)."""
    assert E.annuity_emi(100_000, 12.0, 12) == pytest.approx(8_884.88, abs=0.05)


def test_annuity_emi_matches_a_second_known_value() -> None:
    """P=500,000, 9% p.a., 60 months -> 10,379.18 (reducing-balance annuity)."""
    assert E.annuity_emi(500_000, 9.0, 60) == pytest.approx(10_379.18, abs=0.05)


def test_annuity_emi_zero_rate_is_a_plain_split() -> None:
    assert E.annuity_emi(120_000, 0.0, 12) == pytest.approx(10_000.0)


def test_annuity_emi_rejects_a_non_positive_tenor() -> None:
    with pytest.raises(ValueError):
        E.annuity_emi(100_000, 10.0, 0)


def test_annuity_emi_of_a_non_positive_principal_is_zero() -> None:
    assert E.annuity_emi(0, 10.0, 12) == 0.0
    assert E.annuity_emi(-5, 10.0, 12) == 0.0


def test_amortisation_schedule_fully_amortises() -> None:
    """The last row closes at (approximately) zero, and every row's EMI matches."""
    rows = E.amortisation_schedule(300_000, 12.75, 36)
    assert len(rows) == 36
    assert rows[-1]["closing"] == pytest.approx(0.0, abs=1.0)
    emis = {r["emi"] for r in rows}
    assert len(emis) == 1  # level EMI, only the interest/principal split moves
    total_principal = sum(r["principal"] for r in rows)
    assert total_principal == pytest.approx(300_000, rel=1e-3)


def test_the_sandbox_rate_sanity_checks_against_the_captured_loaninfo_blob() -> None:
    """The captured 433 blob's own `loanInfo` (an existing loan) is in the same
    ballpark as our formula at its rate — the two don't have to match exactly
    (that loan is not a fresh 240-month annuity, `amtAlreadyDisb` says so), but
    a formula that was wrong by an order of magnitude would fail this loosely
    enough to still be a useful guard.
    """
    computed = E.annuity_emi(E.LOAN_INFO["loan_amt"], E.LOAN_INFO["net_int_rate_pa"],
                             int(E.LOAN_INFO["loan_period_months"]))
    claimed = E.LOAN_INFO["emi_amount"]
    assert computed == pytest.approx(claimed, rel=0.10)


# --------------------------------------------------------------------------- #
# emi_source tags
# --------------------------------------------------------------------------- #

def test_every_product_has_a_reference_emi_from_one_of_the_two_bank_sources() -> None:
    """Which of the two depends on whether a pull has run on this checkout —
    `data/bank/pulled.json` is gitignored, so a fresh clone takes the 433 path and a
    machine that has run the batch takes the 473 one. Both are bank sources and the tag
    says which; what is never acceptable is falling to TYPICAL_EMI on a normal run."""
    for p in PRODUCTS:
        assert E.REFERENCE_EMI[p] > 0
        assert E.EMI_SOURCE[p] in (E.EMI_SOURCE_SCHEDULE, E.EMI_SOURCE_BANK)
        assert E.reference_emi(p) == E.REFERENCE_EMI[p]


def test_every_product_prices_off_the_one_uniform_rate() -> None:
    """"if the blob has one rate, use it for all and say so" — every product's
    reference EMI is consistent with the SAME annual rate on its own reference
    ticket; there is no per-product rate variation in this sandbox."""
    for p in PRODUCTS:
        expected = round(E.annuity_emi(E.REFERENCE_PRINCIPAL[p], E.UNIFORM_RATE_PA,
                                       E.REFERENCE_TENOR_MONTHS[p]), -2)
        assert E.REFERENCE_EMI[p] == int(expected)


def test_the_three_sources_are_three_distinct_honest_strings() -> None:
    tags = {E.EMI_SOURCE_SCHEDULE, E.EMI_SOURCE_BANK, E.EMI_SOURCE_TYPICAL}
    assert len(tags) == 3
    assert E.EMI_SOURCE_SCHEDULE == "BANK_API_473_schedule"
    assert E.EMI_SOURCE_BANK == "BANK_API_433_sandbox_fixture"
    assert E.EMI_SOURCE_TYPICAL == "TYPICAL_EMI"


def test_the_typical_emi_fallback_is_retained_and_reachable(monkeypatch) -> None:
    """The fallback is not dead code: break the reference tenor for one product
    (an invalid tenor forces the annuity formula to raise) and the source tag
    flips to TYPICAL_EMI without the caller ever seeing an exception.
    """
    monkeypatch.setitem(E.REFERENCE_TENOR_MONTHS, "gold", 0)  # -> ValueError inside annuity_emi
    value, source = E._reference_emi_and_source("gold")
    assert source == E.EMI_SOURCE_TYPICAL
    assert value == E.TYPICAL_EMI["gold"]


def test_indicative_label_is_a_string_not_a_number() -> None:
    for p in PRODUCTS:
        label = E.indicative_label(p)
        assert isinstance(label, str) and label
        assert str(E.REFERENCE_PRINCIPAL[p]) in label.replace(",", "")


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def test_sandbox_fixture_flag_is_set() -> None:
    assert E.SANDBOX_FIXTURE is True


def test_the_derived_schedule_tag_never_claims_bank_api() -> None:
    """When no 473 schedule was fetched the rows are ours, and the tag has to say so."""
    assert E.SCHEDULE_SOURCE_DERIVED == "DERIVED_FROM_433"
    assert "BANK_API" not in E.SCHEDULE_SOURCE_DERIVED


# --------------------------------------------------------------------------- #
# API 473 — the fetched schedule
# --------------------------------------------------------------------------- #

#: The bank's own answer for SANKET's personal-loan reference ticket (₹300,000 over 36
#: months at 12.75% p.a.), captured from the live sandbox on 2026-09-17. Three rows of the
#: thirty-six, enough to carry the shape, the split and the closing balance.
_LIVE_473_HEAD = {
    "lamodRepaymentLL": [{"flowAmt": {"amountValue": "10072.10", "currencyCode": "INR"},
                          "noOfInstalments": "36", "Freq": "M"}],
    "oamortLL": [
        {"amortStruct": {"instlAmt": {"amountValue": "10072.10", "currencyCode": "INR"},
                         "intAmt": {"amountValue": "3187.50", "currencyCode": "INR"},
                         "princAmt": {"amountValue": "6884.60", "currencyCode": "INR"},
                         "princOutStanding": {"amountValue": "293115.40", "currencyCode": "INR"}}},
        {"amortStruct": {"instlAmt": {"amountValue": "10072.10", "currencyCode": "INR"},
                         "intAmt": {"amountValue": "3114.35", "currencyCode": "INR"},
                         "princAmt": {"amountValue": "6957.75", "currencyCode": "INR"},
                         "princOutStanding": {"amountValue": "286157.65", "currencyCode": "INR"}}},
    ],
}


def _as_473(product: str) -> dict:
    """A full-length schedule in the bank's own `oamortLL` shape.

    `_LIVE_473_HEAD` is the bank's real answer but only its first two rows, and
    `bank_schedule` matches on the row *count* — so a two-row fixture is a two-month loan
    and rightly matches nothing. This re-renders the whole ticket in the same shape. The
    numbers are `amortisation_schedule`'s, which the last test in this file proves are the
    bank's numbers to the paise; the shape is copied from the captured response verbatim.
    """
    def amt(v: float) -> dict:
        return {"amountValue": f"{v:.2f}", "currencyCode": "INR"}

    rows = E.amortisation_schedule(E.REFERENCE_PRINCIPAL[product], E.UNIFORM_RATE_PA,
                                   E.REFERENCE_TENOR_MONTHS[product])
    return {"oamortLL": [{"amortStruct": {"instlAmt": amt(r["emi"]), "intAmt": amt(r["interest"]),
                                          "princAmt": amt(r["principal"]),
                                          "princOutStanding": amt(r["closing"])},
                          "Key": {"serial_num": str(r["n"])}} for r in rows]}


def test_parse_schedule_reads_the_live_473_shape() -> None:
    parsed = E.parse_schedule(_LIVE_473_HEAD)
    assert parsed is not None
    assert parsed["principal"] == pytest.approx(300_000.0)
    assert parsed["emi"] == pytest.approx(10_072.10)
    assert parsed["rate_pa"] == pytest.approx(12.75, abs=1e-6)
    assert parsed["rows"][0] == dict(n=1, opening=300_000.0, emi=10_072.10, interest=3_187.50,
                                     principal=6_884.60, closing=293_115.40)


def test_parse_schedule_accepts_both_envelopes_the_sandbox_and_the_sheet_use() -> None:
    """Live it arrives top-level; the spreadsheet contract nests it under `result`, and the
    raw response wraps it in `loanModellingSchOutputVO`. All three, one parser."""
    direct = E.parse_schedule(_LIVE_473_HEAD)
    wrapped = E.parse_schedule({"loanModellingSchOutputVO": _LIVE_473_HEAD})
    nested = E.parse_schedule({"result": _LIVE_473_HEAD})
    assert direct == wrapped == nested


def test_a_record_with_no_amortisation_rows_parses_to_nothing() -> None:
    assert E.parse_schedule({"message": "Data not found"}) is None
    assert E.parse_schedule({"loanModellingSchOutputVO": {"oamortLL": []}}) is None
    assert E.parse_schedule("not a dict") is None


def test_a_missing_pull_leaves_no_schedules_and_falls_to_the_433_path(tmp_path) -> None:
    """The gitignored file is absent on a fresh clone. That must be a fallback, not a
    crash, and it must land on the 433 tag rather than on TYPICAL_EMI."""
    try:
        sources = E.refresh(tmp_path / "nothing-here.json")
        assert E.BANK_SCHEDULES == {}
        assert set(sources.values()) == {E.EMI_SOURCE_BANK}
        for p in PRODUCTS:
            rows, tag = E.schedule_for(p)
            assert tag == E.SCHEDULE_SOURCE_DERIVED
            assert len(rows) == E.REFERENCE_TENOR_MONTHS[p]
        assert "API 433" in E.indicative_label("personal")
    finally:
        E.refresh()


def test_a_fetched_schedule_wins_and_is_tagged_473(tmp_path) -> None:
    path = tmp_path / "pulled.json"
    path.write_text(json.dumps({"apis": {"473": {"provenance": "BANK_API",
                                                 "records": [_as_473("personal")]}}}),
                    encoding="utf-8")
    try:
        E.refresh(path)
        assert E.EMI_SOURCE["personal"] == E.EMI_SOURCE_SCHEDULE
        assert E.REFERENCE_EMI["personal"] == 10_100  # the same ₹100 rounding as ever
        rows, tag = E.schedule_for("personal")
        assert tag == E.SCHEDULE_SOURCE_BANK and len(rows) == 36
        assert "API 473" in E.indicative_label("personal")
        # Every other product had no fetched ticket, so each falls back on its own.
        assert E.EMI_SOURCE["home"] == E.EMI_SOURCE_BANK
    finally:
        E.refresh()


def test_a_schedule_priced_at_another_rate_is_not_used(tmp_path) -> None:
    """A ladder entry that drifts must not quietly reprice a product off someone else's
    ticket: the principal and tenor match, the rate does not, so it is ignored."""
    wrong = _as_473("personal")
    wrong["oamortLL"][0]["amortStruct"]["intAmt"]["amountValue"] = "2000.00"
    path = tmp_path / "pulled.json"
    path.write_text(json.dumps({"apis": {"473": {"provenance": "BANK_API",
                                                 "records": [wrong]}}}), encoding="utf-8")
    try:
        E.refresh(path)
        assert E.bank_schedule("personal") is None
        assert E.EMI_SOURCE["personal"] == E.EMI_SOURCE_BANK
    finally:
        E.refresh()


def test_a_not_collected_473_is_not_read_as_bank_data(tmp_path) -> None:
    path = tmp_path / "pulled.json"
    path.write_text(json.dumps({"apis": {"473": {"provenance": "NOT_COLLECTED",
                                                 "records": [_as_473("personal")]}}}),
                    encoding="utf-8")
    try:
        E.refresh(path)
        assert E.BANK_SCHEDULES == {}
    finally:
        E.refresh()


def test_the_banks_own_engine_agrees_with_our_annuity_formula() -> None:
    """The reason adopting 473 moved no number downstream. All six reference tickets were
    fetched live on 2026-09-17; each level instalment matches `annuity_emi` to the paise.
    If the bank's engine ever disagrees, this is where it shows up — not in a lead's EMI.
    """
    captured = {"personal": 10_072.10, "gold": 13_380.00, "auto": 13_575.18,
                "education": 9_028.16, "home": 34_614.35, "lap": 24_976.74}
    for product, bank_emi in captured.items():
        ours = E.annuity_emi(E.REFERENCE_PRINCIPAL[product], E.UNIFORM_RATE_PA,
                             E.REFERENCE_TENOR_MONTHS[product])
        assert ours == pytest.approx(bank_emi, abs=0.01), product
