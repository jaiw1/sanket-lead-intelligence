# `data/bank/` — the bank-enrichment contract (SANKET)

What `src/enrich_bank.py` reads from the IDBI Atlas sandbox, what it writes, and what
happens when the sandbox is not available.

```
data/bank/
  raw/                     per-API JSON exactly as Atlas returned it    (gitignored)
  enriched.csv             one row per customer, the join of every pull (gitignored)
  provenance.json          per-column source for that enriched.csv      (gitignored)
  provenance.example.json  a committed example of the above             (committed)
  fixture.json             offline stand-in, 120 customers              (committed)
  check_fixture.py         smoke test for fixture.json                  (committed)
  SCHEMA.md                this file                                    (committed)
```

## The fallback rule

```
credentials present AND endpoint approved  ->  live pull      -> column tagged BANK_API
credentials present BUT endpoint pending   ->  fixture column -> column tagged FIXTURE
no credentials / no endpoints at all       ->  whole fixture  -> every column FIXTURE
no bank API supplies this field at all     ->  generator      -> column tagged SIMULATED
```

**The pipeline never fails because the bank is slow.** It degrades to the fixture, records
exactly what happened in `provenance.json`, and the UI badges every value accordingly.

SANKET has one extra fallback the loan side does not: the **cross-bank** family needs an
*active AA consent per customer*, not merely an approved subscription. A book with approved
595/739 endpoints and no consents still yields `cross_bank: FIXTURE`, and that is the normal
state — consent is per customer and the customer may say no.

`--bank` on `src/score_and_pack.py` selects the enriched path; without it the pipeline runs
purely synthetic, exactly as it did in July 2026.

## ID spaces

Atlas spells the same identifier four different ways depending on the API. `app/atlas/idmap.py`
in the platform repo normalises all of them; `enriched.csv` uses only the normalised name.

| Space | Atlas spellings | Normalised to | Notes |
|---|---|---|---|
| **CIF** | `custId` · `cifId` · `custCifId` · `customerId` | `cif_id` | The customer. |
| **Account** | `acctId` · `acid` · `foracid` · `accountNo` | `account_no` (+ `foracid` kept verbatim) | The CASA account. |
| **AA party** | `vua` -> `consentId` / `linkRefNumber` | `aa_vua` / `aa_consent_id` / `aa_link_ref_number` | The Account Aggregator handle. A `vua` resolves to a consent, a consent to a link reference, and only then can 595/739 be called. |
| **Employee** | `ein` | `rm_ein` | API 508 HRMS; also API 442 `accountManager`. Seeds the round-robin roster. |

## The 25 APIs — which ones SANKET uses, and for what

SANKET touches **21**: 12 shared with DRISHTi, 9 of its own. It ingests 20 and *writes* to
one (428).

