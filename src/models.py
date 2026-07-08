from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    label: str
    passed: bool
    detail: str
    points: int


@dataclass
class AnalysisResult:
    ticker: str
    name: str
    score: int
    grade: str
    summary: str
    checks: list[CheckResult]
    positives: list[str]
    cautions: list[str]
    metrics: dict[str, float | int | str | None]
    chart_path: Path | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationItem:
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    ticker: str
    passed: bool
    items: list[ValidationItem]


@dataclass(frozen=True)
class RecommendationRecord:
    batch_id: str
    recommended_at: str
    ticker: str
    name: str
    price: float
    score: int
    grade: str
    min_score: int
    technical_checks_passed: int


@dataclass(frozen=True)
class RecommendationEvaluation:
    record: RecommendationRecord
    current_price: float | None
    return_pct: float | None
    days_elapsed: int
    verdict: str
    detail: str


@dataclass(frozen=True)
class RecommendationFilters:
    sector: str = "all"
    style: str = "balanced"
    min_score: int = 65
    limit: int = 5
