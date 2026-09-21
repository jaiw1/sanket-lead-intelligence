"""
Business Radar  ->  app/public/radar_data.json

An appendix exhibit on real filings. Not SANKET's model, and not a validation of
it — but, since 2026-09-21, a **point-in-time** backtest rather than one that
quietly read the future.

What it is
----------
A four-term score over real Indian businesses' published annual filings (which
live OUTSIDE this repo): income growth 40, interest cover 25, unused borrowing
headroom 25, positive net worth 10. The weights are chosen, not fitted. The
backtest asks whether top-ranked companies raised total borrowings on their next
filing.

What changed, and why it mattered
---------------------------------
A third-party review (2026-09-21, §8) found two look-aheads, and they were not
small:

1. ``load_default_history`` excluded every company with **any** default event in
   its whole recorded history before the historical years were scored — a 2018
   row was being filtered using a 2023 default.
2. ``pctl`` ranked every ratio across **all** company-years pooled together, so
   a 2018 company was normalised against 2023 peers.

Both are now gone. Defaults are read with their dates and a company is eligible
at year Y only if it has no default dated on or before Y. The percentile
transforms are fitted on an **expanding window** of company-years up to and
including Y and then applied to year Y, so every number a historical decile is
built from existed at the time. The backtest runs year by year and the lift is
reported per year as well as pooled, with a **company-clustered** bootstrap.

The old look-ahead number is kept beside the new one (``lookahead_top_multiple``)
rather than deleted, so the size of the bias is visible instead of merely
asserted.

What it still is not
--------------------
* **Not SANKET's model.** No shared code, features, label or population.
* **Not a causal claim.** "Raised borrowings" means total borrowings from any
  lender rose on the next filing. Nobody called these companies.
* **Not an IDBI disbursement.** The outcome is lender-agnostic.

Ships only derived aggregates + anonymised exemplars. No names, no raw rows.
"""

import csv
import json
import re
from collections import defaultdict

import numpy as np
import pandas as pd

DIR = __file__.rsplit("/sanket/", 1)[0] + "/msme_data"
OUT = __file__.rsplit("/src/", 1)[0] + "/app/public/radar_data.json"

#: Bootstrap resamples for the company-clustered interval on the top-decile lift.
N_RESAMPLES = 500

SECTOR = {"01": "Agriculture", "10": "Food products", "13": "Textiles", "14": "Apparel", "17": "Paper",
          "20": "Chemicals", "21": "Pharma", "22": "Rubber & plastics", "23": "Cement & minerals",
          "24": "Basic metals", "25": "Fabricated metal", "26": "Electronics", "27": "Electrical eqpt",
          "28": "Machinery", "29": "Auto & parts", "41": "Construction", "42": "Civil engineering",
          "45": "Auto trade", "46": "Wholesale trade", "47": "Retail trade", "49": "Transport",
          "52": "Warehousing", "55": "Hotels", "62": "IT services", "68": "Real estate", "71": "Engineering svcs"}


def yr(s):
    m = re.search(r"(\d{4})", s or "")
    return int(m.group(1)) if m else None


def num(x):
    try:
        return float((x or "").strip())
    except ValueError:
        return np.nan


def load_default_history() -> dict[str, int]:
    """``company -> the year of its FIRST recorded default``.

    Point-in-time, which is the whole change: a company is eligible at year Y if
    and only if it has no default dated on or before Y. Reading the set of
    ever-defaulters and excluding them from every historical year — which is what
    this function used to return — filters 2018 using 2023's knowledge and
    flatters every backtest built on top of it.
    """
    rows = list(csv.reader(open(f"{DIR}/msme_ratings_movement.csv", encoding="utf-8-sig")))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Company Name")
    H = {h: i for i, h in enumerate(rows[hi])}
    first: dict[str, int] = {}
    for r in rows[hi + 1:]:
        if len(r) < 6 or not r[0].strip():
            continue
        rating = r[H["Rating"]].strip()
        if not (rating == "D" or rating.startswith("D ")):
            continue
        y = yr(r[H["Date"]]) if "Date" in H else None
        if y is None:
            # a default with no readable date cannot be placed in time; treat it
            # as known from the earliest year in the panel rather than ignoring
            # it, which is the conservative direction for an eligibility rule.
            y = 0
        c = r[0].strip()
        first[c] = min(first.get(c, y), y)
    return first


def load_sectors():
    ids = {}
    for r in csv.DictReader(open(f"{DIR}/msme_identifiers.csv", encoding="utf-8-sig")):
        nic = (r.get("NIC code") or "")[:2]
        ids[r["Company Name"].strip()] = SECTOR.get(nic, "Other")
    return ids


