# SANKET — validation pack

The acceptance criteria for the SANKET prospect-assist model, the harness that
checks them, and the report a bank model-risk reviewer reads.

```
validation/
  criteria.yaml   the contract: 25 pre-registered bands + 1 added, 7 cuts, splits, seeds
  criteria.py     schema + loader (pydantic v2) and the runner contract
  run.py          discovery, execution, grading, exit code
  report.py       REPORT.md + report.json + figures/
  runners/        01_holdout … 12_baseline_ladder
  tests/          tests for the contract itself
  Makefile        make -C validation validate
  report/         generated output — gitignored, never committed by hand
```

## The principle: pre-registration

**`criteria.yaml` is committed before the first model result exists.** That
commit's git timestamp is the evidence. It is the only thing that distinguishes
"our model converts 30 in 100 targeted calls" from "we decided 30 was the bar
once we saw 30", and the two claims are worth very different amounts to a
reviewer.

Three practices follow from it, and they are the whole point of this directory:

1. **Bands are written down before results, not after.** Every criterion carries
   a `source:` pointing at the clause of the build plan it came from, so a
   reviewer can check the transcription rather than trust it.
2. **Criteria may be added, never loosened.** See "Changing a criterion" below.
3. **Where a band was ambiguous, the interpretation is recorded in the file**, in
   that criterion's `note:` — at registration time, while we still did not know
   which reading would flatter us.

Two bands are worth knowing before you read the report:

- **The headline is a band with a ceiling, not a floor.** Precision at the 10%
  contact budget is registered at **25–35%** (`SK-02`), and the baseline it is
  quoted against is registered separately at **8–10%** (`SK-01`). A synthetic
  book that yielded 60% precision would *fail*, because no bank reviewer would
  believe it. The claim that goes in the deck is emitted from the same run as the
  evidence (`SK-06`) rather than typed, so the number and its proof cannot drift
  apart — it currently reads **"9 → 29 disbursements per 100 RM calls"**, and it
  is measured on exactly the list the RM queue delivers (`src/model/policy.py`;
  see `MODEL_CARD.md` §8), not on a different ranking.
- **Top-1 product accuracy is registered with no target** (`SK-14`,
  `severity: report`). Setting one would push the model back toward the single
  next-best-product behaviour the menu of four exists to replace.

Likewise `SK-24`: the gig-worker fairness gap is a **disclosed** finding, not a
gated one. Irregular gig income reads as instability to a model trained mostly on
salaried credits, so gig workers are under-contacted. Tuning that away on
synthetic data would be pretending to have solved it; it is quantified in the
report and carried into the README's "What we did not build, and why".

## Running it

```bash
make -C validation validate          # run everything, write the report
make -C validation validate-strict   # the G7 gate form: pending and warn also fail
make -C validation criteria-test     # check the contract itself
make -C validation list              # print the bands without running anything
make -C validation deps              # pydantic v2, PyYAML, pytest
```

Equivalently, from the repository root:

```bash
python3 -m validation.run --criteria validation/criteria.yaml --out validation/report/
```

Useful flags: `--runner 03_by_cut` (repeatable) to run one runner; `--strict` for
the gate form; `--list` to dump the registered bands and exit.

Requires Python 3.12, `pydantic>=2`, `PyYAML`. The runners themselves will need
the pipeline's own dependencies (pandas, numpy, scikit-learn, lightgbm), which
the repo already has.

**Exit codes:** `0` no `fail` criterion failed · `1` at least one did (or, under
`--strict`, something is pending or warned) · `2` `criteria.yaml` would not load.
The deploy pipeline's verify step and gate G7 read the exit code; a model run
that fails verification stays `candidate` and never replaces the active run.

## Reading the report

`make validate` writes three things into `validation/report/`:

- **`REPORT.md`** — for humans. Leads with the verdict and the pre-registration
  statement (including when `criteria.yaml` actually entered git), then
  **failures first**, then pending criteria, then every criterion by runner with
  its band beside its observed value, then the registered rationale for each band
  in prose. Per-cut criteria carry a collapsible per-cell breakdown.
