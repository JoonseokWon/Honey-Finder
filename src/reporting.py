from __future__ import annotations

from .models import AnalysisResult, RecommendationEvaluation, ValidationResult


def _format_metric_percent(value: float | int | str | None) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "N/A"


def _format_metric_usd(value: float | int | str | None) -> str:
    if not isinstance(value, (int, float)):
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _format_price(value: float | int | str | None) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.2f}"
    return "N/A"


def build_report(result: AnalysisResult) -> str:
    lines: list[str] = [
        f"**{result.ticker} | {result.name}**",
        f"등급: **{result.grade}** / 점수: **{result.score}**",
        "",
        result.summary,
        "",
        "**핵심 지표**",
        f"- 현재가: {_format_price(result.metrics.get('current_price'))}",
        f"- 52주 고점/저점: {_format_price(result.metrics.get('week52_high'))} / {_format_price(result.metrics.get('week52_low'))}",
        f"- 52주 고점 대비: {_format_metric_percent(result.metrics.get('price_to_52w_high'))}",
        f"- 시가총액: {_format_metric_usd(result.metrics.get('market_cap'))}",
        f"- 50일 평균 거래대금: {_format_metric_usd(result.metrics.get('avg_dollar_volume_50'))}",
        f"- 섹터/산업: {result.metrics.get('sector') or 'N/A'} / {result.metrics.get('industry') or 'N/A'}",
        f"- 매출 성장률: {_format_metric_percent(result.metrics.get('revenue_growth'))}",
        f"- 영업이익률: {_format_metric_percent(result.metrics.get('operating_margin'))}",
        "",
        "**체크 결과**",
    ]

    for check in result.checks:
        status = "통과" if check.passed else "미통과"
        lines.append(f"- {status}: {check.label} ({check.detail})")

    lines.extend(["", "**긍정 요인**"])
    lines.extend(f"- {item}" for item in result.positives)

    lines.extend(["", "**주의 요인**"])
    lines.extend(f"- {item}" for item in result.cautions)

    lines.extend(["", "※ 이 결과는 투자자문이 아니라 데이터 기반 후보 진단입니다."])
    return _trim("\n".join(lines), "리포트")


def build_recommendation_report(
    results: list[AnalysisResult],
    scanned_count: int,
    min_score: int = 65,
    batch_id: str | None = None,
    filter_summary: str | None = None,
) -> str:
    lines = [
        "**미너비니 종목 추천 후보**",
        f"스캔 대상: {scanned_count}개 / 검증 기준: {min_score}점 이상 + 핵심 기술 조건 4개 이상 + 유동성 기준 통과",
    ]
    if filter_summary:
        lines.append(filter_summary)
    if batch_id:
        lines.append(f"추천 기록 ID: `{batch_id}`")
    lines.append("")

    if not results:
        lines.extend(
            [
                "현재 조건에서는 검증 기준을 모두 통과한 종목을 찾지 못했습니다.",
                "섹터를 전체로 바꾸거나 하위 기준을 균형형으로 낮춰 다시 실행해보세요.",
                "",
                "※ 이 결과는 투자자문이 아니라 데이터 기반 후보 선별입니다.",
            ]
        )
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        price = _format_price(result.metrics.get("current_price"))
        market_cap = _format_metric_usd(result.metrics.get("market_cap"))
        dollar_volume = _format_metric_usd(result.metrics.get("avg_dollar_volume_50"))
        technical_passed = result.metrics.get("technical_checks_passed")
        sector = result.metrics.get("sector") or "N/A"
        lines.extend(
            [
                f"{index}. **{result.ticker}** | {result.name}",
                f"   등급 {result.grade} / {result.score}점 / 현재가 {price} / 섹터 {sector}",
                f"   기술 조건 통과 {technical_passed}/6, 시가총액 {market_cap}, 50일 평균 거래대금 {dollar_volume}",
                f"   {result.summary}",
            ]
        )

    lines.extend(
        [
            "",
            "추천 당시 가격과 점수는 사후 검증을 위해 로컬 기록으로 저장됩니다.",
            "나중에 `/미너비니 사후검증`으로 추천 결과를 평가할 수 있습니다.",
            "※ 이 결과는 투자자문이 아니라 데이터 기반 후보 선별입니다.",
        ]
    )
    return _trim("\n".join(lines), "후보")