| API | What it gives | Keyed by | Feeds these `enriched.csv` columns |
|---|---|---|---|
| **365** | Account enquiry (balances, CIF) | account | `casa_acct_id` `balance_current` `balance_avg_3m` `balance_min_6m` `account_open_date` `account_status` `product_code` |
| **393** | Full statement (cursor paging, 999/page) | account | `credits_med_6m` `credits_cv_6m` `debits_med_6m` `salary_credit_day` `salary_credit_amount` `salary_credit_narration` `rent_debit_amount` `fuel_cab_spend_3m` `school_fee_debit` `ecommerce_spend_3m` `upi_p2m_count_3m` `card_spend_3m` `insurance_premium_annual` `fd_balance` `fd_break_flag` `min_bal_breach_6m` `narration_samples` |
| **394** | Accounts by CIF | CIF | `linked_account_count` `holdings` |
| **456** | Dedupe / master | CIF / PAN | `pan_masked` `entity_name` `customer_count` `dedupe_match_score` `gstin` |
| **442** | CIF exposure, rating, account manager | CIF | `account_manager_ein` `cust_rating` |
| **391 · 402 · 362 · 538** | Existing loan holdings, DPD, liens, payoff | account / CIF | Used to **suppress**: never pitch a product the customer already holds, and never pitch anyone in arrears. Feeds `holdings` and the `already_holds_product` suppression reason. |
| **433** | Rates (product-level, **no customer id**) | product | `product_rate_code` `card_rate_pa` |
| **473** | Repayment schedule (product-level) | product | `emi_per_lakh` `schedule_ref` |
| **508** | HRMS employee | `ein` | `rm_ein` `rm_name` `branch_code` `branch_name` `ifsc` `reporting_manager_ein` |
| **590** | Create AA consent request | `vua` | starts the lifecycle |
| **591** | Consent list | `vua` / CIF | `aa_consent_id` `aa_fi_type` |
| **592 · 593** | Consent handle / artefact | `consentId` | `aa_link_ref_number` |
| **497 · 498** | Consent + data webhooks | callback | arrival timestamps -> `aa_fetched_on` |
| **595 · 739** | **Cross-bank statement** | `linkRefNumber` | `ext_account_count` `ext_emi_total` `ext_emi_lender` `ext_emi_narration` `ext_salary_bank` `ext_salary_amount` `ext_salary_narration` |
| **428** | `createLead` — **the only write** | CIF | writes nothing to `enriched.csv`; manager-gated, dry-run by default, 456-deduped, every returned `leadId` audited |

**Not used by SANKET:** 404 · 441 (DRISHTi-only overdue/drawing-power detail) · 415 (CKYC —
subscribed, deliberately not scored on).

### API 408 (CIBIL) is deliberately **not** called

Bureau data needs purpose-specific consent and is pulled only at lead-to-application, never
for prospecting. It is already in `EXCLUDED_FEATURES`, and `provenance.json` records it as
`NOT_COLLECTED` with that reason rather than omitting it. The restraint is a governance
exhibit — make sure it survives into the deck.

### What 595/739 unlock

Two gaps nothing else can fill, both visible only in another bank's statement narrations:

- **An EMI paid to another lender** — `ACH-D-HDFCBANK LOAN EMI-XXXXX4821`
- **A salary credited elsewhere** — `AA-XB/AXISBANK/CR/SALARY NOVATECH SOLUTIONS/XXXXXX9317`

Both appear in `fixture.json` so the narration parser can be built and tested before a single
consent exists. Without them, `emi_share` understates true indebtedness and a customer whose
salary lands at another bank looks like they have no income at all — the single worst failure
mode in a capacity model.

### Fields no API supplies — always `SIMULATED`

Product-page dwell and app sessions · campaign and contact history · application-journey
events and stage outcomes · window-shopper signals · marketing consent (AA consent from 591
is a *different* artefact and must not be conflated) · occupation and income band.

## `enriched.csv`

One row per customer, `cust_id` as the key. Columns are exactly the fixture's, minus the
`_`-prefixed bookkeeping fields. Grouped by provenance family:

| Family | Columns |
|---|---|
| `identity` | `cust_id` `cif_id` `casa_acct_id` `foracid` `account_no` `entity_name` `pan_masked` `gstin` `customer_count` `dedupe_match_score` `branch_code` `branch_name` `ifsc` `rm_ein` `rm_name` `reporting_manager_ein` `account_manager_ein` `cust_rating` |
| `casa_behaviour` | `balance_current` `balance_avg_3m` `balance_min_6m` `account_open_date` `account_status` `product_code` `credits_med_6m` `credits_cv_6m` `debits_med_6m` `salary_credit_day` `salary_credit_amount` `salary_credit_narration` `rent_debit_amount` `fuel_cab_spend_3m` `school_fee_debit` `ecommerce_spend_3m` `upi_p2m_count_3m` `card_spend_3m` `insurance_premium_annual` `fd_balance` `fd_break_flag` `min_bal_breach_6m` `narration_samples` |
| `cross_bank` | `aa_consent_id` `aa_link_ref_number` `aa_vua` `aa_fi_type` `aa_fetched_on` `ext_account_count` `ext_emi_total` `ext_emi_lender` `ext_emi_narration` `ext_salary_bank` `ext_salary_amount` `ext_salary_narration` |
| `holdings` | `linked_account_count` `holdings` |
| `digital` | `dwell_personal` `dwell_gold` `dwell_auto` `dwell_education` `dwell_home` `dwell_lap` `campaign_contacts_6m` `last_contact_date` |
| `consent` | `consent_marketing` `dnd` |
| `journey` | `journey_stage_reached` `journey_blank_field_ratio` `journey_refused_income` `journey_fee_balk` `journey_doc_refusal` `journey_multi_product_revisits` |
| `profile` (folded into `identity`) | `segment` `occupation` `income_band` `age` `city_tier` `tenure_m` |
| rate reference | `product_rate_code` `card_rate_pa` `emi_per_lakh` `schedule_ref` `contact_window_days` |

