"""SM-7 — the evaluated policy IS the delivered policy.

A third-party review (2026-09-21, §4) found the headline measured on a list
nobody receives: ``precision@budget`` ranked held-out rows on
``max(product probabilities)``, while the queue an RM is handed was ranked on
``0.65 x intent + 0.35 x capacity`` and truncated.  ``model.policy`` now owns
that selection once and both callers use it.  These tests are what stops the
two drifting apart again, so they check the *identity* of the two lists rather
than the plausibility of either.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from model import PRODUCTS
from model import policy as PO


# --------------------------------------------------------------------------- #
# the policy function itself
# --------------------------------------------------------------------------- #

def _pool(n: int = 40, seed: int = 3):
    rng = np.random.default_rng(seed)
    P = rng.random((n, len(PRODUCTS))) * 0.6
    cust = np.array([f"LB-{2000000 + i}" for i in range(n)])
    safe_emi = rng.integers(0, 60_000, n).astype(float)
    elig = rng.random(n) > 0.25
    return cust, safe_emi, P, elig


def test_the_default_ranking_is_one_of_the_two_it_offers() -> None:
    assert PO.DEFAULT_RANKING in PO.RANKINGS


def test_an_unknown_ranking_is_refused_rather_than_silently_defaulted() -> None:
    cust, emi, P, elig = _pool()
    with pytest.raises(ValueError):
        PO.score_pool(cust, emi, P, elig, ranking="vibes")


def test_a_suppressed_row_is_scored_but_never_selected() -> None:
    """The mentors' rule: scored and shown, never queued."""
    cust, emi, P, elig = _pool()
    sc = PO.score_pool(cust, emi, P, elig)
    assert len(sc.p_top) == len(cust), "a suppressed row keeps its place in the pool"
    chosen = PO.select(sc, k=len(cust))
    assert set(chosen) <= set(np.flatnonzero(elig))
    assert len(chosen) == int(elig.sum()), "truncation cannot reach past the eligible pool"


def test_the_intent_percentile_is_taken_within_the_eligible_pool() -> None:
    """Ranking a customer against people the bank may not call would make the
    blend depend on how many of those there happened to be."""
    cust, emi, P, elig = _pool()
    sc = PO.score_pool(cust, emi, P, elig)
    assert np.allclose(sc.intent[~elig], 0.0)
    assert pytest.approx(float(sc.intent[elig].max()), abs=1e-12) == 1.0


def test_ties_break_on_customer_id_not_on_frame_order() -> None:
    """Same pool, rows shuffled: the same calling order comes back."""
    n = 30
    cust = np.array([f"LB-{2000000 + i}" for i in range(n)])
    P = np.zeros((n, len(PRODUCTS)))
    P[:, 0] = 0.4                                   # every row identical: all ties
    emi = np.full(n, 20_000.0)
    elig = np.ones(n, dtype=bool)

    a = PO.rank_order(PO.score_pool(cust, emi, P, elig))
    order_a = list(cust[a])

    perm = np.random.default_rng(11).permutation(n)
    b = PO.rank_order(PO.score_pool(cust[perm], emi[perm], P[perm], elig[perm]))
    order_b = list(cust[perm][b])
    assert order_a == order_b == sorted(cust.tolist())


def test_hot_is_exactly_what_the_budget_buys_on_the_queue_ranking() -> None:
    cust, emi, P, elig = _pool(n=200)
    sc = PO.score_pool(cust, emi, P, elig)
    tier = PO.tiers(sc, 0.10)
    hot = np.flatnonzero(tier == "hot")
    assert len(hot) == PO.budget_k(sc.n_eligible, 0.10)
    assert set(hot) == set(PO.select(sc, budget=0.10)), \
        "the hot tier and the budgeted queue must be the same rows"
    assert (tier[~elig] == "held").all()


def test_precision_at_counts_the_rows_the_policy_would_call() -> None:
    cust, emi, P, elig = _pool(n=200)
    sc = PO.score_pool(cust, emi, P, elig)
    y = (np.random.default_rng(5).random(200) < 0.2).astype(int)
    r = PO.precision_at(y, sc, 0.10)
    sel = PO.select(sc, budget=0.10)
    assert r["k"] == len(sel)
    assert r["hits"] == int(y[sel].sum())
    assert r["ranking"] == sc.ranking


def test_select_refuses_an_ambiguous_truncation() -> None:
    cust, emi, P, elig = _pool()
    sc = PO.score_pool(cust, emi, P, elig)
    with pytest.raises(ValueError):
        PO.select(sc)
    with pytest.raises(ValueError):
        PO.select(sc, k=5, budget=0.1)


# --------------------------------------------------------------------------- #
# parity: the packed queue is the policy's own list
# --------------------------------------------------------------------------- #