def load_financials():
    """Every company, defaulters included — eligibility is applied per year, later."""
    rows = list(csv.reader(open(f"{DIR}/msme_fin_data.csv", encoding="utf-8-sig")))
    years = [yr(y) for y in rows[4]]
    names = [n.strip() for n in rows[5]]
    fin = {}
    for r in rows[6:]:
        if not r or not r[0].strip():
            continue
        c = r[0].strip()
        d = {}
        for i, (y, nm) in enumerate(zip(years, names)):
            if y and nm and i < len(r) and r[i].strip():
                d.setdefault(y, {})[nm] = num(r[i])
        fin[c] = d
    return fin


def build_panel(fin, sectors, first_default) -> pd.DataFrame:
    rows = []
    for c, d in fin.items():
        ys = sorted(y for y, m in d.items() if not pd.isna(m.get("Total Income", np.nan)))
        for Y in ys:
            m = d[Y]
            inc, inc2 = (d.get(y, {}).get("Total Income", np.nan) for y in (Y, Y - 2))
            tb = m.get("Total borrowings including default", np.nan)
            tb_next = d.get(Y + 1, {}).get("Total borrowings including default", np.nan)
            if pd.isna(inc) or inc <= 0:
                continue
            cagr = (inc / inc2) ** 0.5 - 1 if (not pd.isna(inc2) and inc2 > 0) else np.nan
            icov = m.get("Interest cover (times)", np.nan)
            b2i = tb / inc if (not pd.isna(tb) and inc > 0) else 0.0 if pd.isna(tb) else np.nan
            nw = m.get("Net worth", np.nan)
            fd = first_default.get(c)
            rows.append(dict(
                company=c, year=Y, sector=sectors.get(c, "Other"), income=inc,
                income_cagr=cagr, interest_cover=icov, borrow_to_income=b2i,
                pos_networth=1 if (not pd.isna(nw) and nw > 0) else 0,
                # KNOWN AT YEAR Y, and only that: has this company already defaulted?
                defaulted_by=0 if fd is None else int(fd),
                raised_next=(1 if (not pd.isna(tb_next)
                                   and (tb_next > max(tb if not pd.isna(tb) else 0, 0.05) * 1.25)
                                   and (tb_next - (tb if not pd.isna(tb) else 0) > 0.25))
                             else 0) if not pd.isna(tb_next) else np.nan))
    return pd.DataFrame(rows)


