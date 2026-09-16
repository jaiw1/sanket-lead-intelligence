"""Every pre-registered SK-* quantity, computed once and named the way
``validation/criteria.yaml`` names it.

Why the names matter
--------------------
``validation/criteria.yaml`` was committed before any of these numbers existed;
each criterion carries a ``metric:`` string.  This module emits a dict keyed by
exactly those strings (:func:`registered`), so a runner reads a value instead of
re-deriving one — which is the only way the report and the model can be made to
agree without either being tuned toward the other.

Nothing here is allowed to move a threshold.  :func:`bands` compares the value
to the registered band and writes ``pass`` or ``fail``; a ``fail`` is packed into
the JSON beside everything else.  The failure is the finding.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import PRODUCTS, WINDOW_DAYS

Z95 = 1.959963984540054


# --------------------------------------------------------------------------- #
# small statistics
# --------------------------------------------------------------------------- #

def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval — the right one for a proportion near 0 or 1."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo, hi = (c - h) / d, (c + h) / d
    # floating point can put the bound a hair the wrong side of 0 or of p itself
    return (min(max(lo, 0.0), p), max(min(hi, 1.0), p))


def auc_ci(y: np.ndarray, s: np.ndarray) -> tuple[float, float, float]:
    """AUC with a Hanley-McNeil standard-error interval."""
    y = np.asarray(y).astype(int)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return (float("nan"),) * 3
    a = float(roc_auc_score(y, s))
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt(max(a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a), 0.0) / (n1 * n0))
    return a, max(0.0, a - Z95 * se), min(1.0, a + Z95 * se)


def precision_at(y: np.ndarray, score: np.ndarray, budget: float) -> dict:
    """Precision among the top ``budget`` of the population, with a Wilson CI."""
    n = len(y)
    k = max(1, int(round(n * budget)))
    top = np.argsort(-score, kind="stable")[:k]
    hits = int(y[top].sum())
    lo, hi = wilson(hits, k)
    return dict(budget=round(budget, 4), k=k, hits=hits,
                precision=hits / k, ci_low=lo, ci_high=hi)


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error over equal-count bins.

    Equal-count rather than equal-width: the score distribution here is heavily
    massed near zero, and equal-width bins would put 95% of the population in one
    bucket and call the result well calibrated.
    """
    n = len(p)
    if n == 0:
        return float("nan")
    order = np.argsort(p, kind="stable")
    out = 0.0
    for chunk in np.array_split(order, min(bins, n)):
        if len(chunk) == 0:
            continue
        out += len(chunk) / n * abs(float(p[chunk].mean()) - float(y[chunk].mean()))
    return out


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    """The calibration curve the cockpit plots: predicted vs observed, by decile."""
    order = np.argsort(p, kind="stable")
    out = []
    for chunk in np.array_split(order, bins):
        if len(chunk) == 0:
            continue
        out.append(dict(pred=round(float(p[chunk].mean()), 4),
                        obs=round(float(y[chunk].mean()), 4), n=int(len(chunk))))
    return out


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two score distributions."""
    qs = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(qs) < 3:
        return 0.0
    qs[0], qs[-1] = -np.inf, np.inf
    e = np.histogram(expected, bins=qs)[0] / max(len(expected), 1)
    a = np.histogram(actual, bins=qs)[0] / max(len(actual), 1)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


def measured(value: float, lo: float | None = None, hi: float | None = None,
             n: int | None = None, method: str = "wilson") -> dict:
    """``{value, ci_low, ci_high, n, method}`` — the shape ``app/src/lib/pack.js``
    unwraps, so a number reaches a screen with its interval attached instead of
    arriving bare and being rendered as if it were exact."""
    return dict(value=value, ci_low=lo, ci_high=hi, n=n,
                method=method if lo is not None else None)


def spread(values: list[float]) -> dict:
    """Mean, normal-approximation CI and the percentile interval SK-21 registers."""
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if len(v) == 0:
        return dict(mean=float("nan"), n=0)
    sd = float(v.std(ddof=1)) if len(v) > 1 else 0.0
    half = Z95 * sd / math.sqrt(len(v)) if len(v) > 1 else 0.0
    lo, hi = (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) if len(v) > 1 \
        else (float(v[0]), float(v[0]))
    return dict(mean=float(v.mean()), sd=sd, n=int(len(v)),
                ci_low=float(v.mean()) - half, ci_high=float(v.mean()) + half,
                pct_low=lo, pct_high=hi, min=float(v.min()), max=float(v.max()),
                pct_width_pp=100.0 * (hi - lo))


# --------------------------------------------------------------------------- #
# the model-facing quantities
# --------------------------------------------------------------------------- #

def product_index(labels: np.ndarray) -> np.ndarray:
    """Product name -> column index; -1 for the empty string (a negative row)."""
    idx = {p: i for i, p in enumerate(PRODUCTS)}
    return np.array([idx.get(x, -1) for x in labels], dtype=np.int16)


def menu(P: np.ndarray, k: int) -> np.ndarray:
    """``(n, k)`` product indices, best first."""
    return np.argsort(-P, axis=1, kind="stable")[:, :k]


def menu_metrics(P: np.ndarray, base: pd.DataFrame, k: int) -> dict:
    """SK-13 / SK-14, plus the two sub-readings that keep them honest.

    The drop-off anchor does most of the work: 71% of positives take the product
    they walked away from, so "offer them what they abandoned" is already a
    strong top-1 rule.  Reporting the menu against that rule, and separately on
    the positives who *switched* product, is the difference between a metric and
    a claim.
    """
    y = base["t_label"].to_numpy().astype(bool)
    li = product_index(base["t_label_product"].fillna("").to_numpy())
    di = product_index(base["dropoff_product"].astype(str).to_numpy())
    m = menu(P, k)
    hit = (m == li[:, None]).any(axis=1)
    top1 = m[:, 0] == li
    switched = y & (li != di)
    n = int(y.sum())
    return dict(
        menu_of_4_hit_rate=float(hit[y].mean()) if n else float("nan"),
        menu_of_4_hit_rate_ci=wilson(int(hit[y].sum()), n),
        top_1_product_accuracy=float(top1[y].mean()) if n else float("nan"),
        top_1_product_accuracy_ci=wilson(int(top1[y].sum()), n),
        dropoff_anchor_top_1_accuracy=float((di == li)[y].mean()) if n else float("nan"),
        menu_hit_rate_when_product_changed=(float(hit[switched].mean())
                                            if switched.any() else float("nan")),
        top_1_accuracy_when_product_changed=(float(top1[switched].mean())
                                             if switched.any() else float("nan")),
        n_positives=n, n_switched=int(switched.sum()), k=k,
    )


def window_respect(P: np.ndarray, base: pd.DataFrame, order: np.ndarray, k: int) -> dict:
    """SK-04, as registered.

    Of the held-out rows inside the contact budget that *did* disburse, the share
    whose disbursement landed inside the window of the product **the model
    offered**.  Offering a one-day product to someone who took a fortnight to
    close counts against the model even though the disbursement was real — which
    is the point: the queue's SLA is a promise about timing.
    """
    sel = order[:k]
    days = base["t_days_to_disbursement"].to_numpy(dtype=float)[sel]
    offered = menu(P, 1)[sel, 0]
    win = np.array([WINDOW_DAYS[p] for p in PRODUCTS], dtype=float)[offered]
    done = np.isfinite(days)
    if not done.any():
        return dict(window_respect_rate=float("nan"), n=0)
    ok = days[done] <= win[done]
    return dict(window_respect_rate=float(ok.mean()), n=int(done.sum()),
                window_respect_ci=wilson(int(ok.sum()), int(done.sum())),
                median_days_to_disbursement=float(np.median(days[done])))


def per_product(P: np.ndarray, base: pd.DataFrame, budget: float) -> dict:
    """SK-08 / SK-12: AUC, ECE and precision@budget for each of the six."""
    out = {}
    for i, p in enumerate(PRODUCTS):
        y = base[f"label_product_{p}"].to_numpy().astype(int)
        a, lo, hi = auc_ci(y, P[:, i])
        out[p] = dict(auc=round(a, 4),
                      auc_ci=measured(round(a, 4), round(lo, 4), round(hi, 4),
                                      int(len(y)), "hanley-mcneil"),
                      n_pos_test=int(y.sum()), ece=round(ece(P[:, i], y), 5),
                      precision_at_budget=round(precision_at(y, P[:, i], budget)["precision"], 4))
    return out


def fairness_table(frame: pd.DataFrame, selected: np.ndarray) -> list[dict]:
    """Four-fifths rule on the *contact* rate, at the live budget (SK-23).

    Evaluated on protected *proxies* — occupation segment, income band, city tier,
    age band — because the protected attributes themselves are excluded outright
    by policy and are not in the data at all.
    """
    d = frame.copy()
    d["selected"] = selected
    d["age_band"] = pd.cut(d.age, [20, 30, 45, 63], labels=["21-30", "31-45", "46+"])
    inc = d["t_income_at_month"]
    d["income_band"] = pd.qcut(inc.rank(method="first"), 5,
                               labels=["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"])
    out = []
    for dim, col in [("Segment", "segment"), ("City tier", "city_tier"),
                     ("Age band", "age_band"), ("Income band", "income_band")]:
        rates = d.groupby(col, observed=True).selected.mean()
        n = d.groupby(col, observed=True).selected.size()
        ref = float(rates.max()) if len(rates) else float("nan")
        for g, r in rates.items():
            ratio = float(r / ref) if ref else float("nan")
            out.append(dict(dim=dim, group=str(g), sel_rate=round(float(r), 4),
                            ratio=round(ratio, 2), n=int(n[g]),
                            passes=bool(ratio >= 0.8)))
    return out


def income_accuracy(frame: pd.DataFrame) -> dict:
    """How good the behavioural income estimate is — the number every safe-EMI rests on."""
    true_inc = frame["t_income_at_month"].to_numpy(dtype=float)
    est = frame["credits_med_6m"].to_numpy(dtype=float)
    ok = np.isfinite(true_inc) & (true_inc > 0) & np.isfinite(est)
    err = np.abs(est[ok] - true_inc[ok]) / true_inc[ok]
    gig = (frame["segment"].astype(str).to_numpy()[ok] == "gig")
    return dict(within10=round(float((err <= 0.10).mean()), 3),
                within15=round(float((err <= 0.15).mean()), 3),
                gig_within15=round(float((err[gig] <= 0.15).mean()), 3) if gig.any() else None,
                median_err=round(float(np.median(err)), 3),
                gig_median_err=round(float(np.median(err[gig])), 3) if gig.any() else None,
                n=int(ok.sum()), n_gig=int(gig.sum()))


def qini(u: np.ndarray, T: np.ndarray, y: np.ndarray) -> dict:
    """Incremental conversions as a function of how deep you call, uplift-ranked."""
    order = np.argsort(-u, kind="stable")
    Tv, yv, n = T[order], y[order], len(order)
    curve = []
    for frac in [x / 20 for x in range(1, 21)]:
        k = max(1, int(n * frac))
        t, c = Tv[:k], ~Tv[:k]
        nt, nc = max(int(t.sum()), 1), max(int(c.sum()), 1)
        inc = float(yv[:k][t].sum() - yv[:k][c].sum() * nt / nc)
        curve.append(dict(frac=frac, inc=round(inc, 1), inc_per_1000=round(1000 * inc / nt, 1)))
    nt, nc = max(int(T.sum()), 1), max(int((~T).sum()), 1)
    total = float(y[T].sum() - y[~T].sum() * nt / nc)
    return dict(curve=curve, inc_total=round(total, 1),
                inc_per_1000_all=round(1000 * total / nt, 1),
                inc_per_1000_top20=curve[3]["inc_per_1000"])


# --------------------------------------------------------------------------- #
# the pre-registered contract
# --------------------------------------------------------------------------- #

#: criterion id -> (registered metric name, operator, threshold, severity).
#: Transcribed from ``validation/criteria.yaml``; ``tests/test_model_bands.py``
#: reads the YAML and asserts this table against it, so a silent edit to either
#: side fails the build.  ``severity`` is the YAML's own: ``fail`` gates the run,
#: ``report`` is read by a human and never gates — which is how a criterion like
#: SK-23 (the documented gig-worker gap) can be *failing* and *disclosed* at once.
REGISTERED_BANDS: dict[str, tuple[str, str, object, str]] = {
    "SK-01": ("random_contact_disbursement_rate", "between", (0.08, 0.10), "fail"),
    "SK-02": ("precision_at_10pct_budget", "between", (0.25, 0.35), "fail"),
    "SK-03": ("precision_at_5pct_and_20pct_budget", "report", None, "report"),
    "SK-04": ("window_respect_rate", "ge", 0.90, "fail"),
    "SK-05": ("window_shopper_auc", "ge", 0.70, "fail"),
    "SK-06": ("baseline_ladder_headline_uplift", "report", None, "report"),
    "SK-07": ("oot_precision_at_10pct_degradation_pp", "le", 5.0, "fail"),
    "SK-08": ("auc", "ge", 0.75, "fail"),
    "SK-09": ("macro_auc", "ge", 0.78, "fail"),
    "SK-10": ("auc_and_precision_at_10pct", "report", None, "report"),
    "SK-11": ("ece", "le", 0.03, "fail"),
    "SK-12": ("ece", "le", 0.03, "fail"),
    "SK-13": ("menu_of_4_hit_rate", "ge", 0.80, "fail"),
    "SK-14": ("top_1_product_accuracy", "report", None, "report"),
    "SK-15": ("shopper_signal_negative_direction_count", "ge", 4, "fail"),
    "SK-16": ("psi_score_distribution", "le", 0.10, "fail"),
    "SK-17": ("features_using_post_abandon_information", "eq", 0, "fail"),
    "SK-18": ("permuted_label_auc", "between", (0.48, 0.52), "fail"),
    "SK-19": ("precision_at_10pct_drop_by_feature_family", "report", None, "report"),
    "SK-20": ("n_seeds_run", "ge", 5, "fail"),
    "SK-21": ("cross_seed_precision_at_10pct_ci_width_pp", "le", 4.0, "fail"),
    "SK-22": ("precision_at_10pct_under_stress_scenarios", "report", None, "report"),
    "SK-23": ("adverse_impact_ratio", "ge", 0.80, "report"),
    "SK-24": ("gig_worker_failure_disclosure", "exists", None, "report"),
    "SK-25": ("precision_at_10pct_by_baseline_rung", "report", None, "report"),
}


_OP_TEXT = {"between": "in [{0}, {1}]", "ge": ">= {0}", "le": "<= {0}",
            "eq": "= {0}", "exists": "present", "report": "reported, no band"}


def band_text(metric: str, op: str, threshold) -> str:
    """The band as one readable line, for a screen that has no room for a table."""
    t = threshold if isinstance(threshold, (list, tuple)) else (threshold,)
    return f"{metric} {_OP_TEXT[op].format(*t)}" if t and t[0] is not None \
        else f"{metric} {_OP_TEXT[op]}"


def _verdict(op: str, value, threshold) -> str:
    #: "report" first: a criterion with no band is *reported*, and reporting
    #: nothing is "not_run", never "pass".
    if op == "report":
        return "report" if value is not None else "not_run"
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "not_measured"
    if op == "exists":
        return "pass" if value else "fail"
    if op == "between":
        return "pass" if threshold[0] <= value <= threshold[1] else "fail"
    if op == "ge":
        return "pass" if value >= threshold else "fail"
    if op == "le":
        return "pass" if value <= threshold else "fail"
    if op == "eq":
        return "pass" if value == threshold else "fail"
    raise ValueError(op)


def bands(values: dict[str, object],
          seed_means: dict[str, float] | None = None) -> dict[str, dict]:
    """``{SK-xx: {verdict, value, threshold, ...}}`` — failures included, never hidden.

    ``values`` is keyed by criterion id, not by metric name, because two criteria
    (SK-11 / SK-12, SK-08 / SK-10) share a metric name at different scopes.

    Where a criterion also has a **cross-seed mean**, the verdict on that mean is
    reported beside the packed seed's.  They can disagree, and when they do that
    is the finding: a band that clears on one split and not on the average of five
    has not really cleared.  ``agrees_across_seeds`` makes the disagreement
    impossible to skim past.
    """
    seed_means = seed_means or {}
    out = {}
    for cid, (metric, op, thr, severity) in REGISTERED_BANDS.items():
        v = values.get(cid)
        row = dict(metric=metric, op=op, severity=severity,
                   threshold=list(thr) if isinstance(thr, tuple) else thr,
                   value=v, observed=v, verdict=_verdict(op, v, thr),
                   band=band_text(metric, op, thr),
                   gating=(severity == "fail"))
        if cid in seed_means:
            mv = seed_means[cid]
            row["seed_mean"] = mv
            row["verdict_on_seed_mean"] = _verdict(op, mv, thr)
            row["agrees_across_seeds"] = row["verdict_on_seed_mean"] == row["verdict"]
        out[cid] = row
    return out


def headline(baseline: float, precision: float) -> str:
    """The one sentence the deck, the README and the cockpit all quote.

    Built from the two measured numbers, never typed.  It replaces "1% -> 36%"
    and the "28x lift" that went with it: those came from ranking the *whole
    liability book*, where a random call almost never lands, and they flattered
    the model by roughly a factor of three.
    """
    return (f"{round(baseline * 100):.0f} → {round(precision * 100):.0f} "
            f"disbursements per 100 RM calls")