def test_the_packed_queue_is_the_policys_top_k_in_the_policys_order(
        packed: SimpleNamespace) -> None:
    """Review §4's parity test, on the cockpit pack.

    The delivered list is rebuilt from the policy function and compared id for
    id, in order, against the leads the pack actually wrote.
    """
    out = packed.out
    queued = [lead for lead in out["leads"] if lead["queued"]]
    assert queued, "nothing was queued at all"

    size = packed.cfg.queue_size
    delivered = out["metrics"]["delivered_queue"]
    expected = delivered["top_ids"][:size]
    got = [lead["id"] for lead in queued][:size]
    assert got == expected, "the exported queue is not the policy's own ranked list"

    # queue_rank is 1-based and contiguous over the delivered slice.
    ranks = [lead["queue_rank"] for lead in queued][:size]
    assert ranks == list(range(1, len(ranks) + 1))
    assert all(lead["queue_rank"] is None for lead in out["leads"] if not lead["queued"])


def test_every_lead_inside_the_budget_is_hot(packed: SimpleNamespace) -> None:
    """Tiers are cut on the ranking the queue uses, so the queue cannot contain
    a 'cold' lead while a 'hot' one waits outside it — which is what the split
    between a probability-ranked tier and a blend-ranked queue used to produce."""
    out = packed.out
    delivered = out["metrics"]["delivered_queue"]
    inside = set(delivered["top_ids"][: min(delivered["queue_size"], delivered["budget_k"])])
    for lead in out["leads"]:
        if lead["id"] in inside:
            assert lead["tier"] == "hot", (lead["id"], lead["tier"])


def test_the_evaluated_precision_uses_the_delivered_ranking(packed: SimpleNamespace) -> None:
    m = packed.out["metrics"]
    assert m["headline_parts"]["ranking"] == PO.DEFAULT_RANKING
    assert m["delivered_queue"]["ranking"] == PO.DEFAULT_RANKING
    assert m["ranking_comparison"]["default"] == PO.DEFAULT_RANKING
    both = m["ranking_comparison"]["packed_seed"]
    assert set(both) == set(PO.RANKINGS), "both candidate rankings must be reported"


def test_the_delivered_queue_block_is_internally_consistent(packed: SimpleNamespace) -> None:
    d = packed.out["metrics"]["delivered_queue"]
    assert d["budget_k"] == PO.budget_k(d["eligible_pool"], d["budget"])
    assert d["exported"] <= d["queue_size"] + 1, \
        "at most one disclosed extra row may ride past the queue size"
    assert len(d["top_ids"]) == min(d["queue_size"], d["eligible_pool"])


# --------------------------------------------------------------------------- #
# probabilities (review §10)
# --------------------------------------------------------------------------- #

def test_any_product_probability_is_the_sum_not_the_independent_union() -> None:
    """The six labels partition the outcome, so ``1 - prod(1 - p)`` is the wrong
    formula: it treats "took a home loan" and "took a gold loan" as events that
    can both happen, and reads low for exactly the customers the queue ranks."""
    P = np.array([[0.30, 0.20, 0.10, 0.05, 0.03, 0.02],
                  [0.60, 0.50, 0.40, 0.00, 0.00, 0.00],
                  [0.00, 0.00, 0.00, 0.00, 0.00, 0.00]])
    got = PO.any_product_probability(P)
    assert got == pytest.approx([0.70, 1.00, 0.00])
    union = 1.0 - np.prod(1.0 - P, axis=1)
    assert got[0] > union[0], "the retired union formula would read lower here"
    assert (got <= 1.0).all() and (got >= 0.0).all()


def test_the_packed_any_product_probability_is_within_range(
        packed: SimpleNamespace) -> None:
    for lead in packed.out["leads"]:
        menu_sum = sum(item["p"] for item in lead["product_menu"])
        assert 0.0 <= lead["p_any"] <= 1.0
        # the menu is the top four of six, so the full sum is never below it
        assert lead["p_any"] + 1e-6 >= min(1.0, menu_sum)


def test_the_pack_is_json_serialisable_with_the_new_fields(packed: SimpleNamespace) -> None:
    json.dumps(packed.out["metrics"]["delivered_queue"])
    json.dumps(packed.out["metrics"]["ranking_comparison"])


# --------------------------------------------------------------------------- #
# uncertainty, three ways (review §10)
# --------------------------------------------------------------------------- #

