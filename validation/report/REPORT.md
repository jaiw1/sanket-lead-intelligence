# SANKET — validation report

**Verdict: PASS**  ·  16 pass · 0 fail · 0 warn · 0 pending · 0 skipped · 9 reported

## Pre-registration

These 25 acceptance bands were registered at **2026-09-16T10:47:14+05:30** by RR Squad, before any model result for SANKET existed.

`validation/criteria.yaml` first entered git at **2026-09-16T11:06:09+05:30** — that commit timestamp, not this file, is the evidence. This report was generated at 2026-09-21T17:01:58+05:30 from commit `109e5e2b97f5`.

**Amendments after registration:**
- *2026-09-21T00:00:00+05:30* (RR Squad — third-party review response) — DESCRIPTION ONLY. SK-04's threshold (>= 0.90), op, severity, runner, metric key and scope are all unchanged. What changed is the wording: the rationale used to say the criterion existed so "the RM queue's SLA" would not be "fiction", which reads as a claim that SK-04 measures whether a relationship manager made contact before the lead expired. It does not. It measures conversion timing among converters — of the held-out rows inside the contact budget that disbursed, the share that disbursed inside the offered product's window. The note now states that explicitly, and states that contact-SLA compliance is measured nowhere in this pack. Rationale: A third-party review (2026-09-21, §5) found the 90.1% being described as an operational contact-SLA result in the README, the model card and the cockpit. No contact timestamp exists in this pipeline, so that reading is unsupported by anything in the repo. The band itself was never the problem and is deliberately left where it was registered; loosening or retitling a metric because its description was wrong would be the exact move pre-registration exists to prevent.
- *2026-09-16T00:00:00+05:30* (RR Squad — architect ruling) — SCOPING, NOT THRESHOLDS. No band moves. SK-01 stays [0.08, 0.10], SK-02 stays [0.25, 0.35], SK-18 stays [0.48, 0.52], SK-17 stays 0 — all `fail`, all with their ceilings. What is amended is the SCORING POPULATION SK-01 and SK-02 are computed over, which was under-specified at registration because this file was written before the application-journey layer (plan §B L6 SD-S2) existed and so before there was a drop-off population to name. The same entry re-points runner 07 at the files that layer actually emitted; SK-17 and SK-18 are listed only because that runner answers them, and neither band changes.

ORIGINAL WORDING (registered 2026-09-16T10:47:14+05:30). `label_definition.observation_unit`: "One (cust_id, month) row of the liability book at a snapshot month m. The model scores a consented customer as at m using only information available at or before m." `label_definition.primary.description`: "CONVERSION MEANS DISBURSEMENT, not lead creation and not application start (mentor mandate). 1 if, after being contacted at month m, the customer's application for the offered product reaches the Disburse stage within that product's pre-registered window; 0 otherwise, including applications that start and then abandon." `splits.holdout.scoring_population`: "Held-out, consented customers at the snapshot month. Precision-at-budget is computed on this population; the cockpit queue is built over the whole book but is never a measurement surface." `validation/runners/07_leakage.py` INPUTS: "data/application_journeys.csv  (PLANNED — plan §B L6 SD-S2)".

NEW WORDING. The scoring unit is a (customer, month) row for customers in the DROP-OFF POPULATION — consented, contactable customers with at least one abandoned application attempt in the trailing 12 months and no disbursement in flight — and the label is disbursement of any product within that product's decision window after an RM contact (windows in days: personal 1, gold 1, auto 3, education 7, home 14, lap 14 — unchanged, and unchanged from `conversion_windows_days` above). `random_contact_disbursement_rate` (SK-01) is the disbursement rate among a uniformly random 10% contact sample of that population. `precision_at_10pct_budget` (SK-02) is the same population, model-ranked at the same 10% contact budget. Runner 07's data path becomes `data/journeys.csv` + `data/journey_events.csv` (the alias columns SD-S2 emitted for the pre-registered spelling — cust_id, stage_reached, start_ts, abandon_ts, disburse_ts, blank_ratio, income_refused, revisit_count — stay); only the path and the column mapping change, not the leakage logic. Rationale: The mentors defined conversion as disbursement and said in terms that "the population that matters is the drop-offs". The RM-call baseline of 8-10% is a statement about CALLED PROSPECTS, not about every consented customer-month: on the whole book that rate is ~0.1% at a snapshot month (1.35% even at the three-month horizon the old pipeline measured), which would force the contact effect theta to a value no bank reviewer would accept in order to reach 8%. The business action being priced is an RM working a lead list, not ringing 60,000 savings customers, so the denominator has to be the lead list. Recorded as an amendment rather than applied as a reinterpretation because the population is part of what a pre-registered metric means, and changing it quietly — even without touching a threshold — is exactly the move pre-registration exists to prevent. Generator side: plan §B L6 SD-S4 solves theta against this population and asserts both bands in-script (`src/journeys/labels.py`, `check()`), across five seeds; `DATA_CARD.md` §12 documents the label, the two solved knobs and the known unrealisms that come with them.

