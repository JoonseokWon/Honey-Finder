from __future__ import annotations

from .config import Settings
from .models import AnalysisResult, RecommendationFilters

SECTOR_LABELS = {
    "all": "전체 섹터",
    "technology": "기술",
    "communication": "커뮤니케이션",
    "consumer": "소비재",
    "healthcare": "헬스케어",
    "financial": "금융",
    "industrial": "산업재",
    "energy": "에너지",
    "other": "기타",
}

STYLE_LABELS = {
    "balanced": "균형형",
    "aggressive": "공격형",
    "conservative": "보수형",
    "near_high": "52주 고점 근접",
    "volume": "거래량 증가",
    "quality": "재무 품질",
}


def normalize_sector(raw_sector: str | None) -> str:
    if not raw_sector:
        return "other"

    value = raw_sector.lower()
    if "technology" in value:
        return "technology"
    if "communication" in value:
        return "communication"
    if "consumer" in value:
        return "consumer"
    if "health" in value:
        return "healthcare"
    if "financial" in value:
        return "financial"
    if "industrial" in value:
        return "industrial"
    if "energy" in value:
        return "energy"
    return "other"


def filter_matches(result: AnalysisResult, filters: RecommendationFilters, settings: Settings) -> bool:
    if filters.sector != "all" and result.metrics.get("sector_key") != filters.sector:
        return False

    if result.score < filters.min_score:
        return False

    if filters.style == "aggressive":
        return result.score >= max(filters.min_score, 75)

    if filters.style == "conservative":
        market_cap = _number(result.metrics.get("market_cap"))
        dollar_volume = _number(result.metrics.get("avg_dollar_volume_50"))
        return (
            market_cap is not None
            and dollar_volume is not None
            and market_cap >= max(settings.min_market_cap_usd, 5_000_000_000)
            and dollar_volume >= max(settings.min_avg_dollar_volume_usd, 50_000_000)
        )

    if filters.style == "near_high":
        high_ratio = _number(result.metrics.get("price_to_52w_high"))
        return high_ratio is not None and high_ratio >= 0.85

    if filters.style == "volume":
        volume_ratio = _number(result.metrics.get("recent_volume_ratio"))
        return volume_ratio is not None and volume_ratio >= 1.10

    if filters.style == "quality":
        revenue_growth = _number(result.metrics.get("revenue_growth"))
        operating_margin = _number(result.metrics.get("operating_margin"))
        return (
            revenue_growth is not None
            and operating_margin is not None
            and revenue_growth > 0
            and operating_margin >= 0.10
        )

    return True


def describe_filters(filters: RecommendationFilters) -> str:
    sector = SECTOR_LABELS.get(filters.sector, filters.sector)
    style = STYLE_LABELS.get(filters.style, filters.style)
    return f"상위 분류: {sector} / 하위 기준: {style} / 최소점수: {filters.min_score} / 표시개수: {filters.limit}"


def _number(value: float | int | str | None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