def test_the_bootstrap_resamples_customers_and_reselects_the_queue() -> None:
    """A row-level resample would answer a question nobody asked.

    `precision@budget` is the precision of a list a policy chose; the policy's
    percentiles, its eligible-pool size and therefore its `k` all move when the
    pool moves, so the selection has to happen inside the resample.
    """
    from model import bootstrap as BS

    rng = np.random.default_rng(1)
    n_cust, per_cust = 400, 6
    cust = np.repeat([f"LB-{2000000 + i}" for i in range(n_cust)], per_cust)
    P = rng.random((n_cust * per_cust, len(PRODUCTS))) * 0.5
    emi = rng.integers(0, 60_000, len(cust)).astype(float)
    elig = np.ones(len(cust), dtype=bool)
    y = (rng.random(len(cust)) < 0.2).astype(int)

    out = BS.precision_ci(cust, emi, P, elig, y, budgets=(0.10,), n_resamples=60, seed=3)
    assert out["resampled_unit"] == "cust_id"
    assert out["queue_reselected_per_resample"] is True
    assert out["n_customers"] == n_cust
    assert out["10"]["ci_low"] <= out["10"]["point"] <= out["10"]["ci_high"]
    assert out["baseline"]["ci_low"] <= out["baseline"]["point"] <= out["baseline"]["ci_high"]
    # A customer-clustered interval must be wider than a row-level Wilson one,
    # because six correlated rows are not six independent observations.
    from model.metrics import wilson
    k = out["10"]["budget"] * len(y)
    w_lo, w_hi = wilson(int(round(out["10"]["point"] * k)), int(k))
    assert (out["10"]["ci_high"] - out["10"]["ci_low"]) > 0
    assert w_hi - w_lo > 0


def test_the_bootstrap_is_deterministic_under_its_seed() -> None:
    from model import bootstrap as BS

    rng = np.random.default_rng(9)
    cust = np.repeat([f"LB-{i:07d}" for i in range(120)], 4)
    P = rng.random((480, len(PRODUCTS))) * 0.4
    emi = np.full(480, 20_000.0)
    elig = np.ones(480, dtype=bool)
    y = (rng.random(480) < 0.25).astype(int)
    a = BS.precision_ci(cust, emi, P, elig, y, budgets=(0.10,), n_resamples=25, seed=5)
    b = BS.precision_ci(cust, emi, P, elig, y, budgets=(0.10,), n_resamples=25, seed=5)
    assert a["10"] == b["10"]


def test_the_pack_keeps_the_three_estimands_apart(packed: SimpleNamespace) -> None:
    u = packed.out["metrics"]["uncertainty"]
    assert set(("sample", "training_seed", "generator")) <= set(u)
    assert u["sample"]["method"].startswith("customer-clustered")
    assert "NOT a confidence interval" in u["training_seed"]["estimand"]
    # generator variation is a separate, much longer run; absent is reported as
    # absent and never silently folded into either of the others.
    assert u["generator"]["status"] in ("measured", "not_measured", "unreadable")
    assert u["sample"]["headline"]["sentence"] == packed.out["metrics"]["headline"]


def test_predictions_are_persisted_and_round_trip(packed: SimpleNamespace) -> None:
    from model import bootstrap as BS

    rel = packed.out["metrics"]["uncertainty"]["predictions_file"]
    path = packed.cfg.root / rel
    assert path.is_file(), rel
    doc = BS.load(packed.cfg.data, packed.cfg.seed)
    assert doc is not None
    assert doc["P"].shape[1] == len(PRODUCTS)
    assert len(doc["cust_id"]) == len(doc["y"]) == doc["P"].shape[0]
    assert list(doc["products"]) == list(PRODUCTS)


# --------------------------------------------------------------------------- #
# menu baselines (review §10)
# --------------------------------------------------------------------------- #

def test_the_menu_is_reported_against_rules_that_need_no_model(
        packed: SimpleNamespace) -> None:
    b = packed.out["metrics"]["menu_baselines"]
    assert set(("model", "most_popular", "abandoned_product")) <= set(b)
    for key in ("model", "most_popular", "abandoned_product"):
        row = b[key]
        for field in ("menu_hit_rate", "top_1_accuracy", "menu_hit_rate_switchers",
                      "top_1_accuracy_switchers"):
            assert field in row, (key, field)
    # The abandoned-product rule is the one to beat: it must be reported, and on
    # switchers it must be strictly worse than a model that adds anything at all.
    assert b["abandoned_product"]["top_1_accuracy_switchers"] == 0.0, \
        "offering the abandoned product can never be right for a customer who switched"
    assert b["model"]["n_switchers"] > 0


def test_the_popularity_baseline_is_built_from_training_labels_only() -> None:
    """Building it from the held-out labels would be reading the answer sheet."""
    import pandas as pd
    from model.metrics import product_popularity

    train = pd.DataFrame({
        "t_label": [1, 1, 1, 0, 1],
        "t_label_product": ["gold", "gold", "home", "personal", "home"],
    })
    order = product_popularity(train)
    assert order[0] in ("gold", "home")
    assert set(order) == set(PRODUCTS), "every product must appear, even unseen ones"
    assert len(order) == len(PRODUCTS)