- **`report.json`** — the machine-readable twin. Read by the deploy verify step
  and open on screen during the G5 honesty gate, where every number in the README
  and the deck has to trace back to a row in it.
- **`figures/`** — plots the runners emit; each is named in its criterion's
  result so a figure can always be traced to the band it illustrates.

Statuses, in the order they matter:

| Status | Means |
|---|---|
| `fail` | the band was not met, and the criterion gates |
| `error` | the runner raised — treated as a failure |
| `warn` | the band was not met, and the criterion does not gate |
| `pending` | no result yet. **Not a pass.** `--strict` fails on it |
| `skipped_low_n` | the cell had fewer rows than the pre-registered `min_n`. Reported with its n, never silently dropped |
| `report` | no comparison is made; the value is recorded for a human to read |
| `pass` | the band was met |

`pending` is the one to watch today: the runners are stubs, so a plain
`make validate` currently exits 0 with every criterion pending. That is not a
pass, and `validate-strict` — the form gate G7 uses — correctly exits non-zero.

## Adding a criterion

1. Append an entry to `criteria:` in `criteria.yaml` with a **new** id
   (`SK-NN`), a `runner` from the twelve, a `metric`, a `scope`, an `op` and
   `threshold`, a `min_n`, a `severity`, a `rationale` and a `source`. Add a
   `note:` if the band needs interpreting, and — if the registration date has
   passed — an **`added_at:`** timestamp. That field is what keeps `REPORT.md`
   honest: the pre-registration sentence counts only the bands that were in the
   file at `registered_at`, and every later addition is listed separately
   underneath it instead of being folded into the claim. Record the reason in
   `amendments:` at the same time (`loosening: false`) so a reviewer reads it in
   the report rather than in a diff.
2. Run `make -C validation criteria-test`. The schema rejects duplicate ids,
   unknown runners, non-numeric thresholds, inverted `between` bounds, and a
   `per_cut` criterion naming a cut that is not declared.
3. Teach the relevant runner to emit a `Result` for the new id. Runners measure;
   they never set `status` — the harness grades, so no runner can pass itself.

**The rule: criteria may only be ADDED after registration, never loosened.**
Adding a band makes the pack stricter, which no reviewer objects to. Widening
one, lowering a floor, raising a ceiling, changing `fail` to `report`, or raising
a `min_n` to exempt an inconvenient cell all weaken a claim that was already made,
and doing that quietly is indistinguishable from fitting the bar to the result.

If a band genuinely must change, it requires an `amendments:` entry at the foot
of `criteria.yaml`:

```yaml
amendments:
  - at: "2026-09-24T18:40:00+05:30"
    by: "RR Squad"
    criteria: ["SK-13"]
    change: "Menu-of-4 hit rate floor 0.80 -> 0.75."
    rationale: >-
      Why, in terms a bank reviewer would accept. "It was failing" is not a
      rationale.
    loosening: true
```

`loosening: true` is not decoration: `REPORT.md` prints amendments in the
pre-registration section, and a loosening is flagged there for the reviewer.

Clarifications that do not change a band — resolving an ambiguity, correcting a
count — go in `rulings:` instead, with their own timestamp.

## Writing a runner

Replace the stub in `runners/`. The contract is one function:

```python
def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]: ...
```

Each stub's docstring already names the files and columns it will consume and the
figures it will produce, including the two files the generator lane has yet to
create (`data/application_journeys.csv`, `data/liability_book_truth.csv`). Set
`value`, `ci`, `n` — and `breakdown` (one dict per cell, with `level`, `value`,
`ci`, `n`) for a per-cut or per-product criterion. Leave `status` alone. A runner
that stays silent about one of its criteria leaves it `pending`; it cannot
accidentally pass.

Bootstrap at the group level (`cust_id`) — a customer contributes many months and
a row-level bootstrap would report intervals that are far too tight.

One standing hazard, worth repeating here because it is the easiest way to
produce a beautiful and worthless number: every journey feature is computed from
a timeline that ends in the very outcome being predicted. `SK-17` gates the count
of features drawing on data after `abandon_ts` at **zero**.
