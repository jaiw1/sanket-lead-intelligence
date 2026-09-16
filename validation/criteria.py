"""
Schema and loader for the pre-registered acceptance criteria.

`criteria.yaml` is a contract, not a config file: it is committed before the
first model result exists, and its git timestamp is the evidence that the bands
were not tuned to fit an outcome. This module is what makes that contract
machine-checkable — it refuses to load a file whose shape has drifted, so a
malformed or silently-edited criteria file fails loudly instead of validating
nothing.

Also defines the two small types the runners exchange with the harness
(`RunnerContext` in, `Result` out). They live here, next to the schema, so that
runners never import `validation.run` and no import cycle can form.

Requires: Python 3.12, pydantic v2, PyYAML.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# The twelve runners. The names are fixed by the plan (§B lanes L8/L9); run.py
# discovers modules by these names and runs the ones that are present.
# ---------------------------------------------------------------------------
RUNNERS: tuple[str, ...] = (
    "01_holdout",
    "02_oot",
    "03_by_cut",
    "04_calibration",
    "05_rank_order",
    "06_stability",
    "07_leakage",
    "08_ablation",
    "09_seeds",
    "10_stress",
    "11_fairness",
    "12_baseline_ladder",
)

Severity = Literal["fail", "warn", "report"]
Scope = Literal["overall", "per_cut", "per_portfolio", "per_product"]
Op = Literal[
    "ge", "le", "gt", "lt", "eq", "ne",
    "between",              # threshold is [lo, hi], inclusive at both ends
    "monotone_increasing",  # strictly increasing sequence; ties fail
    "exists",               # an artefact must be present and non-empty
    "report",               # record the value; no comparison is made
]

#: Ops that carry no numeric threshold.
_THRESHOLDLESS: frozenset[str] = frozenset({"monotone_increasing", "exists", "report"})

#: Statuses a Result may carry. `pending` is not a pass and never becomes one.
Status = Literal["pass", "fail", "warn", "report", "pending", "skipped_low_n", "error"]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class Criterion(BaseModel):
    """One pre-registered acceptance band."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z]{2}-\d{2}$")
    runner: str
    metric: str
    scope: Scope
    cut: str | None = None
    op: Op
    threshold: float | int | list[float | int] | None = None
    min_n: int = Field(ge=0)
    severity: Severity
    rationale: str = Field(min_length=1)
    source: str = Field(min_length=1)
    note: str | None = None

    @field_validator("runner")
    @classmethod
    def _known_runner(cls, v: str) -> str:
        if v not in RUNNERS:
            raise ValueError(f"unknown runner {v!r}; must be one of {', '.join(RUNNERS)}")
        return v

    @model_validator(mode="after")
    def _threshold_matches_op(self) -> "Criterion":
        if self.op == "between":
            if not isinstance(self.threshold, list) or len(self.threshold) != 2:
                raise ValueError(f"{self.id}: op 'between' needs a [lo, hi] threshold")
            lo, hi = self.threshold
            if not all(isinstance(x, (int, float)) for x in (lo, hi)):
                raise ValueError(f"{self.id}: 'between' bounds must be numeric")
            if lo >= hi:
                raise ValueError(f"{self.id}: 'between' bounds must satisfy lo < hi, got {lo} >= {hi}")
        elif self.op in _THRESHOLDLESS:
            if self.threshold is not None:
                raise ValueError(f"{self.id}: op {self.op!r} takes no threshold")
        else:
            if not isinstance(self.threshold, (int, float)) or isinstance(self.threshold, bool):
                raise ValueError(f"{self.id}: op {self.op!r} needs a single numeric threshold")

        if self.scope == "per_cut" and not self.cut:
            raise ValueError(f"{self.id}: scope 'per_cut' must name a cut (or 'all')")
        if self.scope != "per_cut" and self.cut:
            raise ValueError(f"{self.id}: `cut` is only meaningful when scope is 'per_cut'")
        return self

    # -- evaluation ---------------------------------------------------------
    def check(self, value: Any) -> bool | None:
        """Compare an observed value against this band.

        Returns True/False, or None when the criterion makes no comparison
        (`op: report`) or the value is missing.
        """
        if self.op == "report" or value is None:
            return None
        if self.op == "exists":
            return bool(value)
        if self.op == "monotone_increasing":
            seq = list(value)
            return all(a < b for a, b in zip(seq, seq[1:]))
        t = self.threshold
        if self.op == "between":
            return bool(t[0] <= value <= t[1])
        return {
            "ge": lambda: value >= t,
            "le": lambda: value <= t,
            "gt": lambda: value > t,
            "lt": lambda: value < t,
            "eq": lambda: value == t,
            "ne": lambda: value != t,
        }[self.op]()

    def band_text(self) -> str:
        """Human-readable band, for REPORT.md."""
        symbols = {"ge": "≥", "le": "≤", "gt": ">", "lt": "<", "eq": "=", "ne": "≠"}
        if self.op == "between":
            return f"∈ [{self.threshold[0]}, {self.threshold[1]}]"
        if self.op == "monotone_increasing":
            return "strictly increasing"
        if self.op == "exists":
            return "must exist"
        if self.op == "report":
            return "reported, no target"
        return f"{symbols[self.op]} {self.threshold}"


