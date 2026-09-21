# -*- coding: utf-8 -*-
"""SM-6 — ``data/export/sanket_export.json``, in the platform's contract shape.

``rrsquad-platform/contracts/sanket_export.schema.json`` is a different, larger
shape than ``app/public/sanket_data.json``: it adds a full ``customers[]`` (the
scored book, not just the ~320-lead queue) and ``journeys[]`` (one row per
application attempt) so the platform's own validation runners never have to
join back to this repo's CSVs, and it flattens ``metrics`` instead of nesting
most of it under ``blended``. This module builds that shape from the same
in-memory objects :func:`model.pack.run` already computed — no second model
run, no second read of the CSVs.

Only produced when ``--bank`` is passed (``score_and_pack.py``'s ``--bank``
flag; see ``model.bank``). Three ``meta`` fields are deliberately left as
placeholders — ``model_run_id``, ``git_sha``, ``criteria_sha`` — because the
platform's batch (not this repo) mints the run id, stamps the commit this
export was built at, and hashes the *committed* ``validation/criteria.yaml``
it verifies against; ``contracts/validate.py`` will flag exactly these three
and nothing else on a correct run. Validate with::

    python3 ../rrsquad-platform/contracts/validate.py sanket data/export/sanket_export.json
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import PRODUCTS, WINDOW_DAYS
from . import bank as B
from . import emi as E

SCHEMA_VERSION = "1.0.0"
#: RFC 4122 nil UUID / all-zero hex — valid-shaped placeholders for the three
#: fields the batch fills; never mistaken for a real id, sha, or hash.
PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"
PLACEHOLDER_GIT_SHA = "0" * 40
PLACEHOLDER_CRITERIA_SHA = "0" * 64

_OCCUPATION = {"salaried": "Salaried-Private", "self-employed": "Self-Employed-Business",
              "gig": "Gig"}
_CHANNEL = {"branch-walk-in": "branch", "rm-call": "call_centre", "app": "mobile_app",
           "web": "web", "dsa": "dsa"}
#: ``model.copy.NEGATIVE``'s chip keys -> the schema's short, closed
#: ``negative_signals[].signal`` enum.
#:
#: A chip that arrives at an RM under a different name than the one the model
#: fired is a lie the schema cannot catch, so the rule here is: extend the
#: contract rather than substitute. ``contact_fatigue`` was added to the
#: contract on 2026-09-21 for exactly that reason — "contacted five times in
#: thirty days" used to reach the RM as "vague answers", which is a different
#: accusation about a different person.
#:
#: TWO CHIPS STILL COLLAPSE, knowingly, and are listed here so the loss is not
#: silent: ``journey_stated_income_ratio`` (stated income above what the account
#: shows) and ``journey_open_now`` (another application already open) both land
#: on ``vague_answers``. Neither has a contract value yet; both are named in
#: MODEL_CARD §10 as open contract debt rather than fixed by inventing enum
#: values this review did not scope.
_NEGATIVE_SIGNAL = {
    "journey_blank_field_ratio": "blank_field_ratio",
    "journey_refused_income": "refused_income",
    "journey_fee_balk": "fee_balk",
    "journey_doc_refusal": "doc_refusal",
    "journey_multi_product_revisits": "multi_product_revisits",
    "journey_docs_shortfall": "doc_refusal",
    "journey_stated_income_ratio": "vague_answers",
    "contacts_30d": "contact_fatigue",
    "journey_open_now": "vague_answers",
}

#: ``model.SUPPRESSION_REASONS`` -> the contract's ``suppression_reasons`` enum.
#: Total over every reason a suppressed row can carry (``tests/test_model_export.py``
#: asserts that), so the ``.get`` default below is unreachable.
#:
#: ``deceased`` and ``dormant`` were added to the contract on 2026-09-21. Both
#: used to be exported as ``kyc_expired``, which told an RM to go and re-KYC a
#: customer who had died.
_SUPPRESSION_REASON = {
    "no_marketing_consent": "no_marketing_consent", "dnd": "dnd_registry",
    "recent_contact": "contact_fatigue", "recent_decline": "recent_decline",
    "application_in_flight": "existing_application_open",
    "already_holds_product": "already_holds_product",
    "account_dormant": "dormant", "deceased": "deceased",
}


def _income_band(monthly: float) -> str:
    if monthly < 25_000:
        return "<25k"
    if monthly < 50_000:
        return "25k-50k"
    if monthly < 100_000:
        return "50k-1L"
    if monthly < 200_000:
        return "1L-2L"
    return "2L+"


def _cif_id(cust_id: str) -> str:
    """A deterministic 9-digit numeric id from ``cust_id``'s own numeric suffix.

    Not a real CIF — no live pull ran — but stable across runs and collision-
    free (the suffix is already unique per customer in this book).
    """
    digits = "".join(ch for ch in str(cust_id) if ch.isdigit())
    return f"9{int(digits[-8:] or 0):08d}"


#: The method name travels unchanged.
#:
#: Until 2026-09-21 this remapped ``"hanley-mcneil"`` onto the contract's
#: ``"delong"``, on the grounds that they are the same family of analytic AUC
#: interval. They are not the same method: Hanley-McNeil assumes a distribution
#: for the score, DeLong is distribution-free on the empirical placement values,
#: and the intervals differ. A consumer reading ``method`` is reading a claim
#: about how the number was computed, so ``hanley-mcneil`` is now a value of the
#: contract's enum and this map exists only to keep the shape of the call site.
_CI_METHOD: dict[str, str] = {}


def _ci(d: dict | None) -> dict:
    """Coerce ``model.metrics.measured``'s ``{value, ci_low, ci_high, n, method}``
    into the schema's ``confidence_interval`` — numbers only, no ``null``s.
    """
    if not d:
        return dict(value=0.0, ci_low=0.0, ci_high=0.0)
    out = dict(value=float(d.get("value") or 0.0),
               ci_low=float(d.get("ci_low") if d.get("ci_low") is not None else d.get("value") or 0.0),
               ci_high=float(d.get("ci_high") if d.get("ci_high") is not None else d.get("value") or 0.0))
    if d.get("n") is not None:
        out["n"] = int(d["n"])
    if d.get("method"):
        out["method"] = _CI_METHOD.get(d["method"], d["method"])
    return out


# --------------------------------------------------------------------------- #
# meta / counts / metrics
# --------------------------------------------------------------------------- #

#: APIs the bank refused us. `subscription_status: "rejected"` is one of the four values the
#: contract's enum offers and this is the only API in either product that earns it — leaving
#: it to read "pending" would describe a decision that is not pending at all.
REJECTED_APIS: frozenset = frozenset({"508"})


def _endpoint_rows(bank_ctx: B.BankContext) -> list[dict]:
    """`meta.sandbox_sync.endpoints[]` — one row per API we asked about, refusals included.

    Prefers `data/bank/provenance.json`'s own endpoint block over `pulled.json`'s, for two
    reasons. It carries `latency_ms` (`pulled.json` does not, and the contract types the
    field integer-with-no-null, so reading it from the wrong file writes a schema
    violation). And it has a row for every *declared* API rather than only the ones a call
    was made for — which is what makes API 508 visible here as `rejected` instead of simply
    missing. An API with no measured latency omits the key rather than sending a null.
    """
    rows = (bank_ctx.provenance_raw or {}).get("endpoints")
    if not isinstance(rows, list) or not rows:
        rows = [dict(api_id=str(api_no), http_status=entry.get("http_status"),
                     n_records=entry.get("n_records"),
                     error=None if entry.get("provenance") == "BANK_API" else "NOT_COLLECTED")
                for api_no, entry in sorted((bank_ctx.pulled or {}).get("apis", {}).items(),
                                            key=lambda kv: int(kv[0]))]
    out = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("api_id") or "").isdigit():
            continue
        api_id = str(row["api_id"])
        answered = not row.get("error")
        entry = dict(
            api_id=api_id,
            http_status=int(row.get("http_status") or 0),
            n_records=int(row.get("n_records") or 0),
            subscription_status=("rejected" if api_id in REJECTED_APIS
                                 else "approved" if answered else "pending"),
        )
        latency = row.get("latency_ms")
        if isinstance(latency, (int, float)):
            entry["latency_ms"] = int(latency)
        out.append(entry)
    return sorted(out, key=lambda r: int(r["api_id"]))


def build_meta(meta: dict, bank_ctx: B.BankContext, seed: int) -> dict:
    ref_month = pd.Timestamp(meta["ref_month"]).strftime("%Y-%m")
    if bank_ctx.pulled is not None:
        pulled_at = bank_ctx.pulled.get("generated_at", meta["generated_at"])
        endpoints = _endpoint_rows(bank_ctx)
    elif bank_ctx.enabled and bank_ctx.fixture_by_cust:
        pulled_at = (bank_ctx.fixture_meta or {}).get("generated_at", meta["generated_at"])
        endpoints = []  # mode "fixture": schema requires this empty
    else:
        pulled_at = meta["generated_at"]
        endpoints = []

    return dict(
        product="sanket",
        schema_version=SCHEMA_VERSION,
        model_run_id=PLACEHOLDER_UUID,
        generated_at=meta["generated_at"],
        git_sha=PLACEHOLDER_GIT_SHA,
        seed=int(seed),
        criteria_sha=PLACEHOLDER_CRITERIA_SHA,
        provenance_version=1,
        sandbox_sync=dict(pulled_at=pulled_at, mode=bank_ctx.mode if bank_ctx.mode != "simulated"
                          else "fixture", endpoints=endpoints if bank_ctx.mode != "simulated" else []),
        generated_from="synthetic liability book (src/book) with an application-journey layer "
                      "(src/journeys)" + (", enriched from the IDBI Atlas sandbox and "
                      "data/bank/fixture.json" if bank_ctx.enabled else "") +
                      "; one LightGBM ranks the drop-off population across six products.",
        ref_month=ref_month,
        n_customers=int(meta["n_customers"]),
        n_consented=int(meta["n_consented"]),
        contact_windows_days=dict(WINDOW_DAYS),
        conversion_definition="disbursement",
        # `label_horizon_months` is optional and typed integer-only (no null)
        # in the contract; this label's horizon is the per-product decision
        # window above, not a fixed N-month lookahead, so it is omitted rather
        # than forced into a number that would misstate the label.
    )


def build_counts(counts: dict) -> dict:
    return dict(hot=int(counts["hot"]), warm=int(counts["warm"]), cold=int(counts["cold"]),
               no_consent=int(counts["no_consent"]), suppressed=int(counts["suppressed"]),
               green=int(counts.get("green", 0)))


def build_metrics(m: dict) -> dict:
    return dict(
        baseline_dropoff_disbursement=_ci(m["baseline_dropoff_disbursement"]),
        precision_at={k: _ci(v) for k, v in m["precision_at"].items()},
        per_product_auc={p: dict(auc=round(float(v["auc"]), 4), auc_ci=_ci(v["auc_ci"]),
                                 n_pos_test=int(v["n_pos_test"]), ece=round(float(v["ece"]), 5))
                         for p, v in m["per_product_auc"].items()},
        auc_macro=round(float(m["auc_macro"]), 4),
        menu_hit_rate=_ci(m["menu_hit_rate"]),
        window_respect=_ci(m["window_respect"]),
        shopper_signal_auc=_ci(m["shopper_signal_auc"]),
        suppression=dict(n_suppressed=int(m["suppression"]["suppressed_count"]),
                         by_reason={str(k): int(v) for k, v in m["suppression"]["reasons"].items()}),
        prec_curve=m["blended"]["prec_curve"],
        calibration=m["calibration"],
        uplift=m["uplift"],
        fairness=m["fairness"],
        income_acc=m["income_acc"],
        excluded_features=m["excluded_features"],
    )


# --------------------------------------------------------------------------- #
# customers[]
# --------------------------------------------------------------------------- #

def build_customers(snap_rows: pd.DataFrame, rm_map: dict, bank_ctx: B.BankContext) -> list[dict]:
    out = []
    for r in snap_rows.itertuples(index=False):
        cust_id = str(r.cust_id)
        overlay = bank_ctx.overlay_for(cust_id)
        est_income = float(overlay.get("credits_med_6m") or r.credits_med_6m or 0.0)
        rm = rm_map.get(cust_id)
        cif_id = str(overlay.get("cif_id") or _cif_id(cust_id))
        row = dict(
            cust_id=cust_id,
            cif_id=cif_id,
            segment=str(r.segment),
            occupation=str(overlay.get("occupation") or _OCCUPATION.get(str(r.segment), "Other")),
            income_band=str(overlay.get("income_band") or _income_band(est_income)),
            age=int(r.age), city_tier=int(r.city_tier), tenure_m=int(r.tenure_m),
            consent=bool(int(r.consent_marketing) == 1), dnd=bool(int(r.dnd) == 1),
            estimated_income_monthly=round(est_income, 2),
            true_income_monthly=(round(float(r.t_income_at_month), 2)
                                 if np.isfinite(getattr(r, "t_income_at_month", float("nan"))) else None),
            holdings=list(overlay.get("holdings") or []),
            # The cif_id too, not just the cust_id: the sandbox is keyed by the bank's own
            # customer ids, so that is the id a fetched record would be found under.
            provenance=bank_ctx.provenance_for(cust_id, cif_id),
        )
        if overlay.get("branch_code"):
            row["branch_code"] = str(overlay["branch_code"])
        elif rm is not None:
            row["branch_code"] = rm.rm_branch
        if overlay.get("rm_ein"):
            row["rm_ein"] = str(overlay["rm_ein"])
        elif rm is not None:
            row["rm_ein"] = rm.rm_id
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# journeys[]
# --------------------------------------------------------------------------- #

def _abandon_reason(row) -> str | None:
    if row.outcome != "abandoned":
        return None
    if bool(row.fee_balk):
        return "fee_balk"
    if bool(row.doc_refusal):
        return "doc_refusal"
    if int(row.income_shared) == 0:
        return "income_refusal"
    return "timeout"


def _stages_for(events: pd.DataFrame) -> list[dict]:
    stages: list[dict] = []
    entered_at = None
    for ev in events.sort_values("seq").itertuples(index=False):
        occ = pd.Timestamp(ev.occurred_at).isoformat()
        dwell = float(ev.days_in_from_stage) * 86400.0 if pd.notna(ev.days_in_from_stage) else 0.0
        if ev.event == "start":
            entered_at = occ
            continue
        if ev.event == "advance":
            stages.append(dict(stage=str(ev.from_stage), entered_at=entered_at, exited_at=occ,
                               outcome="advanced", dwell_seconds=round(max(dwell, 0.0), 1)))
            entered_at = occ
        elif ev.event == "abandon":
            stages.append(dict(stage=str(ev.from_stage), entered_at=entered_at, exited_at=None,
                               outcome="abandoned", dwell_seconds=round(max(dwell, 0.0), 1)))
        elif ev.event == "disburse":
            stages.append(dict(stage=str(ev.from_stage), entered_at=entered_at, exited_at=occ,
                               outcome="advanced", dwell_seconds=round(max(dwell, 0.0), 1)))
            stages.append(dict(stage=str(ev.to_stage), entered_at=occ, exited_at=None,
                               outcome="advanced", dwell_seconds=0.0))
    if not stages:
        # a journey with no events at all (shouldn't happen, but the schema's
        # `stages` is `minItems: 1` and the export must not raise over one row)
        stages = [dict(stage="start", entered_at=entered_at or datetime.now(timezone.utc).isoformat(),
                       exited_at=None, outcome="pending", dwell_seconds=0.0)]
    return stages


def build_journeys(journeys_df: pd.DataFrame, events_df: pd.DataFrame,
                   label_truth: pd.DataFrame, cust_ids: list[str],
                   bank_ctx: B.BankContext) -> list[dict]:
    """One row per application ATTEMPT, for every scored customer.

    Not one per customer: the contract's own words are "one row per application
    ATTEMPT, not per customer", and a lead is about a SPECIFIC attempt — the
    abandonment it revives, named in ``lead.journey_ref``.  This used to carry
    only each customer's most recent attempt (highest ``attempt_seq``), which
    was the wrong attempt for all but a handful of leads and, for 140 of 344,
    an attempt that was never abandoned at all and carries no ``abandon_ts``;
    a ``journey_ref`` pointing into that set would have dangled or, worse,
    resolved to a different application and dated an RM's deadline from it.

    The whole history of the scored population is ~30% more rows than the
    per-customer pick was, and it is the only version in which every
    ``journey_ref`` resolves.  The population is still the scored one: attempts
    by customers outside ``cust_ids`` are not exported.
    """
    keep = set(str(c) for c in cust_ids)
    j = journeys_df[journeys_df["cust_id"].astype(str).isin(keep)].copy()
    if j.empty:
        return []
    j = j.sort_values(["cust_id", "attempt_seq"], kind="stable")

    truth_key = label_truth.set_index(["cust_id", "month"])["shopper_truth"] \
        if {"cust_id", "month", "shopper_truth"} <= set(label_truth.columns) else None

    ev_by_attempt = {aid: g for aid, g in events_df.groupby("attempt_id", sort=False)}

    out = []
    for row in j.itertuples(index=False):
        cust_id = str(row.cust_id)
        stages = _stages_for(ev_by_attempt.get(row.attempt_id, events_df.iloc[0:0]))
        abandoned = row.outcome == "abandoned"
        disbursed = row.outcome == "disbursed"
        shopper_truth = None
        if truth_key is not None:
            try:
                shopper_truth = bool(int(truth_key.loc[(cust_id, int(row.start_month))]))
            except KeyError:
                shopper_truth = None
        if shopper_truth is None:
            shopper_truth = bool(row.fee_balk) or bool(row.doc_refusal) or \
                (float(row.answers_blank_ratio or 0) >= 0.25 and int(row.income_shared) == 0)
        out.append(dict(
            journey_id=str(row.attempt_id), cust_id=cust_id, product=str(row.product),
            channel=_CHANNEL.get(str(row.channel), "web"), attempt_no=int(row.attempt_seq),
            started_at=pd.Timestamp(row.started_at).isoformat(),
            last_event_at=pd.Timestamp(row.last_stage_at).isoformat(),
            stage_reached=str(row.stage_reached), stages=stages, abandoned=bool(abandoned),
            abandon_ts=(pd.Timestamp(row.abandoned_at).isoformat()
                       if abandoned and pd.notna(row.abandoned_at) else None),
            abandon_reason=_abandon_reason(row), disbursed=bool(disbursed),
            disbursed_at=(pd.Timestamp(row.disbursed_at).isoformat()
                         if disbursed and pd.notna(row.disbursed_at) else None),
            disbursed_amount=(float(row.amount_offered) if disbursed and pd.notna(row.amount_offered)
                              else None),
            fee_paid=bool(row.fee_paid) if pd.notna(row.fee_paid) else False,
            window_shopper=shopper_truth,
            shopper_signals=dict(
                blank_field_ratio=round(float(row.answers_blank_ratio or 0.0), 4),
                refused_income=bool(int(row.income_shared) == 0),
                fee_balk=bool(row.fee_balk) if pd.notna(row.fee_balk) else False,
                doc_refusal=bool(row.doc_refusal) if pd.notna(row.doc_refusal) else False,
                multi_product_revisits=int(row.revisits_30d or 0),
            ),
            provenance=bank_ctx.provenance_for(
                cust_id, str((bank_ctx.overlay_for(cust_id).get("cif_id") or _cif_id(cust_id)))),
        ))
    return out


# --------------------------------------------------------------------------- #
# amortisation_schedules{} and leads[]
# --------------------------------------------------------------------------- #

def build_amortisation_schedules() -> dict:
    """One schedule per product, keyed for reuse across every lead pitching it."""
    out = {}
    for p in PRODUCTS:
        principal = E.REFERENCE_PRINCIPAL[p]
        tenor = E.REFERENCE_TENOR_MONTHS[p]
        rows, schedule_source = E.schedule_for(p)
        total_interest = round(sum(r["interest"] for r in rows), 2)
        ref = f"AMT-{p.upper()}-{principal // 1000}K-{tenor}M"
        sample = [rows[0]] + (([rows[len(rows) // 2]] if len(rows) > 2 else []) + [rows[-1]])
        out[ref] = dict(
            product=p, principal=float(principal), rate_pa=round(E.UNIFORM_RATE_PA / 100.0, 4),
            tenor_months=tenor, emi=float(E.reference_emi(p)), total_interest=total_interest,
            rows=sample,
            # `rate` -- API 433 answered with the rate card.  `schedule` -- API 473
            # is an amortisation engine and answers too, once per reference
            # ticket (`rrsquad-platform` batch/pull.py::TICKET_LADDER), so these
            # rows are the bank's own and read BANK_API.  Without a pull on this
            # checkout the schedule is derived from the 433 rate instead, which
            # the platform's three-value enum has no slot for -- SIMULATED is the
            # nearest honest reading ("no API supplied this"), and
            # `E.SCHEDULE_SOURCE_DERIVED` is the fuller tag this repo's own
            # MODEL_CARD and pack.py carry.
            provenance=dict(
                rate="BANK_API",
                schedule=("BANK_API" if schedule_source == E.SCHEDULE_SOURCE_BANK
                          else "SIMULATED"),
            ),
        )
    return out, {p: ref for p, ref in zip(PRODUCTS, out.keys())}


def build_leads(leads_internal: list[dict], rm_map: dict,
               amort_ref_by_product: dict[str, str]) -> list[dict]:
    out = []
    for lead in leads_internal:
        cust_id = lead["id"]
        suppressed = bool(lead["suppressed"])
        rm = rm_map.get(cust_id)
        assigned_rm_id = None if suppressed or rm is None else rm.rm_id
        menu = []
        for item in lead["product_menu"]:
            menu.append(dict(product=item["product"], prob=round(float(item["p"]), 4),
                             reason=item["reason"], safe_emi=float(item["emi"]),
                             window_days=int(item["window_days"]),
                             contact_by=item["contact_by"],
                             amortisation_ref=amort_ref_by_product.get(item["product"])))
        suppression_reasons = ([_SUPPRESSION_REASON.get(lead["suppression_reason"], "contact_fatigue")]
                               if suppressed else [])
        pitch = dict(en=dict(opener=lead["pitch"]["opener"], why_now=lead["pitch"]["why_now"],
                             proof=lead["pitch"]["proof"]),
                    hi=dict(opener=lead["pitch"]["opener"], why_now=lead["pitch"]["why_now"],
                            proof=lead["pitch"]["proof"])) if not suppressed else None
        objection = dict(en=dict(q=lead["objection"]["q"], a=lead["objection"]["a"]),
                         hi=dict(q=lead["objection"]["q"], a=lead["objection"]["a"])) \
            if not suppressed else None
        row = dict(
            id=cust_id, cif_id=_cif_id(cust_id), segment=lead["segment"], age=lead["age"],
            city_tier=lead["city_tier"], tenure_m=lead["tenure_m"], consent=bool(lead["consent"]),
            product=lead["product"], product_menu=menu, tier=lead["tier"], lang=lead["lang"],
            # `score` is the queue's ordering key (model.policy.DEFAULT_RANKING);
            # `intent`, `capacity` and `blend` ride along as displayed signals.
            score=lead["score"], intent=lead["intent"], capacity=lead["capacity"],
            blend=lead["blend"],
            # The three clocks, each with one meaning (review §5). `contact_by`
            # is `abandoned_at + window`, which is what the platform backend
            # computes from `journeys.abandon_ts`; they used to disagree.
            abandoned_at=lead["abandoned_at"], scored_at=lead["scored_at"],
            contact_by=lead["contact_by"], window_days=int(lead["window_days"]),
            outcome_horizon_days=int(lead["outcome_horizon_days"]),
            salary_m=float(lead["salary_m"]), retained_income=float(lead["retained_income"]),
            safe_emi=float(lead["safe_emi"]),
            amortisation_ref=(amort_ref_by_product.get(lead["product"]) if not suppressed else None),
            reasons=lead["reasons"][:5],
            negative_signals=[dict(signal=_NEGATIVE_SIGNAL.get(c.get("signal"), "vague_answers"),
                                   label=c["text"])
                              for c in lead.get("negative_chips", [])][:5],
            pitch=pitch, objection=objection, nba=lead["nba"], suppressed=suppressed,
            suppression_reasons=suppression_reasons, assigned_rm_id=assigned_rm_id,
            # The abandoned attempt this lead revives (`model.pack.scored_attempts`),
            # and the row in `journeys[]` the platform joins to for the drawer's
            # window block.  It was `None` on every lead until 2026-09-21, which
            # left `window.abandoned_at`, `due_by`, `open` and `expired` null on
            # every real export while the bank FIXTURE set it and looked fine.
            journey_ref=lead.get("journey_ref"), spark=lead["spark"], provenance=dict(
                identity="SIMULATED", casa_behaviour="SIMULATED", cross_bank="SIMULATED",
                holdings="SIMULATED", digital="SIMULATED", consent="SIMULATED",
                journey="SIMULATED", model="SIMULATED"),
        )
        if lead.get("uplift_tag"):
            row["uplift_tag"] = lead["uplift_tag"]
        if lead.get("uplift_pct") is not None:
            row["uplift_pct"] = lead["uplift_pct"]
        if lead.get("queue_rank") is not None:
            row["queue_rank"] = int(lead["queue_rank"])
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #

def build_export(cfg, meta: dict, counts: dict, metrics: dict, leads_internal: list[dict],
                 gig_case_id: str, snap_rows: pd.DataFrame, tables: dict,
                 rm_map: dict, bank_ctx: B.BankContext) -> dict:
    amort_schedules, amort_ref_by_product = build_amortisation_schedules()
    cust_ids = snap_rows["cust_id"].astype(str).tolist()
    return dict(
        meta=build_meta(meta, bank_ctx, cfg.seed),
        counts=build_counts(counts),
        metrics=build_metrics(metrics),
        customers=build_customers(snap_rows, rm_map, bank_ctx),
        journeys=build_journeys(tables["journeys"], tables["events"], tables["label_truth"],
                               cust_ids, bank_ctx),
        leads=build_leads(leads_internal, rm_map, amort_ref_by_product),
        amortisation_schedules=amort_schedules,
        gig_case_id=str(gig_case_id),
    )


def write(payload: dict, path: Path) -> None:
    import json

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating, float)):
            v = float(o)
            return None if not np.isfinite(v) else round(v, 6)
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, pd.Timestamp):
            return o.isoformat()
        return o

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(payload), ensure_ascii=False, allow_nan=False,
                               separators=(",", ":")), encoding="utf-8")


__all__ = ["build_export", "build_meta", "build_counts", "build_metrics",
           "build_customers", "build_journeys", "build_amortisation_schedules",
           "build_leads", "write", "SCHEMA_VERSION"]
