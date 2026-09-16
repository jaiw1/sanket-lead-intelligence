"""SM-5 — the annuity EMI formula, the 433 sandbox rate, and the fallback."""

from __future__ import annotations

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

def test_every_product_has_a_reference_emi_tagged_bank_api() -> None:
    for p in PRODUCTS:
        assert E.REFERENCE_EMI[p] > 0
        assert E.EMI_SOURCE[p] == E.EMI_SOURCE_BANK
        assert E.reference_emi(p) == E.REFERENCE_EMI[p]


def test_every_product_prices_off_the_one_uniform_rate() -> None:
    """"if the blob has one rate, use it for all and say so" — every product's
    reference EMI is consistent with the SAME annual rate on its own reference
    ticket; there is no per-product rate variation in this sandbox."""
    for p in PRODUCTS:
        expected = round(E.annuity_emi(E.REFERENCE_PRINCIPAL[p], E.UNIFORM_RATE_PA,
                                       E.REFERENCE_TENOR_MONTHS[p]), -2)
        assert E.REFERENCE_EMI[p] == int(expected)


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


def test_schedule_source_is_derived_not_bank_api() -> None:
    """API 473 never answered in this sandbox — the schedule is DERIVED, and the
    tag says so rather than claiming BANK_API for something we never received.
    """
    assert E.SCHEDULE_SOURCE_DERIVED == "DERIVED_FROM_433"
    assert "BANK_API" not in E.SCHEDULE_SOURCE_DERIVED