class Cut(BaseModel):
    """One dimension the per-cut criteria are evaluated over."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_column: str
    expected_levels: int | None = None
    levels: list[str] | None = None
    binning: str | None = None
    min_n: int = Field(default=0, ge=0)
    note: str | None = None


class Seeds(BaseModel):
    # The YAML key is `list`; the attribute is `seed_list`, because a field
    # literally named `list` would shadow the builtin inside this class's
    # annotation namespace and pydantic could not resolve `list[int] | None`.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    n_min: int = Field(ge=1)
    seed_list: list[int] | None = Field(default=None, alias="list")
    policy: str | None = None

    @model_validator(mode="after")
    def _enough_seeds_listed(self) -> "Seeds":
        if self.seed_list is not None:
            if len(set(self.seed_list)) != len(self.seed_list):
                raise ValueError("seeds.list contains duplicates")
            if len(self.seed_list) < self.n_min:
                raise ValueError(
                    f"seeds.list has {len(self.seed_list)} seeds, n_min is {self.n_min}"
                )
        return self


class Ruling(BaseModel):
    """A clarification issued while still pre-registering — never a loosening."""

    model_config = ConfigDict(extra="forbid")

    at: _dt.datetime
    ruling: str
    affects: list[str] = Field(default_factory=list)
    effect: str | None = None


class Amendment(BaseModel):
    """A post-registration change. Requires a date and a reason, always."""

    model_config = ConfigDict(extra="forbid")

    at: _dt.datetime
    by: str
    criteria: list[str] = Field(default_factory=list)
    change: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    loosening: bool = False


class CriteriaDoc(BaseModel):
    """The whole `criteria.yaml`."""

    model_config = ConfigDict(extra="allow")

    product: str
    schema_version: str
    registered_at: _dt.datetime
    registered_by: str
    repo: str | None = None
    plan_reference: str | None = None
    rulings: list[Ruling] = Field(default_factory=list)
    label_definition: dict[str, Any]
    splits: dict[str, Any]
    cuts: list[Cut]
    seeds: Seeds
    confidence: dict[str, Any] | None = None
    decision_rule: dict[str, Any] | None = None
    criteria: list[Criterion]
    amendments: list[Amendment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _structural_checks(self) -> "CriteriaDoc":
        ids = [c.id for c in self.criteria]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate criterion ids: {', '.join(dupes)}")

        cut_ids = {c.id for c in self.cuts}
        cut_dupes = sorted({c.id for c in self.cuts if [x.id for x in self.cuts].count(c.id) > 1})
        if cut_dupes:
            raise ValueError(f"duplicate cut ids: {', '.join(cut_dupes)}")

        # A per_cut criterion may target 'all', a named cut, or a documented
        # pseudo-cut (e.g. 'protected_proxies' for fairness).
        pseudo = {"all", "protected_proxies"}
        for c in self.criteria:
            if c.scope == "per_cut" and c.cut not in cut_ids | pseudo:
                raise ValueError(
                    f"{c.id}: cut {c.cut!r} is not declared in `cuts:` "
                    f"(known: {', '.join(sorted(cut_ids | pseudo))})"
                )

        if "holdout" not in self.splits or "oot" not in self.splits:
            raise ValueError("splits must declare both 'holdout' and 'oot'")

        if not self.criteria:
            raise ValueError("criteria list is empty")
        return self

    # -- convenience --------------------------------------------------------
    def by_runner(self, runner: str) -> list[Criterion]:
        return [c for c in self.criteria if c.runner == runner]

    def runners_used(self) -> list[str]:
        used = {c.runner for c in self.criteria}
        return [r for r in RUNNERS if r in used]

    def get(self, criterion_id: str) -> Criterion:
        for c in self.criteria:
            if c.id == criterion_id:
                return c
        raise KeyError(criterion_id)


# ---------------------------------------------------------------------------
# Runner contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunnerContext:
    """Everything a runner is handed. Runners read; only the harness writes."""

    repo_root: Path
    out_dir: Path
    figures_dir: Path
    doc: CriteriaDoc
    seeds: tuple[int, ...]
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """One runner's finding for one criterion.

    `status` is assigned by the harness from `value` and the criterion's band —
    a runner reports what it measured, it does not grade itself. It therefore
    defaults to None ("not graded yet"), NOT to "pending": a runner that returned
    a real measurement must be graded, and only the harness may declare a
    criterion pending.
    """

    criterion_id: str
    value: Any = None
    ci: tuple[float, float] | list[float] | None = None
    n: int | None = None
    status: Status | None = None
    detail: str | None = None
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "value": self.value,
            "ci": list(self.ci) if self.ci is not None else None,
            "n": self.n,
            "status": self.status or "pending",
            "detail": self.detail,
            "breakdown": self.breakdown,
            "figures": self.figures,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
class CriteriaError(RuntimeError):
    """Raised when criteria.yaml is missing, unparseable or off-schema."""


def load(path: str | Path) -> CriteriaDoc:
    """Load and fully validate a criteria file."""
    p = Path(path)
    if not p.is_file():
        raise CriteriaError(f"criteria file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CriteriaError(f"{p}: not valid YAML — {exc}") from exc
    if not isinstance(raw, dict):
        raise CriteriaError(f"{p}: expected a mapping at the top level")
    try:
        return CriteriaDoc.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError, deliberately widened
        raise CriteriaError(f"{p}: does not match the criteria schema —\n{exc}") from exc
