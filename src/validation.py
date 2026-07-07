from __future__ import annotations

from .config import Settings
from .models import AnalysisResult, ValidationItem, ValidationResult


def _number(value: float | int | str | None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def validate_candidate(
    result: AnalysisResult,
    settings: Settings,
    min_score: int = 65,
    min_technical_passed: int = 4,
) -> ValidationResult:
    price = _number(result.metrics.get("current_price"))
    market_cap = _number(result.metrics.get("market_cap"))
    dollar_volume = _number(result.metrics.get("avg_dollar_volume_50"))
    technical_passed = _number(result.metrics.get("technical_checks_passed"))

    items = [
        ValidationItem(
            label="가격 데이터",
            passed=not result.errors,
            detail="분석 가능한 1년 가격 데이터 확보" if not result.errors else ", ".join(result.errors),
        ),
        ValidationItem(
            label="최소 점수",
            passed=result.score >= min_score,
            detail=f"{result.score}점 / 기준 {min_score}점",
        ),
        ValidationItem(
            label="핵심 기술 조건",
            passed=technical_passed is not None and technical_passed >= min_technical_passed,
            detail=f"{int(technical_passed or 0)}/6개 통과 / 기준 {min_technical_passed}개",
        ),
        ValidationItem(
            label="시가총액",
            passed=market_cap is not None and market_cap >= settings.min_market_cap_usd,
            detail=f"{market_cap:,.0f} / 기준 {settings.min_market_cap_usd:,.0f}" if market_cap is not None else "데이터 없음",
        ),
        ValidationItem(
            label="거래대금",
            passed=dollar_volume is not None and dollar_volume >= settings.min_avg_dollar_volume_usd,
            detail=f"{dollar_volume:,.0f} / 기준 {settings.min_avg_dollar_volume_usd:,.0f}" if dollar_volume is not None else "데이터 없음",
        ),
        ValidationItem(
            label="최소 주가",
            passed=price is not None and price >= settings.min_price_usd,
            detail=f"${price:.2f} / 기준 ${settings.min_price_usd:.2f}" if price is not None else "데이터 없음",
        ),
    ]
    return ValidationResult(
        ticker=result.ticker,
        passed=all(item.passed for item in items),
        items=items,
    )


def is_recommendable(result: AnalysisResult, settings: Settings, min_score: int = 65) -> bool:
    return validate_candidate(result, settings, min_score=min_score).passed
