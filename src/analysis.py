from __future__ import annotations

import math
from typing import Any

import pandas as pd
import yfinance as yf

from .config import Settings
from .models import AnalysisResult, CheckResult
from .validation import is_recommendable


def _last_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        return float(value)
    return None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _fmt_usd(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 75:
        return "B+"
    if score >= 65:
        return "B"
    if score >= 55:
        return "C+"
    if score >= 45:
        return "C"
    return "D"


def _add_check(
    checks: list[CheckResult],
    label: str,
    passed: bool,
    detail: str,
    points: int,
) -> None:
    checks.append(
        CheckResult(
            label=label,
            passed=passed,
            detail=detail,
            points=points if passed else 0,
        )
    )


def _get_info_number(info: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _last_number(info.get(key))
        if value is not None:
            return value
    return None


def _first_available_row(frame: pd.DataFrame, labels: list[str]) -> pd.Series | None:
    for label in labels:
        if label in frame.index:
            return frame.loc[label]
    return None


def _financial_signals(ticker: yf.Ticker) -> tuple[list[str], list[str], dict[str, float | None]]:
    positives: list[str] = []
    cautions: list[str] = []
    metrics: dict[str, float | None] = {}

    financials = ticker.financials
    balance_sheet = ticker.balance_sheet
    info = ticker.info or {}

    revenue_growth = None
    operating_margin = _get_info_number(info, "operatingMargins")
    debt_to_assets = None

    if not financials.empty:
        revenue_row = _first_available_row(financials, ["Total Revenue", "Operating Revenue"])
        operating_income_row = _first_available_row(financials, ["Operating Income"])

        if revenue_row is not None and len(revenue_row.dropna()) >= 2:
            latest_revenue = float(revenue_row.dropna().iloc[0])
            previous_revenue = float(revenue_row.dropna().iloc[1])
            revenue_growth = _safe_ratio(latest_revenue - previous_revenue, abs(previous_revenue))

            if revenue_growth is not None and revenue_growth > 0:
                positives.append("최근 연간 매출이 전년 대비 증가했습니다.")
            elif revenue_growth is not None:
                cautions.append("최근 연간 매출이 전년 대비 감소했습니다.")

        if operating_margin is None and revenue_row is not None and operating_income_row is not None:
            latest_revenue = float(revenue_row.dropna().iloc[0]) if not revenue_row.dropna().empty else None
            latest_operating_income = (
                float(operating_income_row.dropna().iloc[0])
                if not operating_income_row.dropna().empty
                else None
            )
            operating_margin = _safe_ratio(latest_operating_income, latest_revenue)

    if not balance_sheet.empty:
        debt_row = _first_available_row(balance_sheet, ["Total Debt", "Total Liabilities Net Minority Interest"])
        assets_row = _first_available_row(balance_sheet, ["Total Assets"])
        if debt_row is not None and assets_row is not None:
            latest_debt = float(debt_row.dropna().iloc[0]) if not debt_row.dropna().empty else None
            latest_assets = float(assets_row.dropna().iloc[0]) if not assets_row.dropna().empty else None
            debt_to_assets = _safe_ratio(latest_debt, latest_assets)

    if operating_margin is not None:
        if operating_margin >= 0.15:
            positives.append("최근 영업이익률이 양호합니다.")
        elif operating_margin < 0.05:
            cautions.append("영업이익률이 낮거나 이익 체력이 약할 수 있습니다.")

    if debt_to_assets is not None:
        if debt_to_assets <= 0.5:
            positives.append("총자산 대비 부채 부담이 과도해 보이지 않습니다.")
        elif debt_to_assets > 0.75:
            cautions.append("총자산 대비 부채 부담이 높은 편입니다.")

    trailing_pe = _get_info_number(info, "trailingPE")
    forward_pe = _get_info_number(info, "forwardPE")
    if trailing_pe is not None and trailing_pe > 60:
        cautions.append("후행 PER 기준 밸류에이션 부담이 있을 수 있습니다.")
    if forward_pe is not None and forward_pe > 45:
        cautions.append("선행 PER 기준 기대치가 높게 반영되어 있을 수 있습니다.")

    metrics.update(
        {
            "revenue_growth": revenue_growth,
            "operating_margin": operating_margin,
            "debt_to_assets": debt_to_assets,
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
        }
    )
    return positives, cautions, metrics


def analyze_ticker(ticker_symbol: str, settings: Settings) -> AnalysisResult:
    symbol = ticker_symbol.strip().upper()
    ticker = yf.Ticker(symbol)
    history = ticker.history(period="1y", interval="1d", auto_adjust=False)

    if history.empty or len(history) < 220:
        return AnalysisResult(
            ticker=symbol,
            name=symbol,
            score=0,
            grade="N/A",
            summary=f"{symbol} 분석에 필요한 가격 데이터가 충분하지 않습니다.",
            checks=[],
            positives=[],
            cautions=["가격 데이터가 부족하거나 티커가 올바르지 않을 수 있습니다."],
            metrics={},
            errors=["insufficient_price_history"],
        )

    history = history.dropna(subset=["Close", "Volume"]).copy()
    close = history["Close"]
    volume = history["Volume"]
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    current_price = float(close.iloc[-1])
    avg_volume_50 = float(volume.tail(50).mean())
    avg_dollar_volume_50 = current_price * avg_volume_50
    week52_high = float(close.max())
    week52_low = float(close.min())
    current_ma50 = float(ma50.iloc[-1])
    current_ma150 = float(ma150.iloc[-1])
    current_ma200 = float(ma200.iloc[-1])
    ma200_month_ago = float(ma200.iloc[-22])
    recent_volume = float(volume.tail(5).mean())

    info = ticker.info or {}
    name = info.get("shortName") or info.get("longName") or symbol
    market_cap = _get_info_number(info, "marketCap")

    checks: list[CheckResult] = []
    _add_check(
        checks,
        "현재가가 150일/200일 이동평균선 위",
        current_price > current_ma150 and current_price > current_ma200,
        f"현재가 {current_price:.2f}, 150일선 {current_ma150:.2f}, 200일선 {current_ma200:.2f}",
        16,
    )
    _add_check(
        checks,
        "50일 이동평균선이 150일/200일 이동평균선 위",
        current_ma50 > current_ma150 and current_ma50 > current_ma200,
        f"50일선 {current_ma50:.2f}, 150일선 {current_ma150:.2f}, 200일선 {current_ma200:.2f}",
        12,
    )
    _add_check(
        checks,
        "200일 이동평균선 상승",
        current_ma200 > ma200_month_ago,
        f"현재 200일선 {current_ma200:.2f}, 약 1개월 전 {ma200_month_ago:.2f}",
        12,
    )
    _add_check(
        checks,
        "52주 고점 근접",
        current_price >= week52_high * 0.75,
        f"현재가가 52주 고점의 {current_price / week52_high:.1%} 수준",
        12,
    )
    _add_check(
        checks,
        "52주 저점 대비 회복",
        current_price >= week52_low * 1.25,
        f"현재가가 52주 저점 대비 {current_price / week52_low - 1:.1%} 상승",
        10,
    )
    _add_check(
        checks,
        "최근 거래량 증가",
        recent_volume > avg_volume_50,
        f"최근 5일 평균 거래량 {recent_volume:,.0f}, 50일 평균 {avg_volume_50:,.0f}",
        8,
    )
    _add_check(
        checks,
        "시가총액 기준",
        market_cap is not None and market_cap >= settings.min_market_cap_usd,
        f"시가총액 {_fmt_usd(market_cap)}",
        10,
    )
    _add_check(
        checks,
        "50일 평균 거래대금 기준",
        avg_dollar_volume_50 >= settings.min_avg_dollar_volume_usd,
        f"50일 평균 거래대금 {_fmt_usd(avg_dollar_volume_50)}",
        10,
    )
    _add_check(
        checks,
        "최소 주가 기준",
        current_price >= settings.min_price_usd,
        f"현재가 ${current_price:.2f}",
        10,
    )

    financial_positives, financial_cautions, financial_metrics = _financial_signals(ticker)
    positives = financial_positives[:]
    cautions = financial_cautions[:]

    if market_cap is not None and market_cap >= settings.min_market_cap_usd and avg_dollar_volume_50 >= settings.min_avg_dollar_volume_usd:
        positives.append("시가총액과 거래대금 기준을 충족합니다.")
    if current_price < settings.min_price_usd:
        cautions.append("주가가 최소 가격 기준보다 낮아 변동성 또는 유동성 리스크가 커질 수 있습니다.")
    if market_cap is None:
        cautions.append("시가총액 데이터를 확인하지 못했습니다.")

    score = sum(check.points for check in checks)
    grade = _grade(score)
    passed_core = sum(check.passed for check in checks[:6])
    if score >= 75:
        summary = f"{symbol}는 미너비니식 기술 조건과 거래 가능성 조건을 상당수 충족합니다."
    elif score >= 55:
        summary = f"{symbol}는 일부 조건을 충족하지만 추가 확인이 필요한 관찰 후보입니다."
    else:
        summary = f"{symbol}는 현재 기준으로는 미너비니 후보 우선순위가 높지 않습니다."

    metrics: dict[str, float | int | str | None] = {
        "current_price": current_price,
        "ma50": current_ma50,
        "ma150": current_ma150,
        "ma200": current_ma200,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "market_cap": market_cap,
        "avg_dollar_volume_50": avg_dollar_volume_50,
        "technical_checks_passed": passed_core,
    }
    metrics.update(financial_metrics)

    return AnalysisResult(
        ticker=symbol,
        name=str(name),
        score=score,
        grade=grade,
        summary=summary,
        checks=checks,
        positives=positives or ["뚜렷한 긍정 요인은 추가 데이터 확인이 필요합니다."],
        cautions=cautions or ["현재 MVP 기준으로 두드러진 주의 신호는 확인되지 않았습니다."],
        metrics=metrics,
    )


def recommend_minervini_candidates(
    tickers: list[str],
    settings: Settings,
    limit: int = 5,
    min_score: int = 65,
) -> list[AnalysisResult]:
    results: list[AnalysisResult] = []

    for ticker in tickers:
        result = analyze_ticker(ticker, settings)
        if is_recommendable(result, settings, min_score=min_score):
            results.append(result)

    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]