## All criteria

**About the `Interval` column.** It is not always a confidence interval, and the `Detail` column on every row says which of the three kinds it is. In preference order: (1) the **customer-clustered percentile bootstrap** `criteria.yaml confidence.method` registers — `cust_id` resampled with replacement and the queue re-selected by `model.policy` inside every resample — available for the headline precision and baseline numbers, and a genuine 95% confidence interval around `Observed`; (2) the **5-seed spread**, the 2.5-97.5 percentile of the metric across the registered seeds [7, 8, 9, 10, 11], which measures *training-seed variability* and is **not** a confidence interval — `Observed` is always the packed seed (seed 7) and can fall outside it, which is a property of a five-point percentile interval rather than a defect; (3) the packed seed's own 95% Wilson or Hanley-McNeil interval, for the metrics neither of the first two covers. Generator variability is a fourth question again and is reported separately in `metrics.uncertainty.generator`, never merged into any of these.

### 01_holdout

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-01 | random_contact_disbursement_rate | overall | ∈ [0.08, 0.1] | 0.0948 | [0.0901, 0.0998] | 29154 | fail | PASS |
| SK-02 | precision_at_10pct_budget | overall | ∈ [0.25, 0.35] | 0.2906 | [0.2676, 0.3118] | 2915 | fail | PASS |
| SK-03 | precision_at_5pct_and_20pct_budget | overall | reported, no target | {'precision_at_5pct': 0.358, 'precision_at_20pct': 0.2301} | — | — | report | reported |
| SK-04 | window_respect_rate | overall | ≥ 0.9 | 0.9009 | [0.8697, 0.899] | 908 | fail | PASS |
| SK-05 | window_shopper_auc | overall | ≥ 0.7 | 0.847 | [0.8416, 0.8525] | 29154 | fail | PASS |
| SK-06 | baseline_ladder_headline_uplift | overall | reported, no target | 9 → 29 disbursements per 100 RM calls | — | — | report | reported |

