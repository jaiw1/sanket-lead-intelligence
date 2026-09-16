# Changelog — SANKET validation pack

## 2026-09-16 — Pre-registered before first model run.

25 acceptance criteria registered across the twelve runners, transcribed from
the approved build plan (§B lane L9, §D gates G3 and G7), **before any SANKET
model result existed**. Seven cuts, both splits, the per-product conversion
windows, the seed policy and the confidence-interval method fixed at the same
time. Runners are documented stubs; they report `pending`, never `pass`.

Notable registered positions, all taken before results:

- `SK-01`/`SK-02` the baseline (8–10%) and precision@10% (25–35%) registered
  separately, each with a **ceiling** — a book that converts too well fails.
- `SK-14` top-1 product accuracy registered with **no target**, so the menu of
  four is not quietly optimised back into a single recommendation.
- `SK-17` features drawing on post-`abandon_ts` information gated at **zero**.
- `SK-23`/`SK-24` fairness reported, not gated, including the gig-worker gap we
  disclose rather than tune away.
