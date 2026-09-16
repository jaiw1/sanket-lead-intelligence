"""SD-S7 — the realism suite for SANKET's synthetic book, journeys, campaigns and labels.

Every other lane's ``check()`` (``book.build.check``, ``journeys.build.check``,
``journeys.labels.check``) raises on the first violation, which is exactly right
for a generator gate: fail the run before a bad book ships.  This suite is a
different tool, run *after* a book already passed those gates.  It re-measures
the same and additional properties **independently**, from the CSVs on disk
rather than the in-memory frames, and it never stops at the first failure — it
runs every check, prints PASS/FAIL for each with the observed value, the
expected value and a one-line rationale, and only then decides the exit code.
That is the shape a jury-facing realism audit needs: a full report, not a
stack trace.

Usage
-----
    python3 src/realism.py                                  # data/, writes data/realism_report.json
    python3 src/realism.py --data-dir data --out data/realism_report.json
    python3 src/realism.py --n 3000                          # generate a fresh small book+journeys
                                                               # into a temp dir and audit *that*
    python3 src/realism.py --n 3000 --data-dir /tmp/small     # ...into a chosen dir instead

Exit code is 0 iff every check passed; 1 otherwise.  A JSON report (one entry
per check, plus counts) is always written, pass or fail.

What is NOT covered here
-------------------------
This suite never edits, imports the ``check()`` functions of, or otherwise
second-guesses ``src/book/**`` or ``src/journeys/**`` — SD-S7's brief is to
audit the artefact, not to touch the generator.  Constants (product windows,
funnel shape targets, salary-day table, etc.) are imported read-only for
comparison; the two builder functions (``book.build.build_frames`` and
``journeys.build.generate_all``) are used only by ``--n``, to produce a *fresh*
artefact to audit — not to grade the generator's own opinion of itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]          # .../sanket
SRC = Path(__file__).resolve().parent                # .../sanket/src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from book.channels import (                                                    # noqa: E402
    BALANCE_FLOOR, FEE_SEASON_MONTHS, FESTIVE_MONTHS, MIN_BALANCE_FLOOR,
)
from book.products import DECISION_WINDOW_DAYS, PRODUCT_MIX, PRODUCTS          # noqa: E402
from journeys import CHANNELS, N_GATES, STAGES                                 # noqa: E402
from journeys.attempts import FEE_AMOUNT                                       # noqa: E402
from journeys.funnel import ABANDON_SHARE                                      # noqa: E402

# --------------------------------------------------------------------------- #
# assumed marginals this suite checks the book against — see DATA_CARD.md §2
# --------------------------------------------------------------------------- #

SEGMENT_TARGET = {"salaried": 0.60, "self-employed": 0.25, "gig": 0.15}
CITY_TIER_TARGET = {1: 0.38, 2: 0.40, 3: 0.22}
MARGIN_TOL = 0.05          # share points

DATA_FILES: tuple[str, ...] = (
    "customer_book.csv", "customer_panel.csv", "liability_book_truth.csv",
    "journeys.csv", "journey_events.csv", "journey_truth.csv",
    "campaigns.csv", "labels.csv", "label_truth.csv",
)


# --------------------------------------------------------------------------- #
# report plumbing
# --------------------------------------------------------------------------- #

@dataclass
class Result:
    group: str
    name: str
    passed: bool
    observed: str
    expected: str
    rationale: str

    def line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.group}/{self.name}: observed={self.observed} expected={self.expected} — {self.rationale}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group, "name": self.name,
            "status": "PASS" if self.passed else "FAIL",
            "observed": self.observed, "expected": self.expected,
            "rationale": self.rationale,
        }


class Suite:
    """Collects every check.  Nothing here raises — a broken assumption is a
    FAIL line in the report, not a stack trace, so the suite always finishes
    and always tells you everything that is wrong, not just the first thing."""

    def __init__(self, verbose: bool = True) -> None:
        self.results: list[Result] = []
        self.verbose = verbose

    def check(self, group: str, name: str, passed: bool, observed: Any, expected: Any,
              rationale: str) -> Result:
        r = Result(group=group, name=name, passed=bool(passed),
                   observed=str(observed), expected=str(expected), rationale=rationale)
        self.results.append(r)
        if self.verbose:
            print(r.line())
        return r

    @property
    def n_pass(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def n_fail(self) -> int:
        return len(self.results) - self.n_pass

    @property
    def all_passed(self) -> bool:
        return self.n_fail == 0

    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.passed]

    def group_count(self, group: str) -> int:
        return sum(1 for r in self.results if r.group == group)

    def summary(self) -> dict[str, Any]:
        by_group: dict[str, dict[str, int]] = {}
        for r in self.results:
            g = by_group.setdefault(r.group, {"pass": 0, "fail": 0, "total": 0})
            g["pass" if r.passed else "fail"] += 1
            g["total"] += 1
        return {"total": len(self.results), "passed": self.n_pass, "failed": self.n_fail,
                "by_group": by_group}


def pct(x: float) -> str:
    return f"{x:.2%}"


# --------------------------------------------------------------------------- #
# data loading / generation
# --------------------------------------------------------------------------- #

@dataclass
class Data:
    dir: Path
    book: pd.DataFrame
    panel: pd.DataFrame
    truth: pd.DataFrame
    journeys: pd.DataFrame
    events: pd.DataFrame
    journey_truth: pd.DataFrame
    campaigns: pd.DataFrame
    labels: pd.DataFrame
    label_truth: pd.DataFrame
    params: dict[str, Any]


def load_data(data_dir: Path) -> Data:
    """Read every artefact this suite audits from ``data_dir``.

    Deliberately plain ``pd.read_csv`` semantics (default NA handling): both a
    true ``NaN`` and the generator's own ``""`` sentinel collapse to a blank
    CSV field on write, so on read-back both come back as ``NaN`` uniformly —
    there is no ambiguity to special-case, only ``.isna()`` to check.
    """
    data_dir = Path(data_dir)
    missing = [f for f in DATA_FILES if not (data_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"{data_dir} is missing {missing}. Run `python3 src/make_book.py && "
            f"python3 src/make_journeys.py` first, or pass --n to generate a fresh book.")

    def rd(name: str) -> pd.DataFrame:
        try:
            return pd.read_csv(data_dir / name, engine="pyarrow")
        except Exception:
            return pd.read_csv(data_dir / name)

    params_path = data_dir / "journey_params.json"
    params = json.loads(params_path.read_text()) if params_path.exists() else {}

    return Data(
        dir=data_dir,
        book=rd("customer_book.csv"),
        panel=rd("customer_panel.csv"),
        truth=rd("liability_book_truth.csv"),
        journeys=rd("journeys.csv"),
        events=rd("journey_events.csv"),
        journey_truth=rd("journey_truth.csv"),
        campaigns=rd("campaigns.csv"),
        labels=rd("labels.csv"),
        label_truth=rd("label_truth.csv"),
        params=params,
    )


def generate_book_and_journeys(n: int, months: int, seed: int, out_dir: Path) -> Path:
    """Build a fresh book + journey/label/campaign layer and write every CSV
    this suite audits, exactly as ``make_book.py`` / ``make_journeys.py`` do.

    Used by ``--n``.  This calls the two *builder* entry points
    (``book.build.build_frames``, ``journeys.build.generate_all``) — never
    their ``check()`` functions, which is what keeps this a fresh artefact to
    audit independently rather than a re-run of the generator's own opinion of
    itself.
    """
    from book import BookConfig
    from book.build import build_frames
    from journeys import JourneyConfig
    from journeys.build import generate_all

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = BookConfig(n=n, months=months, seed=seed, out_dir=out_dir)
    panel, book, truth = build_frames(cfg)
    panel.to_csv(out_dir / "customer_panel.csv", index=False)
    book.to_csv(out_dir / "customer_book.csv", index=False)
    truth.to_csv(out_dir / "liability_book_truth.csv", index=False, float_format="%.4g")

    jcfg = JourneyConfig(book_dir=out_dir, out_dir=out_dir, seed=seed)
    b = generate_all(jcfg)
    b.journeys.to_csv(out_dir / "journeys.csv", index=False)
    b.events.to_csv(out_dir / "journey_events.csv", index=False)
    b.truth.to_csv(out_dir / "journey_truth.csv", index=False)
    b.campaigns.to_csv(out_dir / "campaigns.csv", index=False)
    b.labels.to_csv(out_dir / "labels.csv", index=False)
    b.label_truth.to_csv(out_dir / "label_truth.csv", index=False)
    (out_dir / "journey_params.json").write_text(json.dumps(b.params, indent=2) + "\n")
    return out_dir


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="mixed")


# --------------------------------------------------------------------------- #
# 0. seed reproducibility
# --------------------------------------------------------------------------- #

#: A tiny, fixed configuration used only to prove the RNG-substream mechanism
#: is reproducible.  Deliberately decoupled from the size of the data being
#: audited (which can be 60,000 x 30) so this check stays under a second
#: regardless of how big a run it is embedded in.
_REPRO_N, _REPRO_MONTHS, _REPRO_SEED = 1_500, 13, 4242112


def check_seed_reproducibility(suite: Suite) -> None:
    from book import BookConfig
    from book.build import build_frames
    g = "seed_reproducibility"

    cfg = BookConfig(n=_REPRO_N, months=_REPRO_MONTHS, seed=_REPRO_SEED)
    p1, b1, t1 = build_frames(cfg)
    p2, b2, t2 = build_frames(cfg)
    book_ok = (pd.util.hash_pandas_object(p1).equals(pd.util.hash_pandas_object(p2))
               and pd.util.hash_pandas_object(b1).equals(pd.util.hash_pandas_object(b2))
               and pd.util.hash_pandas_object(t1).equals(pd.util.hash_pandas_object(t2)))
    h1 = int(pd.util.hash_pandas_object(pd.concat([p1, b1], axis=0, ignore_index=True)).sum())
    h2 = int(pd.util.hash_pandas_object(pd.concat([p2, b2], axis=0, ignore_index=True)).sum())
    suite.check(g, "book_same_seed_same_hash", book_ok, f"{h1:x}", f"{h2:x} (equal)",
                "book.build.substream() draws from named substreams keyed on (seed, stream_id), "
                "never a single sequential stream — the same seed must reproduce every column "
                "bit-for-bit (DATA_CARD §8)")

    with tempfile.TemporaryDirectory(prefix="sanket_repro_") as td:
        out = Path(td)
        p1.to_csv(out / "customer_panel.csv", index=False)
        b1.to_csv(out / "customer_book.csv", index=False)
        t1.to_csv(out / "liability_book_truth.csv", index=False, float_format="%.4g")

        from journeys import JourneyConfig
        from journeys.build import generate_all
        jcfg = JourneyConfig(book_dir=out, out_dir=out, seed=_REPRO_SEED)
        r1 = generate_all(jcfg)
        r2 = generate_all(jcfg)
        journeys_ok = (pd.util.hash_pandas_object(r1.journeys).equals(pd.util.hash_pandas_object(r2.journeys))
                       and pd.util.hash_pandas_object(r1.labels).equals(pd.util.hash_pandas_object(r2.labels))
                       and pd.util.hash_pandas_object(r1.campaigns).equals(pd.util.hash_pandas_object(r2.campaigns)))
        jh1 = int(pd.util.hash_pandas_object(r1.journeys).sum())
        jh2 = int(pd.util.hash_pandas_object(r2.journeys).sum())
        suite.check(g, "journeys_same_seed_same_hash", journeys_ok, f"{jh1:x}", f"{jh2:x} (equal)",
                    "journeys.build likewise draws from named substreams (shoppers/applicants/attempts/"
                    "signals/funnel/timing/campaigns/labels); theta and the S/N knob are solved "
                    "deterministically so a re-run at the same seed must match exactly")

        theta1 = r1.params["labels"]["theta_contact_effect"]
        theta2 = r2.params["labels"]["theta_contact_effect"]
        suite.check(g, "solved_knobs_reproducible", theta1 == theta2, theta1, theta2,
                    "the contact-effect theta and the signal-to-noise knob are solved numerically "
                    "(DATA_CARD §12.3); a non-reproducible solve would mean the bands passing is luck")


# --------------------------------------------------------------------------- #
# 1. funnel shape vs target
# --------------------------------------------------------------------------- #

def check_funnel_shape(suite: Suite, d: Data) -> None:
    g = "funnel_shape"
    j = d.journeys
    abandoned = j.outcome == "abandoned"
    disbursed = j.outcome == "disbursed"

    if int(abandoned.sum()) == 0:
        suite.check(g, "abandonments_exist_to_measure_shape_against", False, "0", "> 0",
                    "no abandoned attempts in this draw — the funnel shape is unmeasurable")
        return

    stage_share = j.loc[abandoned, "last_stage"].value_counts(normalize=True)
    tol = 0.08  # journeys/build.py's own STAGE_SHARE_TOL is 0.06 at the default 60k size;
                # widened here for an independent audit that must also hold on a small book
    for s in STAGES[:N_GATES]:
        target = ABANDON_SHARE[s]
        obs = float(stage_share.get(s, 0.0))
        suite.check(g, f"abandon_share_at_{s}", abs(obs - target) <= tol, pct(obs),
                    f"{pct(target)} +/- {pct(tol)}",
                    "funnel.ABANDON_SHARE is the one declared shape parameter the seven stage "
                    "intercepts are solved to hit (DATA_CARD §11.1); Docs and Fee should be the two "
                    "biggest bars")

    if int(disbursed.sum()) > 0:
        t = d.journey_truth.set_index("attempt_id")["p_complete"]
        p_disb = float(t.reindex(j.loc[disbursed, "attempt_id"]).mean())
        p_aband = float(t.reindex(j.loc[abandoned, "attempt_id"]).mean())
        suite.check(g, "hazard_rates_disbursed_attempts_higher", p_disb > p_aband,
                    f"{p_disb:.3f} vs {p_aband:.3f}", "p_complete(disbursed) > p_complete(abandoned)",
                    "the level constraint on the solved intercepts (DATA_CARD §11.1) must keep the "
                    "hazard's own completion odds honest, or a 26% completion rate would be a "
                    "coincidence the model could not have predicted")


# --------------------------------------------------------------------------- #
# 2. product mix vs the assumed table
# --------------------------------------------------------------------------- #

def check_product_mix(suite: Suite, d: Data) -> None:
    g = "product_mix"
    b = d.book
    conv = b[b.event_month >= 0]

    seen = set(conv.product_canonical.dropna().unique())
    suite.check(g, "all_six_products_taken_by_some_converter", seen == set(PRODUCTS),
                sorted(seen), sorted(PRODUCTS),
                "book.products.PRODUCTS names six products; every one of them should have at least "
                "one converter, or the menu-of-four exhibit has a dead entry")

    tol = 0.12   # share points; PRODUCT_MIX is `assumed` (DATA_CARD §4), and substitution +
                 # eligibility move the realised mix away from it, so this is plausibility, not equality
    for seg, table in PRODUCT_MIX.items():
        sub = conv[conv.segment == seg]
        if len(sub) < 20:
            suite.check(g, f"product_mix_{seg}_has_enough_converters", False, len(sub), ">= 20",
                        "too few converters in this segment at this book size to compare a mix")
            continue
        mix = sub.product_canonical.value_counts(normalize=True)
        max_dev = max(abs(mix.get(p, 0.0) - table[p]) for p in PRODUCTS)
        worst = max(PRODUCTS, key=lambda p: abs(mix.get(p, 0.0) - table[p]))
        suite.check(g, f"product_mix_{seg}_near_assumed_table", max_dev <= tol,
                    f"max dev {pct(max_dev)} (on {worst})", f"<= {pct(tol)}",
                    f"book.products.PRODUCT_MIX[{seg!r}] is the assumed converter product mix by "
                    "segment (DATA_CARD §4)")


# --------------------------------------------------------------------------- #
# 3. time-to-disburse vs product decision windows
# --------------------------------------------------------------------------- #

def check_time_to_disburse(suite: Suite, d: Data) -> None:
    g = "time_to_disburse"
    j = d.journeys
    disbursed = j.outcome == "disbursed"
    have_contact = disbursed & j.rm_contacted_at.notna() & j.disbursed_at.notna()

    if int(have_contact.sum()) == 0:
        suite.check(g, "contacted_disbursements_exist_to_measure", False, "0", "> 0",
                    "no RM-contacted disbursed attempts in this draw")
        return

    dd = _dt(j.loc[have_contact, "disbursed_at"])
    cc = _dt(j.loc[have_contact, "rm_contacted_at"])
    lag = (dd - cc).dt.total_seconds().to_numpy() / 86400.0
    w = j.loc[have_contact, "decision_window_days"].to_numpy(dtype=float)
    respect = float(np.mean(lag <= w))
    suite.check(g, "window_respect_rate_floor", respect >= 0.90, pct(respect), ">= 90%",
                "SK-04 / DATA_CARD §11.5: of contacted disbursements, the share landing inside the "
                "offered product's own decision window")
    suite.check(g, "some_disbursements_miss_their_window", respect < 1.0, pct(respect), "< 100%",
                "if literally everything lands inside the window the stall tail (DATA_CARD §11.5) "
                "is dead and SK-04 is trivially satisfied rather than genuinely measured")

    for p, wdays in DECISION_WINDOW_DAYS.items():
        mask = have_contact & (j["product"] == p)
        sub_n = int(mask.sum())
        if sub_n < 5:
            continue
        dd_p = _dt(j.loc[mask, "disbursed_at"])
        cc_p = _dt(j.loc[mask, "rm_contacted_at"])
        lag_p = ((dd_p - cc_p).dt.total_seconds() / 86400.0).to_numpy()
        med = float(np.median(lag_p))
        inside = float(np.mean(lag_p <= wdays))
        # a generous ceiling on the MEDIAN, not a per-row bound: the clock's own stall tail
        # (DATA_CARD §11.5) means some contacted disbursements land well past the window.
        suite.check(g, f"median_lag_{p}_same_order_as_window", med <= 3 * wdays, f"{med:.1f}d (n={sub_n})",
                    f"<= {3 * wdays}d ({wdays}d window)",
                    f"the {p} decision window is {wdays} days; a median many multiples of it would mean "
                    "the clock is not actually keyed to the product")
        suite.check(g, f"share_of_{p}_inside_window_plausible", inside >= 0.60, pct(inside), ">= 60%",
                    f"per-product share landing inside the {wdays}-day window; SK-04's 90% floor is "
                    "over ALL products pooled, so a thin product can sit below it individually")


# --------------------------------------------------------------------------- #
# 4. UPI adoption trend monotone
# --------------------------------------------------------------------------- #

def check_upi_trend(suite: Suite, d: Data) -> None:
    g = "upi_trend"
    by_month = d.panel.groupby("month")[["upi_p2m_value", "upi_p2m_count"]].mean().sort_index()
    months = pd.Series(by_month.index.to_numpy(), index=by_month.index)

    for col in ("upi_p2m_value", "upi_p2m_count"):
        series = by_month[col]
        rho = float(series.corr(months, method="spearman"))
        suite.check(g, f"{col}_trend_rising_with_month", rho >= 0.85, f"spearman rho={rho:.3f}",
                    ">= 0.85",
                    "channels.UPI_ADOPTION_DRIFT drifts the P2M share up 0.6%/month (DATA_CARD §5.2); "
                    "the book-wide monthly mean should rise with the panel month")
        q = max(1, len(series) // 4)
        first_q, last_q = float(series.iloc[:q].mean()), float(series.iloc[-q:].mean())
        suite.check(g, f"{col}_last_quarter_above_first_quarter", last_q > first_q,
                    f"{last_q:.1f} vs {first_q:.1f}", "last quarter of the panel > first quarter",
                    "the same adoption drift, read as a coarser and more robust first-vs-last check")


# --------------------------------------------------------------------------- #
# 5. salary-day concentration
# --------------------------------------------------------------------------- #

def check_salary_day(suite: Suite, d: Data) -> None:
    g = "salary_day_concentration"
    day_share = d.panel.salary_credit_day.value_counts(normalize=True)
    uniform = 1.0 / 28.0

    day1 = float(day_share.get(1, 0.0))
    suite.check(g, "day_1_is_the_mode", int(day_share.idxmax()) == 1, int(day_share.idxmax()), 1,
                "population.SALARY_DAY_P puts 30% of base salary days on the 1st, the single "
                "largest cell (DATA_CARD §2) — it should stay the observed mode after jitter")
    suite.check(g, "day_1_materially_above_uniform", day1 >= 3 * uniform, pct(day1),
                f">= {pct(3 * uniform)} (3x uniform)",
                "a flat 1/28 per day would mean salary_credit_day carries no signal at all")

    top3 = float(day_share.sort_values(ascending=False).head(3).sum())
    suite.check(g, "top3_salary_days_concentrated", top3 >= 0.30, pct(top3), ">= 30%",
                "Indian payroll clusters hard on a handful of days (SALARY_DAY_P, DATA_CARD §2); "
                "3/28 = 10.7% would be the uniform baseline")

    # day 30 in SALARY_DAY_P clips to 28 (`np.clip(base + jitter, 1, 28)`), so the mass that
    # channels.py assigns to "the last working day" shows up on 28, not 30 — checking for 30
    # directly would be a self-inflicted false negative.
    day28 = float(day_share.get(28, 0.0))
    suite.check(g, "day_28_elevated_end_of_month_clip", day28 >= 3 * uniform, pct(day28),
                f">= {pct(3 * uniform)} (3x uniform)",
                "SALARY_DAY_P's 18% on day 30 clips to day 28 in channels.py (np.clip(..., 1, 28)); "
                "the end-of-month cluster should show up there")


# --------------------------------------------------------------------------- #
# 6. income-balance correlation sign and range
# --------------------------------------------------------------------------- #

def check_income_balance_correlation(suite: Suite, d: Data) -> None:
    g = "income_balance_correlation"
    avg_bal = d.panel.groupby("cust_id")["bal_avg"].mean()
    income = d.book.set_index("cust_id")["true_income"]
    joined = pd.concat([income, avg_bal], axis=1).dropna()
    joined.columns = ["true_income", "bal_avg"]
    corr = float(joined["true_income"].corr(joined["bal_avg"]))
    suite.check(g, "income_balance_correlation_sign_and_range", 0.05 <= corr <= 0.90,
                f"{corr:.3f}", "(0.05, 0.90)",
                "capacity should track income positively — richer customers carry higher balances "
                "on average — but not deterministically: the dormant_rich archetype (fat balance, no "
                "income-linked intent, DATA_CARD §6) and income volatility should keep it well short "
                "of 1.0")


# --------------------------------------------------------------------------- #
# 7. EMI burden bounds
# --------------------------------------------------------------------------- #

def check_emi_burden(suite: Suite, d: Data) -> None:
    g = "emi_burden"
    p = d.panel
    suite.check(g, "ext_emi_never_negative", bool((p.ext_emi >= 0).all()), f"min={p.ext_emi.min()}",
                ">= 0", "an EMI outflow can be zero, never negative")
    suite.check(g, "emi_outflow_to_other_bank_never_negative",
                bool((p.emi_outflow_to_other_bank >= 0).all()),
                f"min={p.emi_outflow_to_other_bank.min()}", ">= 0",
                "the AA/595-gap column is a share of ext_emi (DATA_CARD §5.2); it can be zero, "
                "never negative")

    ratio = p.ext_emi / p.credits.replace(0, np.nan)
    max_ratio = float(np.nanmax(ratio.to_numpy()))
    p99 = float(np.nanpercentile(ratio.to_numpy(), 99))
    suite.check(g, "emi_to_income_ratio_capped", max_ratio <= 3.0, f"max={max_ratio:.2f}, p99={p99:.2f}",
                "max <= 3.0",
                "even under the personal-loan EMI-stacking ramp (channels.EMI_CREEP_STRONG) and an "
                "existing home loan, EMI outflow should stay a bounded multiple of monthly credits, "
                "not blow up unboundedly")
    suite.check(g, "emi_to_income_ratio_p99_reasonable", p99 <= 1.0, f"p99={p99:.2f}", "<= 1.0",
                "the 99th percentile of the EMI burden should sit at or below one month's income for "
                "the overwhelming majority of customer-months")


# --------------------------------------------------------------------------- #
# 8. age / tenure / segment / city-tier marginals
# --------------------------------------------------------------------------- #

def check_marginals(suite: Suite, d: Data) -> None:
    g = "marginals"
    b = d.book

    age = b.age.to_numpy()
    suite.check(g, "age_within_lending_window", bool(((age >= 21) & (age <= 62)).all()),
                f"[{int(age.min())}, {int(age.max())}]", "[21, 62]",
                "population.py draws age ~ N(36, 9) clipped to [21, 62] (DATA_CARD §2)")

    tenure = b.tenure_m.to_numpy()
    suite.check(g, "tenure_within_drawn_range", bool(((tenure >= 8) & (tenure < 180)).all()),
                f"[{int(tenure.min())}, {int(tenure.max())}]", "[8, 180)",
                "population.py draws tenure_m ~ U{8..179} (DATA_CARD §2)")

    seg_share = b.segment.value_counts(normalize=True).to_dict()
    for seg, target in SEGMENT_TARGET.items():
        obs = float(seg_share.get(seg, 0.0))
        suite.check(g, f"segment_share_{seg}", abs(obs - target) <= MARGIN_TOL, pct(obs),
                    f"{pct(target)} +/- {pct(MARGIN_TOL)}",
                    "book.SEGMENT_P is the assumed employment-segment mix (DATA_CARD §2)")

    tier_share = b.city_tier.value_counts(normalize=True).to_dict()
    for tier, target in CITY_TIER_TARGET.items():
        obs = float(tier_share.get(tier, 0.0))
        suite.check(g, f"city_tier_share_{tier}", abs(obs - target) <= MARGIN_TOL, pct(obs),
                    f"{pct(target)} +/- {pct(MARGIN_TOL)}",
                    "population.py draws city_tier at 38/40/22% (DATA_CARD §2)")

    consent = float(b.consent.mean())
    suite.check(g, "consent_share", abs(consent - 0.85) <= MARGIN_TOL, pct(consent),
                f"85% +/- {pct(MARGIN_TOL)}",
                "BookConfig.consent_share = 0.85 (DATA_CARD §2)")


# --------------------------------------------------------------------------- #
# 9. seasonality present where designed, absent where not
# --------------------------------------------------------------------------- #

def _calendar_month(panel: pd.DataFrame) -> pd.Series:
    return panel["date"].astype(str).str.split("-").str[1].astype(int)


def check_seasonality(suite: Suite, d: Data) -> None:
    g = "seasonality"
    p = d.panel.assign(cal_m=_calendar_month(d.panel))
    fee_season = p.cal_m.isin(FEE_SEASON_MONTHS)
    festive = p.cal_m.isin(FESTIVE_MONTHS)

    school_in = float(p.loc[fee_season, "school_fees"].mean())
    school_out = float(p.loc[~fee_season, "school_fees"].mean())
    ratio = school_in / school_out if school_out else float("nan")
    suite.check(g, "school_fee_season_present", ratio >= 1.3, f"{ratio:.2f}x", ">= 1.3x",
                f"channels.FEE_SEASON_MULTIPLIER = 1.6 in months {FEE_SEASON_MONTHS} (DATA_CARD §5.3)")

    ecom_in = float(p.loc[festive, "ecommerce"].mean())
    ecom_out = float(p.loc[~festive, "ecommerce"].mean())
    ratio = ecom_in / ecom_out if ecom_out else float("nan")
    suite.check(g, "festive_ecommerce_season_present", ratio >= 1.15, f"{ratio:.2f}x", ">= 1.15x",
                f"channels.FESTIVE_ECOM_MULTIPLIER = 1.4 in months {FESTIVE_MONTHS} (DATA_CARD §5.3)")

    cardholders = p[p.card_spend > 0]
    card_in = float(cardholders.loc[cardholders.cal_m.isin(FESTIVE_MONTHS), "card_spend"].mean())
    card_out = float(cardholders.loc[~cardholders.cal_m.isin(FESTIVE_MONTHS), "card_spend"].mean())
    ratio = card_in / card_out if card_out else float("nan")
    suite.check(g, "festive_card_spend_season_present", ratio >= 1.15, f"{ratio:.2f}x", ">= 1.15x",
                f"channels.FESTIVE_CARD_MULTIPLIER = 1.5 among cardholders in {FESTIVE_MONTHS}")

    # controls: channels NOT designed to carry a calendar-seasonal effect should show none.
    fuel_in = float(p.loc[festive, "fuel_cab"].mean())
    fuel_out = float(p.loc[~festive, "fuel_cab"].mean())
    fuel_ratio = fuel_in / fuel_out if fuel_out else float("nan")
    suite.check(g, "fuel_cab_has_no_festive_seasonality_control", 0.85 <= fuel_ratio <= 1.15,
                f"{fuel_ratio:.2f}x", "[0.85x, 1.15x]",
                "fuel_cab only moves with the auto-loan ramp (channels.FUEL_SURGE_*), never with the "
                "calendar; a control that DID show a seasonal swing would mean a spurious calendar "
                "effect leaked into a channel that should not carry one")

    mand_in = float(p.loc[fee_season, "mandate_failure_count"].mean())
    mand_out = float(p.loc[~fee_season, "mandate_failure_count"].mean())
    mand_ratio = mand_in / mand_out if mand_out else float("nan")
    suite.check(g, "mandate_failures_have_no_fee_season_seasonality_control",
                0.85 <= mand_ratio <= 1.15, f"{mand_ratio:.2f}x", "[0.85x, 1.15x]",
                "channels.MANDATE_FAIL_* has no calendar term at all — only a balance/EMI coupling — "
                "so this control should show no fee-season swing")


# --------------------------------------------------------------------------- #
# 10. duplicate keys
# --------------------------------------------------------------------------- #

def check_duplicate_keys(suite: Suite, d: Data) -> None:
    g = "duplicate_keys"

    def dup(name: str, df: pd.DataFrame, cols: list[str]) -> None:
        n = int(df.duplicated(cols).sum())
        suite.check(g, f"{name}_key_unique", n == 0, f"{n} duplicate rows",
                    f"0 duplicates on {cols}", f"{name}'s primary key must be unique")

    dup("customer_book", d.book, ["cust_id"])
    dup("customer_panel", d.panel, ["cust_id", "month"])
    dup("liability_book_truth", d.truth, ["cust_id", "month"])
    dup("journeys", d.journeys, ["attempt_id"])
    dup("journey_truth", d.journey_truth, ["attempt_id"])
    dup("journey_events", d.events, ["attempt_id", "seq"])
    dup("campaigns", d.campaigns, ["campaign_id"])
    dup("labels", d.labels, ["cust_id", "month"])
    dup("label_truth", d.label_truth, ["cust_id", "month"])


# --------------------------------------------------------------------------- #
# 11. referential integrity across book / journeys / events / labels / campaigns
# --------------------------------------------------------------------------- #

def check_referential_integrity(suite: Suite, d: Data) -> None:
    g = "referential_integrity"
    book_ids = set(d.book.cust_id)

    def orphans(name: str, series: pd.Series, valid: set) -> None:
        bad = int((~series.isin(valid)).sum())
        suite.check(g, name, bad == 0, f"{bad} orphaned rows", "0", f"every {name} key must resolve")

    orphans("journeys_customer_id_in_book", d.journeys.customer_id, book_ids)
    orphans("campaigns_cust_id_in_book", d.campaigns.cust_id, book_ids)
    orphans("labels_cust_id_in_book", d.labels.cust_id, book_ids)
    orphans("journey_events_attempt_id_in_journeys", d.events.attempt_id, set(d.journeys.attempt_id))
    orphans("journey_truth_attempt_id_in_journeys", d.journey_truth.attempt_id, set(d.journeys.attempt_id))

    lab_keys = set(zip(d.labels.cust_id, d.labels.month))
    lt_keys = set(zip(d.label_truth.cust_id, d.label_truth.month))
    suite.check(g, "label_truth_keys_match_labels_keys", lab_keys == lt_keys,
                f"{len(lt_keys)} keys", f"{len(lab_keys)} keys",
                "label_truth.csv and labels.csv are one row per (cust_id, month) of the same "
                "population (DATA_CARD §12.1) — the key sets must be identical")

    j_keys = set(d.journeys.attempt_id)
    jt_keys = set(d.journey_truth.attempt_id)
    suite.check(g, "journey_truth_keys_match_journeys_keys", j_keys == jt_keys,
                f"{len(jt_keys)} keys", f"{len(j_keys)} keys",
                "journey_truth.csv is one row per attempt in journeys.csv")

    bad = int((~d.journeys["product"].isin(PRODUCTS)).sum())
    suite.check(g, "journeys_product_values_valid", bad == 0, f"{bad} invalid", "0",
                f"journeys.product must be one of {PRODUCTS}")
    bad = int((~d.campaigns["product"].isin(PRODUCTS)).sum())
    suite.check(g, "campaigns_product_values_valid", bad == 0, f"{bad} invalid", "0",
                f"campaigns.product must be one of {PRODUCTS}")
    bad = int((~d.labels.dropoff_product.isin(PRODUCTS)).sum())
    suite.check(g, "labels_dropoff_product_values_valid", bad == 0, f"{bad} invalid", "0",
                f"labels.dropoff_product must be one of {PRODUCTS}")
    bad = int((~d.journeys.channel.isin(CHANNELS)).sum())
    suite.check(g, "journeys_channel_values_valid", bad == 0, f"{bad} invalid", "0",
                f"journeys.channel must be one of {CHANNELS}")


# --------------------------------------------------------------------------- #
# 12. impossible-state assertions (>= 25)
# --------------------------------------------------------------------------- #

def check_impossible_states(suite: Suite, d: Data) -> None:
    """Every state the generator's own design says cannot exist.  Each one is a
    separate PASS/FAIL line; the group is asserted (below, in ``run_suite``) to
    contain at least 25 of them, per the SD-S7 brief."""
    g = "impossible_states"
    b, panel, j, ev, camp, lab = d.book, d.panel, d.journeys, d.events, d.campaigns, d.labels
    fee_idx = STAGES.index("fee")

    def n(mask) -> int:
        return int(np.asarray(mask).sum())

    def imp(name: str, bad_count: int, rationale: str) -> None:
        suite.check(g, name, bad_count == 0, f"{bad_count} violating rows", "0", rationale)

    # ---- the journey funnel ------------------------------------------------ #
    disb = j.outcome == "disbursed"
    aband = j.outcome == "abandoned"
    inflight = j.outcome == "in_flight"
    started = _dt(j.started_at)

    disbursed_at = _dt(j.disbursed_at)
    bad = n(disb & j.disbursed_at.notna() & j.started_at.notna() & (disbursed_at < started))
    imp("disburse_before_start", bad, "an attempt cannot disburse before it started")

    bad = n((j.fee_paid == 1) & (j.last_stage_idx < fee_idx))
    imp("fee_paid_without_reaching_fee", bad,
        "fee_paid can only be true for an attempt that reached the Fee gate")

    ev2 = ev.merge(j[["attempt_id", "abandoned_at", "disbursed_at"]], on="attempt_id", how="left")
    term = _dt(ev2.abandoned_at.where(ev2.abandoned_at.notna(), ev2.disbursed_at))
    occ = _dt(ev2.occurred_at)
    bad = n(term.notna() & (occ > term + pd.Timedelta(seconds=2)))
    imp("events_after_terminal_instant", bad,
        "no stage-transition event may occur after abandoned_at / disbursed_at")

    bad = n(panel.bal_avg < 0)
    imp("negative_bal_avg", bad, "a balance cannot be negative")
    bad = n(panel.bal_avg < BALANCE_FLOOR - 1e-6)
    imp("bal_avg_below_documented_floor", bad,
        f"channels.BALANCE_FLOOR = {BALANCE_FLOOR:,.0f} is enforced every month (DATA_CARD §5.1)")
    bad = n(panel.bal_min < 0)
    imp("negative_bal_min", bad, "a minimum balance cannot be negative")
    bad = n(panel.bal_min < MIN_BALANCE_FLOOR - 1e-6)
    imp("bal_min_below_documented_floor", bad,
        f"channels.MIN_BALANCE_FLOOR = {MIN_BALANCE_FLOOR:,.0f} is enforced every month")

    bad = n((lab.suppressed == 1) & (lab.contacted == 1))
    imp("contacted_while_suppressed", bad,
        "labels.py forces `contacted &= eligible` — a suppressed row can never carry a contact")
    bad = n((lab.suppressed == 1) & (lab.label_disbursed_in_window == 1))
    imp("label_positive_on_suppressed_row", bad,
        "asserted in labels.check() too; independently re-verified here from the CSV")

    bad = n((b.age < 18) & (b.has_home_loan == 1))
    imp("minors_with_home_loans", bad,
        "population.py clips age to >= 21, so this should be vacuously true, but the check stands "
        "as a guard against a future age-range change")

    bad = n((b.product_canonical == "gold") & (b.gold_holding_g <= 0))
    imp("gold_loan_without_gold_holding", bad,
        "book.latent eligibility zeroes the gold-loan weight for customers with no gold "
        "(DATA_CARD §4) — a converter cannot take gold with no holding")
    bad = n((b.product_canonical == "lap") & (b.owns_property == 0))
    imp("lap_without_owning_property", bad,
        "a loan against property requires owning one — eligibility zeroes the LAP weight otherwise")

    bad = n(disb & (j.fee_paid != 1))
    imp("disbursed_without_paying_the_fee", bad,
        "every disbursement passed the Fee gate, which means the Rs 1,000 fee was paid")
    bad = n(disb & j.abandoned_at.notna())
    imp("disbursed_attempt_also_abandoned", bad, "an attempt has exactly one terminal outcome")
    bad = n(aband & j.disbursed_at.notna())
    imp("abandoned_attempt_also_disbursed", bad, "an attempt has exactly one terminal outcome")
    bad = n(inflight & (j.abandoned_at.notna() | j.disbursed_at.notna()))
    imp("in_flight_attempt_carries_a_terminal_timestamp", bad,
        "in_flight means the panel ended before either terminal event happened")
    bad = n((j.last_stage_idx == len(STAGES) - 1) != disb)
    imp("reaching_disburse_stage_disagrees_with_outcome", bad,
        "last_stage_idx == 7 (Disburse) iff outcome == 'disbursed'")

    bad = n(j.docs_supplied.notna() & j.docs_requested.notna()
            & (j.docs_supplied > j.docs_requested + 1e-6))
    imp("more_documents_supplied_than_requested", bad, "docs_supplied cannot exceed docs_requested")

    bad = n(panel.mandate_failure_count > panel.external_emi_count)
    imp("more_mandate_failures_than_mandates", bad,
        "asserted in book.build.check() too; independently re-verified from the CSV")
    bad = n(panel.emi_outflow_to_other_bank > panel.ext_emi + 1)
    imp("other_bank_emi_exceeds_total_external_emi", bad,
        "emi_outflow_to_other_bank is a share of ext_emi (DATA_CARD §5.2); it cannot exceed the whole")

    bad = n(~panel.salary_credit_day.between(1, 28))
    imp("salary_credit_day_out_of_range", bad, "the day-of-month channel is clipped to [1, 28]")

    money_cols = ["credits", "bal_avg", "bal_min", "rent", "fuel_cab", "school_fees", "ecommerce",
                  "ext_emi", "fd_bal", "upi_p2m_value", "emi_outflow_to_other_bank", "card_spend",
                  "insurance_premium", "bonus_or_irregular_credit"]
    bad = int(sum(int((panel[c] < 0).sum()) for c in money_cols))
    imp("negative_money_column_value", bad, f"none of {money_cols} may go negative (book.build.check())")

    bad = n(j.amount_offered.notna() & (j.amount_offered > j.amount_requested + 1.0))
    imp("amount_offered_exceeds_amount_requested", bad,
        "attempts.build_month_signals caps the offer at the request (offered = min(req, max_loan) * "
        "(1 - haircut))")
    bad = n(j.fee_amount.notna() & (j.fee_amount != FEE_AMOUNT))
    imp("fee_amount_not_flat_1000", bad,
        f"attempts.FEE_AMOUNT = {FEE_AMOUNT:,} is a flat fee across all six products (DATA_CARD §11.8)")

    conv_ids = set(b.loc[b.event_month >= 0, "cust_id"])
    disb_ids = set(j.loc[disb, "customer_id"])
    imp("converter_without_a_matching_disbursed_attempt", len(conv_ids - disb_ids),
        "every book converter must have exactly one disbursed journey attempt")
    imp("disbursed_attempt_for_a_non_converter", len(disb_ids - conv_ids),
        "the journey layer must never invent a disbursement the book does not have")

    disb_prod = j.loc[disb].set_index("customer_id")["product"]
    book_prod = b.set_index("cust_id")["product_canonical"]
    common = disb_prod.index.intersection(book_prod.index)
    bad = int((disb_prod.reindex(common) != book_prod.reindex(common)).sum())
    imp("disbursed_product_differs_from_book_product", bad,
        "a converter's disbursed attempt must be for the product the book names")

    # ---- suppression / campaigns ------------------------------------------- #
    dnd_ids = set(b.loc[b.dnd == 1, "cust_id"])
    bad = int(camp.cust_id.isin(dnd_ids).sum())
    imp("campaign_sent_to_a_dnd_customer", bad,
        "campaigns.build_campaigns computes `mailable = (consent==1) & (dnd==0)` before drawing "
        "any touch")
    noconsent_ids = set(b.loc[b.consent == 0, "cust_id"])
    bad = int(camp.cust_id.isin(noconsent_ids).sum())
    imp("campaign_sent_to_a_no_consent_customer", bad, "same `mailable` gate as the DND check above")

    if "deceased" in set(lab.suppression_reason):
        first_dead = lab.loc[lab.suppression_reason == "deceased"].groupby("cust_id").as_at.min()
        cs = camp.assign(_t=_dt(camp.sent_at))
        bad_count = 0
        for cid, asat in first_dead.items():
            mine = cs[cs.cust_id == cid]
            bad_count += int((mine["_t"] > pd.Timestamp(asat)).sum())
        imp("campaign_sent_after_customer_observed_deceased", bad_count,
            "campaigns.build_campaigns zeroes counts where `deceased_day < month_end`; no touch "
            "should follow the month a deceased suppression was first observed")
    else:
        suite.check(g, "campaign_sent_after_customer_observed_deceased", True,
                    "0 deceased customers in this draw", "n/a",
                    "no deceased-suppressed customer in this draw to check against — vacuously fine")

    fat = camp.fatigue.to_numpy()
    bad = int(np.sum((fat < 0.12 - 1e-9) | (fat > 1.0 + 1e-9)))
    imp("fatigue_outside_documented_bounds", bad,
        "campaigns.FATIGUE_DECAY**k is floored at FATIGUE_FLOOR=0.12 and starts at 1.0 for k=0")

    bad = n((lab.contacts_30d > lab.contacts_90d) | (lab.contacts_90d > lab.campaign_contacts_6m))
    imp("contact_counters_not_monotonic_in_window", bad,
        "contacts_30d <= contacts_90d <= campaign_contacts_6m must hold: each counts the same touches "
        "over a wider trailing window")

    bad = n(lab.window_days != lab.contact_window_days)
    imp("label_window_alias_drift", bad, "window_days and contact_window_days are the same column "
        "written twice (DATA_CARD §12.1) and must never disagree")

    prod_cols = [f"label_product_{p}" for p in PRODUCTS]
    bad = n(lab[prod_cols].to_numpy().sum(axis=1) != lab.label_disbursed_in_window.to_numpy())
    imp("per_product_label_columns_do_not_sum_to_row_label", bad,
        "the six label_product_<p> columns must partition label_disbursed_in_window exactly")

    bad = n((lab.suppressed == 1) != (lab.suppression_reason != "none"))
    imp("suppressed_flag_disagrees_with_suppression_reason", bad,
        "suppressed is true iff suppression_reason is not 'none' (campaigns.py's own invariant)")

    positive = lab.label_disbursed_in_window == 1
    bad = n(positive & lab.label_product.isna())
    imp("positive_label_names_no_product", bad, "a positive row must name the product it disbursed")
    bad = n((~positive) & lab.label_product.notna())
    imp("negative_label_names_a_product", bad, "a negative row must not name a product")

    panel_start = pd.Timestamp(year=2024, month=4, day=1)
    if d.panel["date"].iloc[0] != "2024-04":
        # legacy anchor / a non-default calendar was used; infer it instead of hard-coding.
        y, m = str(d.panel["date"].iloc[0]).split("-")[:2]
        panel_start = pd.Timestamp(year=int(y), month=int(m), day=1)
    bad = n(started < panel_start - pd.Timedelta(seconds=1))
    imp("attempt_started_before_the_panel_begins", bad,
        "an application cannot start before the panel's own calendar does")

    last_stage_at = _dt(j.last_stage_at)
    bad = n(j.last_stage_at.notna() & j.started_at.notna() & (last_stage_at < started - pd.Timedelta(seconds=1)))
    imp("last_stage_reached_before_the_attempt_started", bad,
        "an attempt cannot reach any stage before it started")

    bad = n(b.gold_holding_g < 0)
    imp("negative_gold_holding", bad, "gold_holding_g is a lognormal draw, never negative by construction")
    bad = n(b.dependants < 0)
    imp("negative_dependants", bad, "dependants is a Poisson draw clipped to [0, 4]")
    bad = n(b.tenure_m.between(8, 179, inclusive="both") == False)  # noqa: E712
    imp("tenure_outside_drawn_range", bad, "tenure_m ~ U{8..179} (DATA_CARD §2)")

    n_impossible = suite.group_count(g)
    suite.check(g, "at_least_25_impossible_state_checks_ran", n_impossible >= 25, n_impossible,
                ">= 25", "SD-S7's brief: enumerate at least 25 impossible-state assertions")


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

CHECK_GROUPS: tuple[Callable[[Suite, Data], None], ...] = (
    check_funnel_shape,
    check_product_mix,
    check_time_to_disburse,
    check_upi_trend,
    check_salary_day,
    check_income_balance_correlation,
    check_emi_burden,
    check_marginals,
    check_seasonality,
    check_duplicate_keys,
    check_referential_integrity,
    check_impossible_states,
)


def run_suite(data: Data, verbose: bool = True) -> Suite:
    suite = Suite(verbose=verbose)
    check_seed_reproducibility(suite)
    for fn in CHECK_GROUPS:
        fn(suite, data)
    return suite


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="realism", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="directory holding the generated CSVs (default: data/); with --n, where "
                         "the fresh book is written (default: a temp directory)")
    ap.add_argument("--out", type=Path, default=None,
                    help="where to write the JSON report (default: <data-dir>/realism_report.json)")
    ap.add_argument("--n", type=int, default=None,
                    help="generate a fresh n-customer book + journey layer and audit that instead "
                         "of reading --data-dir")
    ap.add_argument("--months", type=int, default=30, help="panel months for --n (default: 30)")
    ap.add_argument("--seed", type=int, default=20260709, help="seed for --n (default: 20260709)")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-check PASS/FAIL lines")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.n is not None:
        gen_dir = args.data_dir if args.data_dir is not None else Path(
            tempfile.mkdtemp(prefix="sanket_realism_"))
        print(f"generating a fresh {args.n:,} x {args.months} book + journey layer "
              f"(seed {args.seed}) into {gen_dir} ...")
        t0 = time.perf_counter()
        generate_book_and_journeys(args.n, args.months, args.seed, gen_dir)
        print(f"generated in {time.perf_counter() - t0:.1f}s")
        data_dir = gen_dir
    else:
        data_dir = args.data_dir if args.data_dir is not None else ROOT / "data"

    print(f"loading {data_dir} ...")
    data = load_data(data_dir)

    t0 = time.perf_counter()
    suite = run_suite(data, verbose=not args.quiet)
    elapsed = time.perf_counter() - t0

    summary = suite.summary()
    print()
    print(f"{summary['passed']}/{summary['total']} checks passed in {elapsed:.1f}s "
          f"({summary['failed']} FAILED)")
    if suite.failed():
        print("\nFAILED checks:")
        for r in suite.failed():
            print(f"  - {r.group}/{r.name}: observed={r.observed} expected={r.expected}")
            print(f"    {r.rationale}")

    out = args.out if args.out is not None else data_dir / "realism_report.json"
    report = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_dir": str(data_dir),
        "elapsed_seconds": round(elapsed, 2),
        "summary": summary,
        "checks": [r.to_dict() for r in suite.results],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nreport written to {out}")

    return 0 if suite.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