<details><summary>SK-03 — per-cell breakdown (2 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| precision_at_5pct | 0.358 | [0.3212, 0.3916] | 1458 | reported |
| precision_at_20pct | 0.2301 | [0.2144, 0.2458] | 5831 | reported |

</details>

### 02_oot

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-07 | oot_precision_at_10pct_degradation_pp | overall | ≤ 5.0 | -0.7982 | — | 11017 | fail | PASS |

### 03_by_cut

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-08 | auc | per_product | ≥ 0.75 | 0.804 | [0.8002, 0.8135] | 29154 | fail | PASS |
| SK-09 | macro_auc | overall | ≥ 0.78 | 0.8648 | [0.8637, 0.8714] | 29154 | fail | PASS |
| SK-10 | auc_and_precision_at_10pct | per_cut (all) | reported, no target | 33 cells across 7 registered cuts | — | — | report | reported |

<details><summary>SK-08 — per-cell breakdown (6 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| home | 0.9307 | [0.9263, 0.9419] | 29154 | PASS |
| lap | 0.8466 | [0.8482, 0.9041] | 29154 | PASS |
| gold | 0.8428 | [0.8254, 0.8522] | 29154 | PASS |
| auto | 0.8923 | [0.8831, 0.8945] | 29154 | PASS |
| education | 0.8721 | [0.8546, 0.8709] | 29154 | PASS |
| personal | 0.804 | [0.8002, 0.8135] | 29154 | PASS |

</details>

<details><summary>SK-10 — per-cell breakdown (33 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| product:home | AUC 0.9307 · precision@10% 0.1187 | — | 29154 | reported |
| product:lap | AUC 0.8466 · precision@10% 0.0367 | — | 29154 | reported |
| product:gold | AUC 0.8428 · precision@10% 0.0652 | — | 29154 | reported |
| product:auto | AUC 0.8923 · precision@10% 0.1087 | — | 29154 | reported |
| product:education | AUC 0.8721 · precision@10% 0.0892 | — | 29154 | reported |
| product:personal | AUC 0.804 · precision@10% 0.1341 | — | 29154 | reported |
| channel:app | AUC 0.7105 · precision@10% 0.2207 | [0.6886, 0.7324] | 8877 | reported |
| channel:branch-walk-in | AUC 0.7443 · precision@10% 0.3388 | [0.7228, 0.7657] | 6049 | reported |
| channel:dsa | AUC 0.6817 · precision@10% 0.1873 | [0.6441, 0.7194] | 3311 | reported |
| channel:rm-call | AUC 0.7616 · precision@10% 0.3667 | [0.7395, 0.7836] | 5397 | reported |
| channel:web | AUC 0.7272 · precision@10% 0.2156 | [0.6989, 0.7554] | 5520 | reported |
| occupation_segment:gig | AUC 0.7368 · precision@10% 0.2883 | [0.7076, 0.766] | 4437 | reported |
| occupation_segment:salaried | AUC 0.7368 · precision@10% 0.2805 | [0.7229, 0.7507] | 17611 | reported |
| occupation_segment:self-employed | AUC 0.737 · precision@10% 0.3108 | [0.7147, 0.7594] | 7106 | reported |
| income_band:Q1 | AUC 0.7419 · precision@10% 0.2899 | [0.7162, 0.7676] | 5831 | reported |
| income_band:Q2 | AUC 0.7533 · precision@10% 0.2985 | [0.7305, 0.776] | 5831 | reported |
| income_band:Q3 | AUC 0.7172 · precision@10% 0.2487 | [0.6918, 0.7427] | 5830 | reported |
| income_band:Q4 | AUC 0.7277 · precision@10% 0.2933 | [0.703, 0.7524] | 5831 | reported |
| income_band:Q5 | AUC 0.7345 · precision@10% 0.3087 | [0.7102, 0.7589] | 5831 | reported |
| tenure_band:6-12m | AUC 0.7305 · precision@10% 0.2113 | [0.6498, 0.8112] | 712 | reported |
| tenure_band:12-24m | AUC 0.7252 · precision@10% 0.3039 | [0.6848, 0.7656] | 2043 | reported |
| tenure_band:24-36m | AUC 0.7204 · precision@10% 0.2476 | [0.6805, 0.7602] | 2096 | reported |
| tenure_band:36m+ | AUC 0.7391 · precision@10% 0.2951 | [0.727, 0.7511] | 24303 | reported |
| stage_reached:accept | AUC 0.6909 · precision@10% 0.3762 | [0.6569, 0.7249] | 2021 | reported |
| stage_reached:docs | AUC 0.7367 · precision@10% 0.2179 | [0.7101, 0.7632] | 6700 | reported |
| stage_reached:eligibility | AUC 0.7138 · precision@10% 0.2281 | [0.6786, 0.7491] | 3989 | reported |
| stage_reached:fee | AUC 0.7077 · precision@10% 0.2673 | [0.6836, 0.7318] | 5654 | reported |
| stage_reached:kyc | AUC 0.7164 · precision@10% 0.2318 | [0.6788, 0.754] | 3024 | reported |
| stage_reached:offer | AUC 0.7244 · precision@10% 0.3985 | [0.6958, 0.753] | 2658 | reported |
| stage_reached:start | AUC 0.7161 · precision@10% 0.2779 | [0.6878, 0.7444] | 5108 | reported |
| city_tier:1 | AUC 0.7229 · precision@10% 0.2681 | [0.7051, 0.7407] | 11080 | reported |
| city_tier:2 | AUC 0.7457 · precision@10% 0.3119 | [0.7287, 0.7626] | 12116 | reported |
| city_tier:3 | AUC 0.7443 · precision@10% 0.2919 | [0.7199, 0.7687] | 5958 | reported |

</details>

### 04_calibration

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-11 | ece | overall | ≤ 0.03 | 0.0072 | [0.0054, 0.0104] | 29154 | fail | PASS |
| SK-12 | ece | per_product | ≤ 0.03 | 0.0027 | — | 29154 | fail | PASS |

<details><summary>SK-12 — per-cell breakdown (6 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| home | 0.0017 | — | 29154 | PASS |
| lap | 0.001 | — | 29154 | PASS |
| gold | 0.002 | — | 29154 | PASS |
| auto | 0.0019 | — | 29154 | PASS |
| education | 0.0027 | — | 29154 | PASS |
| personal | 0.0025 | — | 29154 | PASS |

</details>

### 05_rank_order

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-13 | menu_of_4_hit_rate | overall | ≥ 0.8 | 0.9649 | [0.9649, 0.9738] | 2764 | fail | PASS |
| SK-14 | top_1_product_accuracy | overall | reported, no target | 0.7044 | [0.6871, 0.7211] | 2764 | report | reported |
| SK-15 | shopper_signal_negative_direction_count | overall | ≥ 4 | 4 | — | 12000 | fail | PASS |

### 06_stability

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-16 | psi_score_distribution | overall | ≤ 0.1 | 0.0088 | — | 29154 | fail | PASS |

### 07_leakage

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-17 | features_using_post_abandon_information | overall | = 0 | 0 | — | 1075580 | fail | PASS |
| SK-18 | permuted_label_auc | overall | ∈ [0.48, 0.52] | 0.5062 | — | — | fail | PASS |

<details><summary>SK-17 — per-cell breakdown (2 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| forbidden_input_names | 0 | — | 60 | PASS |
| journey_feature_truncation_diff | 0 | — | 1075580 | PASS |

</details>

### 08_ablation

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-19 | precision_at_10pct_drop_by_feature_family | overall | reported, no target | {'income': 1.02, 'balance': -2.03, 'outflow': 0.51, 'debt': -2.79, 'life_event': 0.51, 'profile': -0.25, 'journey': 1.53, 'shopper': 6.86, 'contact': 0.77, 'product': -2.28} | — | — | report | reported |

<details><summary>SK-19 — per-cell breakdown (10 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| income | 1.02 | [0.164, 0.2428] | 394 | reported |
| balance | -2.03 | [0.1921, 0.2751] | 394 | reported |
| outflow | 0.51 | [0.1686, 0.2482] | 394 | reported |
| debt | -2.79 | [0.1991, 0.2831] | 394 | reported |
| life_event | 0.51 | [0.1686, 0.2482] | 394 | reported |
| profile | -0.25 | [0.1756, 0.2563] | 394 | reported |
| journey | 1.53 | [0.1593, 0.2374] | 394 | reported |
| shopper | 6.86 | [0.1111, 0.1801] | 394 | reported |
| contact | 0.77 | [0.1663, 0.2455] | 394 | reported |
| product | -2.28 | [0.1944, 0.2777] | 394 | reported |

</details>

### 09_seeds

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-20 | n_seeds_run | overall | ≥ 5 | 5 | — | 5 | fail | PASS |
| SK-21 | cross_seed_precision_at_10pct_ci_width_pp | overall | ≤ 4.0 | 1.4639 | — | 5 | fail | PASS |

### 10_stress

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-22 | precision_at_10pct_under_stress_scenarios | overall | reported, no target | {'2x_base_rate_reweight_positives': 1.52, 'channel_missing_contact': 0.0} | — | — | report | reported |

<details><summary>SK-22 — per-cell breakdown (2 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| 2x_base_rate_reweight_positives | 1.52 | [0.1874, 0.2697] | 394 | reported |
| channel_missing_contact | 0 | [0.1733, 0.2536] | 394 | reported |

</details>

### 11_fairness

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-23 | adverse_impact_ratio | per_cut (protected_proxies) | ≥ 0.8 | 0.69 | — | 815 | report | reported |
| SK-24 | gig_worker_failure_disclosure | overall | must exist | yes | — | — | report | reported |

<details><summary>SK-23 — per-cell breakdown (14 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| Segment:gig | 0.69 | — | 815 | reported |
| Segment:salaried | 1 | — | 3341 | reported |
| Segment:self-employed | 0.81 | — | 1373 | reported |
| City tier:1 | 1 | — | 2085 | reported |
| City tier:2 | 0.92 | — | 2282 | reported |
| City tier:3 | 0.84 | — | 1162 | reported |
| Age band:21-30 | 0.97 | — | 1622 | reported |
| Age band:31-45 | 1 | — | 3144 | reported |
| Age band:46+ | 0.91 | — | 763 | reported |
| Income band:Q1 lowest | 0.79 | — | 1106 | reported |
| Income band:Q2 | 0.87 | — | 1106 | reported |
| Income band:Q3 | 1 | — | 1105 | reported |
| Income band:Q4 | 0.93 | — | 1106 | reported |
| Income band:Q5 highest | 0.91 | — | 1106 | reported |

</details>

### 12_baseline_ladder

| ID | Metric | Scope | Band | Observed | Interval | n | Severity | Status |
|---|---|---|---|---|---|---|---|---|
| SK-25 | precision_at_10pct_by_baseline_rung | overall | reported, no target | [{'level': 'random contact', 'value': 0.0948, 'n': 2915, 'ci': [0.084581, 0.105851], 'status': 'report'}, {'level': 'balance-ranked (what a branch does today)', 'value': 0.0995, 'n': 2915, 'ci': [0.089141, 0.110884], 'status': 'report'}, {'level': 'logistic scorecard', 'value': 0.2583, 'n': 2915, 'ci': [0.242755, 0.27452], 'status': 'report'}, {'level': 'SANKET (one LightGBM, six products)', 'value': 0.2906, 'n': 2915, 'ci': [0.274368, 0.307315], 'status': 'report'}] | — | — | report | reported |

<details><summary>SK-25 — per-cell breakdown (4 cells)</summary>

| Cell | Observed | Interval | n | Status |
|---|---|---|---|---|
| random contact | 0.0948 | [0.0846, 0.1059] | 2915 | reported |
| balance-ranked (what a branch does today) | 0.0995 | [0.0891, 0.1109] | 2915 | reported |
| logistic scorecard | 0.2583 | [0.2428, 0.2745] | 2915 | reported |
| SANKET (one LightGBM, six products) | 0.2906 | [0.2744, 0.3073] | 2915 | reported |

</details>

## Why each band is what it is

Registered rationale, verbatim from `criteria.yaml`. Notes record where a band's wording admitted more than one reading and which reading we took.

**SK-01 — random_contact_disbursement_rate** (∈ [0.08, 0.1], severity `fail`)  
The denominator of the entire pitch. "9 → 30 disbursements per 100 RM calls" is only meaningful if the 9 is real, so the untargeted random-contact disbursement rate is pre-registered as a band in its own right rather than being read off whatever the generator happened to produce.  
*Source:* plan §B L9 bands ("baseline 8–10% (asserted)"); §D gate G3
  
*Note:* Also asserted inside the generator (§B L6 SD-S4 solves the contact-effect θ to land in this band). Asserting it here as well means a generator change that drifts the baseline cannot pass silently.
AMENDED 2026-09-16 — see `amendments` at the foot of this file. The BAND IS UNCHANGED at [0.08, 0.10]; the scoring population is now written down as the drop-off population (consented, contactable, an abandoned attempt in the trailing 12 months, no disbursement in flight) at the (customer, month) grain, and this metric is the disbursement rate among a uniformly random 10% contact sample of it. Source table: `data/labels.csv` (`eligible_for_contact = 1`, column `label_disbursed_in_window`).

**SK-02 — precision_at_10pct_budget** (∈ [0.25, 0.35], severity `fail`)  
The headline claim. Contact the top 10% of the consented held-out book and roughly 30 in 100 of those calls end in a disbursement. The upper bound matters as much as the lower: a synthetic book that yields 60% precision has leaked its own generative structure and no bank reviewer would believe it.  
*Source:* plan §B L9 bands ("precision@10% 25–35%"); §D gate G3
  
*Note:* Band is on the point estimate; the 95% CI is reported beside it.
AMENDED 2026-09-16 — see `amendments` at the foot of this file. The BAND IS UNCHANGED at [0.25, 0.35]; the scoring population is the same drop-off population as SK-01, model-ranked at the same 10% contact budget, so the "9 → 30 per 100 RM calls" headline is two numbers over one denominator. The generator (§B L6 SD-S4) tunes a single signal-to-noise knob so that an ORACLE ranker — one that sees the latent index the label was drawn from — reaches ~0.32. That is a ceiling on this criterion, not a prediction of it: the model reads those latents only through noisy observables and will land below it.

**SK-03 — precision_at_5pct_and_20pct_budget** (reported, no target, severity `report`)  
The shape of the precision curve either side of the operating budget, with CIs. A curve that is flat between 5% and 20% would mean the ranking is not doing much, whatever the single headline number says.  
*Source:* plan §B L9 bands ("+ @5/@20 w/ CI")
  
*Note:* REPORTED, NO TARGET — the plan pre-registers a band at 10% only.

**SK-04 — window_respect_rate** (≥ 0.9, severity `fail`)  
Per-product windows are a mentor mandate: a gold-loan lead is worthless on day three, a home-loan lead is alive for a fortnight. If the model pitches a one-day product to people who take a fortnight to close, the window it prints beside the lead does not describe the product it is selling.  
*Source:* plan §B L9 bands ("window respect ≥ 90% (new)")
  
*Note:* WHAT THIS MEASURES: conversion timing among converters. Of the held-out customers inside the contact budget who do disburse, the share whose disbursement falls within the pre-registered window of the product the model offered them (see label_definition.conversion_windows_days). A conversion that lands outside the offered product's window counts against this criterion even though it is a real disbursement.
WHAT THIS IS NOT: it is NOT contact-SLA compliance. It does not measure whether a relationship manager made contact before the lead's contact_by expired, and it never should be quoted as if it did. Nothing in this pipeline observes an RM dialling — there are no contact timestamps in the delivered pack — so contact-SLA compliance is unmeasured. The earlier phrasing ("the RM queue's SLA") was wrong and is retired.
INTERPRETATION: the plan introduces "window respect" without defining it; the definition above is this pack's registration of it. The threshold is unchanged from pre-registration.

**SK-05 — window_shopper_auc** (≥ 0.7, severity `fail`)  
Window-shopper detection is the feature that keeps RM time away from tyre-kickers. Deliberately a modest floor: the generator makes the signal informative but NOT deterministic (§B L6 SD-S3 — some genuine buyers balk at the fee once), so a high AUC here would mean the synthetic data had made the problem too easy.  
*Source:* plan §B L9 bands ("shopper AUC ≥ 0.70")
  
*Note:* AUC against the generator's latent window_shopper flag on the held-out book.

**SK-06 — baseline_ladder_headline_uplift** (reported, no target, severity `report`)  
The exact two numbers that go on the deck and in the README, emitted from the same run as everything else so they cannot drift apart from the evidence. Replaces the retired "28×" claim everywhere.  
*Source:* plan §B L7 SM-2 ("9 → 30 disbursements per 100 RM calls")
  
*Note:* Derived from SK-01 and SK-02; reported, no separate band.

**SK-07 — oot_precision_at_10pct_degradation_pp** (≤ 5.0, severity `fail`)  
A prospecting model is retrained on a cadence but used continuously. Losing more than 5 percentage points of precision on later months means the queue goes stale faster than the bank can refresh it.  
*Source:* plan §B L9 bands ("OOT degradation ≤ 5 pp")
  
*Note:* Measured in PERCENTAGE POINTS (holdout precision@10% minus out-of-time precision@10%), not as a ratio. Improvement is reported as a negative degradation and passes.

**SK-08 — auc** (≥ 0.75, severity `fail`)  
This is what licenses the 3-models-to-1 collapse (§B L7 SM-1). One model with `product` as a categorical is only defensible if it holds its own on every product, including the two thin ones.  
*Source:* plan §B L9 bands ("per-product AUC ≥ 0.75"); §D gate G3 ("×6")
  
*Note:* All six products, with CI. min_n is 0 deliberately: "×6" means all six, so a thin product is a generator problem to fix, not a cell to exempt.

**SK-09 — macro_auc** (≥ 0.78, severity `fail`)  
Unweighted mean of the six per-product AUCs, so a large product cannot carry the average while a small one is being failed.  
*Source:* plan §B L9 bands ("macro ≥ 0.78")

**SK-10 — auc_and_precision_at_10pct** (reported, no target, severity `report`)  
AUC and precision@10% with CI and n for every level of all seven cuts. Only the product cut carries a pre-registered floor, so the remaining six are reported in full and read by a human — including the cells that look bad.  
*Source:* plan §B L9 (12 runners, cut list); owner direction 7 ("validated across every cut")
  
*Note:* min_n of 500 is carried over from the calibration cell-size convention used on the DRISHTi side rather than inventing a second number. Cells below 500 are listed with their n and marked skipped_low_n.

**SK-11 — ece** (≤ 0.03, severity `fail`)  
The lead drawer shows a probability to an RM who will act on it. If a "40%" lead converts at 15%, the RM stops trusting the queue within a week.  
*Source:* plan §B L9 bands ("ECE ≤ 0.03 overall")

**SK-12 — ece** (≤ 0.03, severity `fail`)  
One model across six products can be well calibrated on average while being systematically over-confident on the products it saw least.  
*Source:* plan §B L9 bands ("ECE ≤ 0.03 overall + per product")
  
*Note:* The plan states a single figure (0.03) for both the overall and the per-product clause, so the same 0.03 is registered here — NOT a looser per-cell band. min_n is 0 for the same reason as SK-08.

**SK-13 — menu_of_4_hit_rate** (≥ 0.8, severity `fail`)  
The mentors asked for a menu of four, not a single next-best product. The menu earns its place only if the product the customer actually takes is inside it four times in five.  
*Source:* plan §B L9 bands ("menu-of-4 hit rate ≥ 80% (new)")
  
*Note:* INTERPRETATION: among held-out customers who disburse, the share whose realised product appears in the model's top-4 `product_menu` at the snapshot month. Random ordering over six products would score ~0.67, so 0.80 is a real but not heroic bar — recorded here so nobody later mistakes it for a strong result.

**SK-14 — top_1_product_accuracy** (reported, no target, severity `report`)  
The same measurement at rank 1. Reported so the menu's value over a single recommendation is visible as a number rather than asserted.  
*Source:* plan §B L9 (menu of 4); §D gate G3
  
*Note:* REPORTED, NO PRE-REGISTERED TARGET — deliberately. Setting a top-1 target would push the model back toward the single-recommendation behaviour the menu exists to replace.

**SK-15 — shopper_signal_negative_direction_count** (≥ 4, severity `fail`)  
The four window-shopper signals the mentors named — vague / blank answers, refusing to share income details, balking at the ₹1,000 fee, and refusing documents — must each push the disbursement probability DOWN. A signal that came out positive would mean the model had learned the opposite of the behaviour the business named, and the negative chips in the lead drawer would be lying to the RM.  
*Source:* plan §D gate G3 ("4 signals negative"); mentor mandate (window-shopper signals)
  
*Note:* INTERPRETATION: direction is measured as the sign of the signal's mean signed contribution on the held-out book; all four must be negative, hence a count of 4. Filed under rank-order because it is a direction-of-effect check on the score, not a leakage or ablation test.

**SK-16 — psi_score_distribution** (≤ 0.1, severity `fail`)  
Population Stability Index of the score distribution between the training window and the most recent window. 0.10 is the conventional "no meaningful shift" line in bank model-risk practice.  
*Source:* plan §B L9 bands ("PSI ≤ 0.10")

**SK-17 — features_using_post_abandon_information** (= 0, severity `fail`)  
The application-journey layer is the single biggest leakage hazard in SANKET: every feature about a journey is computed from a timeline that ends in the very outcome being predicted. Not one model input may draw on data timestamped after `abandon_ts` (or after disbursement, for the converters).  
*Source:* plan §B L9 bands ("leakage: nothing after abandon_ts")
  
*Note:* Zero tolerance, as written. Enforced as a count of violating features, so the report names the offending feature rather than just failing. Pairs with the existing rule in src/score_and_pack.py EXCLUDED_FEATURES that nothing after an application starts may be used at prospecting.

**SK-18 — permuted_label_auc** (∈ [0.48, 0.52], severity `fail`)  
Retrain the full pipeline on randomly permuted labels. Anything outside chance means the evaluation harness itself leaks — the strongest single check that the reported precision is real.  
*Source:* plan §B L9 bands ("permutation ∈ [0.48,0.52]")
  
*Note:* INTERPRETATION: the permutation is of the LABEL, with split, features and hyper-parameters untouched. Averaged over the registered seeds.

**SK-19 — precision_at_10pct_drop_by_feature_family** (reported, no target, severity `report`)  
Which families actually carry the model — cross-bank transactions from API 595/739, salary-credit behaviour, dwell signals, journey friction, shopper signals. Reported so the "what would we lose without this API" question has an evidenced answer.  
*Source:* plan §B L9 (runner 08)
  
*Note:* The plan specifies runner 08 for SANKET but pre-registers no band for it, so no threshold was invented. Reported with CIs; a human reads it.

**SK-20 — n_seeds_run** (≥ 5, severity `fail`)  
One seed is an anecdote. Five is the minimum at which the CI below means anything.  
*Source:* plan §B L9 bands ("≥5 seeds"); §D gate G7

**SK-21 — cross_seed_precision_at_10pct_ci_width_pp** (≤ 4.0, severity `fail`)  
The headline precision must be a property of the model, not of the seed. Registered in percentage points: a cross-seed interval wider than 4 pp would put the 25–35% band itself within noise.  
*Source:* plan §B L9 bands ("CI ≤ 4 pp")

**SK-22 — precision_at_10pct_under_stress_scenarios** (reported, no target, severity `report`)  
Behaviour when the book shifts: consent withdrawal at scale, a suppression-rule sweep (§B L6 SD-S6), cross-bank transaction data (595/739) unavailable, and a doubled window-shopper share.  
*Source:* plan §B L9 (runner 10)
  
*Note:* The plan specifies runner 10 for SANKET but pre-registers no band for it, so no threshold was invented. The scenarios themselves ARE pre-registered here so the set cannot be chosen after seeing which ones look good.

**SK-23 — adverse_impact_ratio** (≥ 0.8, severity `report`)  
Four-fifths rule on the contact rate: least-contacted group ÷ most-contacted group within each protected-proxy attribute, at the live contact budget.  
*Source:* plan §B L9 bands ("fairness incl. the documented gig failure")
  
*Note:* REPORTED, NOT GATED. SANKET excludes gender, religion, caste, marital status and pin-code outright by policy (src/score_and_pack.py EXCLUDED_FEATURES), so the protected-proxy attributes evaluated are occupation_segment, income_band, city_tier and age band. The 0.80 reference line is the conventional four-fifths threshold, recorded so the report can say how far each attribute sits from it.

**SK-24 — gig_worker_failure_disclosure** (must exist, severity `report`)  
A known, accepted failure mode: irregular gig-economy income reads as instability to a model trained mostly on salaried credits, so gig workers are under-contacted. It is disclosed rather than tuned away, because tuning it away on synthetic data would be pretending to have solved it.  
*Source:* plan §B L9 bands ("fairness incl. the documented gig failure")
  
*Note:* INTERPRETATION: registered as an existence check — the fairness section of REPORT.md must contain a quantified statement of the gig-worker gap, and it must be carried into the README's "What we did not build, and why". Kept at severity `report` because the plan lists it among reported findings; it is nonetheless a G5 honesty-gate item.

**SK-25 — precision_at_10pct_by_baseline_rung** (reported, no target, severity `report`)  
Contextualises the gain: random contact, then balance-ranked contact (what a branch does today), then a logistic scorecard, then the LightGBM model, each with CI. If balance-ranking is within noise of the model, that is the honest finding and the deck says so.  
*Source:* plan §B L9 (runner 12)
  
*Note:* The plan specifies runner 12 but pre-registers no band for it, so no threshold was invented. The rungs ARE pre-registered here so the comparison set cannot be chosen after the fact.

## Figures

- `figures/ablation_deltas.png`
- `figures/auc_by_cut_grid.png`
- `figures/auc_by_product.png`
- `figures/baseline_ladder.png`
- `figures/ece_by_product.png`
- `figures/fairness_contact_rates.png`
- `figures/gig_gap.png`
- `figures/leakage_checks.png`
- `figures/menu_hit_rate.png`
- `figures/oot_precision.png`
- `figures/precision_curve.png`
- `figures/psi_score.png`
- `figures/reliability_overall.png`
- `figures/seed_sweep_precision.png`
- `figures/shopper_signal_directions.png`
- `figures/stress_precision.png`
- `figures/window_respect.png`