def build_validation_report(validations: list[ValidationResult]) -> str:
    passed = [item for item in validations if item.passed]
    failed = [item for item in validations if not item.passed]

    lines = [
        "**미너비니 후보군 검증 결과**",
        f"전체 {len(validations)}개 중 검증 통과 {len(passed)}개, 보류 {len(failed)}개",
        "",
    ]

    for validation in validations[:15]:
        status = "통과" if validation.passed else "보류"
        failed_reasons = [item.label for item in validation.items if not item.passed]
        reason_text = "모든 기준 통과" if not failed_reasons else ", ".join(failed_reasons)
        lines.append(f"- **{validation.ticker}**: {status} ({reason_text})")

    if len(validations) > 15:
        lines.append(f"- 외 {len(validations) - 15}개 생략")

    lines.extend(["", "검증 기준은 데이터 충분성, 최소 점수, 핵심 기술 조건, 시가총액, 거래대금, 최소 주가입니다."])
    return _trim("\n".join(lines), "검증 결과")


def build_single_validation_report(result: AnalysisResult, validation: ValidationResult) -> str:
    lines = [
        f"**{result.ticker} 검증 결과: {'통과' if validation.passed else '보류'}**",
        f"점수 {result.score}점 / 등급 {result.grade}",
        "",
    ]
    for item in validation.items:
        status = "통과" if item.passed else "미통과"
        lines.append(f"- {status}: {item.label} ({item.detail})")
    lines.extend(["", "※ 검증 통과는 매수 추천이 아니라 후보군에 올릴 수 있다는 뜻입니다."])
    return "\n".join(lines)


def build_performance_report(evaluations: list[RecommendationEvaluation]) -> str:
    lines = ["**미너비니 추천 사후 검증**", ""]

    if not evaluations:
        lines.extend(
            [
                "아직 저장된 추천 기록이 없습니다.",
                "`/미너비니 종목추천`을 먼저 실행하면 추천 당시 가격과 점수가 기록됩니다.",
            ]
        )
        return "\n".join(lines)

    success = sum(1 for item in evaluations if item.verdict == "성공")
    failed = sum(1 for item in evaluations if item.verdict == "실패")
    watch = sum(1 for item in evaluations if item.verdict == "관찰")
    lines.append(f"평가 대상 {len(evaluations)}개 / 성공 {success}개 / 관찰 {watch}개 / 실패 {failed}개")
    lines.append("")

    for item in evaluations[:15]:
        record = item.record
        current_price = _format_price(item.current_price)
        return_text = "N/A" if item.return_pct is None else f"{item.return_pct:+.1%}"
        lines.extend(
            [
                f"- **{record.ticker}**: {item.verdict} ({return_text}, {item.days_elapsed}일 경과)",
                f"  추천가 ${record.price:.2f} -> 현재가 {current_price} / 추천 당시 {record.score}점 {record.grade}",
            ]
        )

    if len(evaluations) > 15:
        lines.append(f"- 외 {len(evaluations) - 15}개 생략")

    lines.extend(
        [
            "",
            "판정 기준은 기본적으로 +10% 이상 성공, -8% 이하 실패, 그 사이는 관찰입니다.",
            "※ 사후 검증은 추천 로직 개선을 위한 성과 기록이며 투자자문이 아닙니다.",
        ]
    )
    return _trim("\n".join(lines), "결과")


def _trim(report: str, label: str) -> str:
    if len(report) <= 1900:
        return report
    return report[:1850] + f"\n\n※ {label}가 길어 일부 내용이 생략되었습니다."