Nulls are meaningful: a null `ext_emi_total` means *no AA consent*, which is not the same as
*no external EMI*. Never coerce it to zero — that would silently claim a customer has no
outside debt, and the capacity model would over-lend.

## `provenance.json`

Written beside `enriched.csv` on every enrichment run. See `provenance.example.json` for a
full instance. Shape:

```jsonc
{
  "provenance_version": 1,
  "product": "sanket",
  "generated_at": "<iso8601>",
  "mode": "live" | "fixture" | "mixed",
  "fixture_reason": "<why anything fell back>",
  "families": { "identity": "BANK_API", "cross_bank": "FIXTURE", ... },   // the 8 families
  "columns":  { "credits_med_6m": { "source": "BANK_API", "api_id": "393",
                                    "field": "txnAmt", "pulled_at": "...", "n_records": 4820 }, ... },
  "endpoints": [ { "api_id": "595", "http_status": 0, "n_records": 0,
                   "subscription_status": "approved",
                   "error": "no active AA consent for this customer" }, ... ]
}
```

`families` and `endpoints` flow straight into the export's `provenance` and
`meta.sandbox_sync` blocks — see `rrsquad-platform/contracts/sanket_export.schema.json`.
The **`model` family is the weakest of the other seven** in trust order
`BANK_API > SIMULATED > FIXTURE`; the batch runner asserts it.

A column may also carry `"source": "NOT_COLLECTED"` with a reason — used for API 408, where
*not* fetching is the deliberate design.

## `fixture.json`

120 customers: **20 per product** across all six (personal, gold, auto, education, home,
lap), 85 columns each, every record tagged `"_provenance": "FIXTURE"`.

Built so the hard parts are exercisable offline: the three segments have genuinely different
income volatility (gig `credits_cv_6m` runs 0.22–0.61, salaried 0.02–0.09), ~55% carry an
external EMI, **~30% have their salary credited at another bank**, AA consent is present for
only ~62% so the fallback path is the common case, and `narration_samples` carries realistic
NEFT / ACH / UPI / AA-XB narration formats for the parser to chew on.

> **Every value in `fixture.json` is fabricated.** No real customer, employee or employer is
> represented. Third-party bank short codes appear only inside synthetic cross-bank
> narrations, to exercise the narration parser; no claim is made about any institution.

```bash
python3 data/bank/check_fixture.py     # exits non-zero if the fixture is unusable
```

## Rules

1. **Never commit `raw/`, `enriched.csv` or `provenance.json`.** `.gitignore` covers all three.
2. **Never put a credential in this directory.** Client ids and secrets live in
   `/etc/rrsquad/*.env` at 0600 and reach the process through systemd `LoadCredential=`.
3. **Every column gets a provenance entry.** A column absent from `provenance.json` must fail
   the enrichment, not default to `BANK_API`.
4. **Never score a customer without marketing consent.** They are excluded *before* scoring,
   not filtered out of the queue afterwards.
5. **Never call 595/739 without an ACTIVE consent**, and never cache the result past the
   consent's validity.