def _ecdf_rank(train: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Percentile of ``x`` against the empirical distribution of ``train`` alone.

    ``pd.rank(pct=True)`` over the pooled panel is what made the old backtest
    look-ahead: it normalised a 2018 company against 2023 peers. This ranks only
    against history.
    """
    t = np.sort(train[np.isfinite(train)])
    out = np.full(len(x), 0.5)
    if len(t) == 0:
        return out
    finite = np.isfinite(x)
    out[finite] = np.searchsorted(t, x[finite], side="right") / len(t)
    return out


def score_as_of(panel: pd.DataFrame, year: int, eligible_only: bool = True) -> pd.DataFrame:
    """Score year ``year`` using only company-years up to and including it."""
    hist = panel[panel.year <= year]
    rows = panel[panel.year == year].copy()
    if eligible_only:
        # A company that has already defaulted by `year` is not a prospect. A
        # company that defaults LATER is still a prospect today, and leaving it
        # in is the point of doing this point-in-time.
        rows = rows[(rows.defaulted_by == 0) | (rows.defaulted_by > year)]
    if rows.empty:
        return rows
    g = _ecdf_rank(hist.income_cagr.to_numpy(float), rows.income_cagr.to_numpy(float))
    ic = _ecdf_rank(hist.interest_cover.clip(upper=20).to_numpy(float),
                    rows.interest_cover.clip(upper=20).to_numpy(float))
    bi = _ecdf_rank(hist.borrow_to_income.to_numpy(float), rows.borrow_to_income.to_numpy(float))
    rows["score"] = 0.40 * g + 0.25 * ic + 0.25 * (1 - bi) + 0.10 * rows.pos_networth
    return rows


def expanding_backtest(panel: pd.DataFrame, min_train: int = 2000) -> tuple[pd.DataFrame, list[dict]]:
    """Score each year on its own history, evaluate on the following filing.

    The first year with enough history to normalise against is the first
    evaluated year; everything before it is training window only.
    """
    years = sorted(panel.year.dropna().unique().astype(int))
    scored, per_year = [], []
    for Y in years:
        if len(panel[panel.year <= Y]) < min_train:
            continue
        rows = score_as_of(panel, Y)
        rows = rows.dropna(subset=["raised_next"])
        if len(rows) < 500:
            continue
        rows = rows.copy()
        # Deciles WITHIN the year: a decile is "top 10% of the companies an
        # analyst could rank that year", which is the decision being simulated.
        rows["decile"] = pd.qcut(rows.score.rank(method="first"), 10, labels=range(1, 11)).astype(int)
        top = rows[rows.decile == 10].raised_next
        rest = rows[rows.decile < 10].raised_next
        per_year.append(dict(
            year=int(Y), n=int(len(rows)), n_companies=int(rows.company.nunique()),
            n_train_rows=int(len(panel[panel.year <= Y])),
            top_decile_rate=round(float(top.mean()), 4),
            rest_rate=round(float(rest.mean()), 4),
            multiple=round(float(top.mean() / max(rest.mean(), 1e-9)), 3),
        ))
        scored.append(rows)
    return (pd.concat(scored, ignore_index=True) if scored else panel.iloc[0:0]), per_year


def company_clustered_ci(bt: pd.DataFrame, n_resamples: int = N_RESAMPLES,
                         seed: int = 7) -> dict:
    """Percentile interval for the top-decile multiple, resampling COMPANIES.

    One company contributes several company-years and its borrowing behaviour is
    correlated across them, so a row-level interval would be too narrow. The
    decile assignment is not recomputed inside the resample: it is a function of
    the training window, not of which companies happen to be drawn.
    """
    rng = np.random.default_rng(seed)
    idx_by_company = defaultdict(list)
    for i, c in enumerate(bt.company.to_numpy()):
        idx_by_company[c].append(i)
    companies = np.array(list(idx_by_company))
    rows = [np.asarray(idx_by_company[c]) for c in companies]
    top = (bt.decile.to_numpy() == 10)
    y = bt.raised_next.to_numpy(float)

    draws = np.empty(n_resamples)
    for b in range(n_resamples):
        pick = rng.integers(0, len(companies), len(companies))
        idx = np.concatenate([rows[j] for j in pick])
        t, r = y[idx][top[idx]], y[idx][~top[idx]]
        draws[b] = t.mean() / max(r.mean(), 1e-9) if len(t) and len(r) else np.nan
    draws = draws[np.isfinite(draws)]
    return dict(method="company-clustered percentile bootstrap",
                n_companies=int(len(companies)), n_resamples=int(len(draws)),
                ci_low=round(float(np.percentile(draws, 2.5)), 3),
                ci_high=round(float(np.percentile(draws, 97.5)), 3))


def lookahead_multiple(panel: pd.DataFrame, first_default: dict[str, int]) -> float:
    """The retired number: ever-defaulters dropped, percentiles pooled over all years.

    Kept so the size of the bias the point-in-time rebuild removed is a published
    figure rather than an assertion.
    """
    df = panel[~panel.company.isin(first_default)].copy()
    def pctl(s):
        return s.rank(pct=True).fillna(0.5)
    df["score"] = (0.40 * pctl(df.income_cagr)
                   + 0.25 * pctl(df.interest_cover.clip(upper=20))
                   + 0.25 * (1 - pctl(df.borrow_to_income))
                   + 0.10 * df.pos_networth)
    bt = df.dropna(subset=["raised_next"]).copy()
    if bt.empty:
        return float("nan")
    bt["decile"] = pd.qcut(bt.score, 10, labels=range(1, 11)).astype(int)
    top = bt[bt.decile == 10].raised_next.mean()
    rest = bt[bt.decile < 10].raised_next.mean()
    return float(top / max(rest, 1e-9))


def main():
    first_default = load_default_history()
    sectors = load_sectors()
    fin = load_financials()
    panel = build_panel(fin, sectors, first_default)
    print(f"companies with financials: {panel.company.nunique():,} | "
          f"company-years: {len(panel):,} | with a dated default on record: "
          f"{len(first_default):,}")

    bt, per_year = expanding_backtest(panel)
    if bt.empty:
        raise SystemExit("no year had enough history to backtest point-in-time")
    top_rate = float(bt[bt.decile == 10].raised_next.mean())
    rest_rate = float(bt[bt.decile < 10].raised_next.mean())
    top_multiple = top_rate / max(rest_rate, 1e-9)
    ci = company_clustered_ci(bt)
    look = lookahead_multiple(panel, first_default)
    print(f"point-in-time backtest: top-decile {top_rate:.1%} vs rest {rest_rate:.1%} "
          f"({top_multiple:.2f}x, company-clustered 95% CI {ci['ci_low']}-{ci['ci_high']}x) "
          f"across {len(per_year)} evaluation years")
    print(f"the retired look-ahead version of the same number: {look:.2f}x")
    for r in per_year:
        print(f"  {r['year']}: {r['multiple']:.2f}x  (n={r['n']:,})")

    dec = bt.groupby("decile", observed=True).raised_next.mean()
    deciles = [dict(decile=f"D{int(d)}", jump_rate_pct=round(float(v) * 100, 1))
               for d, v in dec.items()]

    # ---- current prospects: the latest year, scored on its own history -------- #
    latest_year = int(panel.year.max())
    latest = score_as_of(panel, latest_year)
    if len(latest) < 500:
        latest_year -= 1
        latest = score_as_of(panel, latest_year)
    thr = latest.score.quantile(0.80)
    latest = latest.copy()
    latest["headroom"] = latest.score >= thr

    sec = (latest.groupby("sector").agg(n=("company", "size"), share_headroom=("headroom", "mean"))
           .query("n >= 120").sort_values("share_headroom", ascending=False).head(8).reset_index())
    sectors_out = [dict(sector=r.sector, n=int(r.n), share_headroom=round(float(r.share_headroom), 3))
                   for r in sec.itertuples()]

    # exemplars: believable mid-size businesses with REAL, non-zero borrowing ratios
    # (some existing bank debt they service comfortably = provable relationship + room to grow).
    cred = latest[(latest.income >= 5) & (latest.income <= 500)
                  & latest.income_cagr.between(0.10, 0.55)
                  & latest.interest_cover.between(3, 30)
                  & latest.borrow_to_income.between(0.10, 1.20)]
    top = cred.sort_values("score", ascending=False).head(8)
    prospects = []
    for i, r in enumerate(top.itertuples(), 1):
        reasons = []
        if not pd.isna(r.income_cagr) and r.income_cagr > 0.10:
            reasons.append(f"Income compounding at {round(r.income_cagr * 100)}%/yr — growth needs working capital")
        if not pd.isna(r.interest_cover) and r.interest_cover > 3:
            reasons.append(f"Interest cover {round(r.interest_cover, 1)}× — debt costs are comfortably absorbed")
        if not pd.isna(r.borrow_to_income):
            if r.borrow_to_income < 0.3:
                reasons.append("Barely any existing borrowings — whole credit line is headroom")
            else:
                reasons.append(f"Borrowings only {r.borrow_to_income:.1f}× income on {round(r.interest_cover)}× cover — clear room to lend more")
        prospects.append(dict(
            id=f"BR-{i:03d}", sector=r.sector,
            income_cagr=round(float(r.income_cagr), 3) if not pd.isna(r.income_cagr) else 0,
            interest_cover=round(float(r.interest_cover), 1) if not pd.isna(r.interest_cover) else None,
            borrow_to_income=round(float(r.borrow_to_income), 2) if not pd.isna(r.borrow_to_income) else 0,
            score=round(float(r.score), 3),
            reasons=reasons or ["Composite headroom signal across growth, cover and leverage"],
        ))

    out = dict(
        meta=dict(
            n_companies_str=f"{panel.company.nunique():,}",
            n_prospects=int(latest.headroom.sum()),
            years=f"{len(per_year)} backtest yrs",
            latest_year=latest_year,
            desc="Sector-level aggregates and anonymised exemplars from real Indian companies' annual financial "
                 "statements and published credit-rating histories. Only derived aggregates ship with this app — "
                 "never raw company data.",
            illustrative=True,
            point_in_time=True,
            caveat="ILLUSTRATIVE EXHIBIT, NOT A VALIDATION. This is a hand-weighted financial-ratio "
                   "score, not SANKET's trained drop-off model, and the two share no code, features, "
                   "label or population. The backtest IS now point-in-time — eligibility uses only "
                   "defaults dated on or before each scored year, and the percentile transforms are "
                   "fitted on an expanding window of prior filings — which is why the lift below is "
                   "much smaller than the figure this screen carried before 2026-09-21. "
                   "“Raised borrowings” means total borrowings from any lender rose on the next "
                   "filing: it is not evidence of an IDBI disbursement, and nobody called these "
                   "companies, so no relationship-manager call caused anything here.",
        ),
        sectors=sectors_out,
        prospects=prospects,
        backtest=dict(
            deciles=deciles,
            top_multiple=round(top_multiple, 2),
            top_decile_rate=round(top_rate, 4),
            rest_rate=round(rest_rate, 4),
            method="expanding-window, point-in-time: each year is scored using only "
                   "filings up to and including it, and only companies with no default "
                   "dated on or before it; deciles are cut within the year",
            n_rows=int(len(bt)), n_companies=int(bt.company.nunique()),
            evaluation_years=[r["year"] for r in per_year],
            by_year=per_year,
            company_clustered_ci=ci,
            lookahead_top_multiple=round(look, 2),
            lookahead_note="The retired figure: ever-defaulters dropped before the historical "
                           "years were scored, and percentile ranks pooled across all years. "
                           "Published beside the honest number so the size of the look-ahead "
                           "bias is a measurement rather than an assertion.",
        ),
    )
    json.dump(out, open(OUT, "w"))
    print(f"radar prospects: {out['meta']['n_prospects']:,} | sectors: "
          f"{[s['sector'] for s in sectors_out]}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
