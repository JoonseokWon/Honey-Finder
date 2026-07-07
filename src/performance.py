from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .analysis import analyze_ticker
from .config import Settings
from .models import AnalysisResult, RecommendationEvaluation, RecommendationRecord

STORE_PATH = Path("data") / "recommendations.json"


def _load_records(path: Path = STORE_PATH) -> list[RecommendationRecord]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [RecommendationRecord(**item) for item in payload]


def _save_records(records: list[RecommendationRecord], path: Path = STORE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(record) for record in records]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record_recommendations(
    results: list[AnalysisResult],
    min_score: int,
    path: Path = STORE_PATH,
) -> str | None:
    if not results:
        return None

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    recommended_at = datetime.now(timezone.utc).isoformat()
    records = _load_records(path)

    for result in results:
        price = result.metrics.get("current_price")
        technical_checks_passed = result.metrics.get("technical_checks_passed")
        if not isinstance(price, (int, float)):
            continue
        records.append(
            RecommendationRecord(
                batch_id=batch_id,
                recommended_at=recommended_at,
                ticker=result.ticker,
                name=result.name,
                price=float(price),
                score=result.score,
                grade=result.grade,
                min_score=min_score,
                technical_checks_passed=int(technical_checks_passed or 0),
            )
        )

    _save_records(records, path)
    return batch_id


def _latest_record_per_ticker(records: list[RecommendationRecord]) -> list[RecommendationRecord]:
    latest: dict[str, RecommendationRecord] = {}
    for record in records:
        current = latest.get(record.ticker)
        if current is None or record.recommended_at > current.recommended_at:
            latest[record.ticker] = record
    return sorted(latest.values(), key=lambda item: item.recommended_at, reverse=True)


def evaluate_recommendations(
    settings: Settings,
    ticker: str | None = None,
    target_return_pct: float = 0.10,
    fail_return_pct: float = -0.08,
    latest_only: bool = True,
    path: Path = STORE_PATH,
) -> list[RecommendationEvaluation]:
    records = _load_records(path)
    if ticker:
        symbol = ticker.strip().upper()
        records = [record for record in records if record.ticker == symbol]

    if latest_only:
        records = _latest_record_per_ticker(records)

    evaluations: list[RecommendationEvaluation] = []
    for record in records:
        result = analyze_ticker(record.ticker, settings)
        current_price = result.metrics.get("current_price")
        if not isinstance(current_price, (int, float)):
            evaluations.append(
                RecommendationEvaluation(
                    record=record,
                    current_price=None,
                    return_pct=None,
                    days_elapsed=_days_elapsed(record.recommended_at),
                    verdict="데이터 부족",
                    detail="현재 가격 데이터를 확인하지 못했습니다.",
                )
            )
            continue

        return_pct = float(current_price) / record.price - 1
        if return_pct >= target_return_pct:
            verdict = "성공"
            detail = f"목표 수익률 {target_return_pct:.1%} 이상입니다."
        elif return_pct <= fail_return_pct:
            verdict = "실패"
            detail = f"손실 기준 {fail_return_pct:.1%} 이하입니다."
        else:
            verdict = "관찰"
            detail = "아직 성공/실패 기준 사이에 있습니다."

        evaluations.append(
            RecommendationEvaluation(
                record=record,
                current_price=float(current_price),
                return_pct=return_pct,
                days_elapsed=_days_elapsed(record.recommended_at),
                verdict=verdict,
                detail=detail,
            )
        )

    return evaluations


def _days_elapsed(iso_datetime: str) -> int:
    recommended_at = datetime.fromisoformat(iso_datetime)
    if recommended_at.tzinfo is None:
        recommended_at = recommended_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - recommended_at).days
