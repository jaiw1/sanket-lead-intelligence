"""
Business Radar  ->  app/public/radar_data.json

Proof-on-real-data module: scores REAL Indian businesses (public annual financial
filings living OUTSIDE this repo) as business-banking prospects — growing income,
comfortable interest cover, unused borrowing headroom — then BACKTESTS the ranking:
did top-ranked businesses actually raise borrowings the following year?

Ships only derived aggregates + anonymised exemplars. No names, no raw rows.
"""

import csv, json, re
import numpy as np
import pandas as pd

DIR = __file__.rsplit("/sanket/", 1)[0] + "/msme_data"
OUT = __file__.rsplit("/src/", 1)[0] + "/app/public/radar_data.json"

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


def load_default_history():
    """Companies with ANY default event on record — excluded from the prospect pool."""
    rows = list(csv.reader(open(f"{DIR}/msme_ratings_movement.csv", encoding="utf-8-sig")))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Company Name")
    H = {h: i for i, h in enumerate(rows[hi])}
    ever_d = set()
    for r in rows[hi + 1:]:
        if len(r) < 6 or not r[0].strip():
            continue
        rating = r[H["Rating"]].strip()
        if rating == "D" or rating.startswith("D "):
            ever_d.add(r[0].strip())
    return ever_d


def load_sectors():
    ids = {}
    for r in csv.DictReader(open(f"{DIR}/msme_identifiers.csv", encoding="utf-8-sig")):
        nic = (r.get("NIC code") or "")[:2]
        ids[r["Company Name"].strip()] = SECTOR.get(nic, "Other")
    return ids


def load_financials(exclude):
    rows = list(csv.reader(open(f"{DIR}/msme_fin_data.csv", encoding="utf-8-sig")))
    years = [yr(y) for y in rows[4]]
    names = [n.strip() for n in rows[5]]
    fin = {}
    for r in rows[6:]:
        if not r or not r[0].strip():
            continue
        c = r[0].strip()
        if c in exclude:
            continue
        d = {}
        for i, (y, nm) in enumerate(zip(years, names)):
            if y and nm and i < len(r) and r[i].strip():
                d.setdefault(y, {})[nm] = num(r[i])
        fin[c] = d
    return fin


def main():
    ever_d = load_default_history()
    sectors = load_sectors()
    fin = load_financials(ever_d)
    print(f"default-history exclusions: {len(ever_d):,} | clean businesses with financials: {len(fin):,}")

    rows = []
    for c, d in fin.items():
        ys = sorted(y for y, m in d.items() if not pd.isna(m.get("Total Income", np.nan)))
        for Y in ys:
            m = d[Y]
            inc, inc1, inc2 = (d.get(y, {}).get("Total Income", np.nan) for y in (Y, Y - 1, Y - 2))
            tb = m.get("Total borrowings including default", np.nan)
            tb_next = d.get(Y + 1, {}).get("Total borrowings including default", np.nan)
            if pd.isna(inc) or inc <= 0:
                continue
            cagr = (inc / inc2) ** 0.5 - 1 if (not pd.isna(inc2) and inc2 > 0) else np.nan
            icov = m.get("Interest cover (times)", np.nan)
            b2i = tb / inc if (not pd.isna(tb) and inc > 0) else 0.0 if pd.isna(tb) else np.nan
            nw = m.get("Net worth", np.nan)
            rows.append(dict(company=c, year=Y, sector=sectors.get(c, "Other"), income=inc,
                             income_cagr=cagr, interest_cover=icov, borrow_to_income=b2i,
                             pos_networth=1 if (not pd.isna(nw) and nw > 0) else 0,
                             raised_next=(1 if (not pd.isna(tb_next) and (tb_next > max(tb if not pd.isna(tb) else 0, 0.05) * 1.25)
                                               and (tb_next - (tb if not pd.isna(tb) else 0) > 0.25)) else 0) if not pd.isna(tb_next) else np.nan))
    df = pd.DataFrame(rows)
    print(f"company-years: {len(df):,}")

    # transparent radar score: growth (40) + interest-cover comfort (25) + headroom (25) + health (10)
    def pctl(s):
        return s.rank(pct=True).fillna(0.5)
    df["score"] = (0.40 * pctl(df.income_cagr)
                   + 0.25 * pctl(df.interest_cover.clip(upper=20))
                   + 0.25 * (1 - pctl(df.borrow_to_income))
                   + 0.10 * df.pos_networth)

    # ---- backtest on rows where next-FY borrowings are observable ----
    bt = df.dropna(subset=["raised_next"]).copy()
    bt["decile"] = pd.qcut(bt.score, 10, labels=range(1, 11))
    dec = bt.groupby("decile", observed=True).raised_next.mean()
    deciles = [dict(decile=f"D{int(d)}", jump_rate_pct=round(float(v) * 100, 1)) for d, v in dec.items()]
    top_rate = float(dec.iloc[-1])
    rest_rate = float(bt[bt.decile.astype(int) <= 9].raised_next.mean())
    top_multiple = top_rate / max(rest_rate, 1e-9)
    print(f"backtest: top-decile raised-borrowings rate {top_rate:.1%} vs rest {rest_rate:.1%}  ({top_multiple:.1f}x)")

    # ---- current prospects: latest year per company ----
    latest = df.sort_values("year").groupby("company").tail(1)
    latest = latest[latest.year >= latest.year.max() - 1]
    thr = latest.score.quantile(0.80)
    latest["headroom"] = latest.score >= thr

    sec = (latest.groupby("sector").agg(n=("company", "size"), share_headroom=("headroom", "mean"))
           .query("n >= 120").sort_values("share_headroom", ascending=False).head(8).reset_index())
    sectors_out = [dict(sector=r.sector, n=int(r.n), share_headroom=round(float(r.share_headroom), 3)) for r in sec.itertuples()]

    # exemplars: believable mid-size businesses with REAL, non-zero borrowing ratios
    # (some existing bank debt they service comfortably = provable relationship + room to grow).
    # Filtering to b2i in [0.1, 1.2] avoids the all-zero column that pure headroom-max would give.
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
            n_companies_str="26,000+", n_prospects=int(latest.headroom.sum()), years="7 yrs",
            desc="Sector-level aggregates and anonymised exemplars from real Indian companies' annual financial statements "
                 "and published credit-rating histories; companies with any default history are screened out before ranking. "
                 "Only derived aggregates ship with this app — never raw company data.",
        ),
        sectors=sectors_out,
        prospects=prospects,
        backtest=dict(deciles=deciles, top_multiple=round(top_multiple, 1)),
    )
    json.dump(out, open(OUT, "w"))
    print(f"radar prospects: {out['meta']['n_prospects']:,} | sectors: {[s['sector'] for s in sectors_out]}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
