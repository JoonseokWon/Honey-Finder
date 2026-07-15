from unittest import TestCase

from src.models import (
    AnalysisResult,
    CheckResult,
    RecommendationEvaluation,
    RecommendationRecord,
    ValidationItem,
    ValidationResult,
)
from src.reporting import (
    build_performance_report,
    build_recommendation_report,
    build_report,
    build_single_validation_report,
    build_validation_report,
)


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        ticker="NVDA",
        name="NVIDIA",
        score=88,
        grade="A",
        summary="기술 조건을 상당수 충족합니다.",
        checks=[CheckResult("장기 추세", True, "현재가가 200일선 위", 16)],
        positives=["추세가 정배열입니다."],
        cautions=["거래량을 확인해야 합니다."],
        metrics={
            "current_price": 120.0,
            "technical_checks_passed": 5,
            "sector": "Technology",
        },
    )


def _validation() -> ValidationResult:
    return ValidationResult(
        ticker="NVDA",
        passed=True,
        items=[ValidationItem("최소 점수", True, "88점")],
    )


class DiscordReportingFormatTest(TestCase):
    def assert_discord_hierarchy(self, report: str) -> None:
        self.assertIn("# ", report)
        self.assertIn("## ", report)
        self.assertIn("### ", report)
        self.assertIn("- ", report)

    def test_diagnosis_uses_headings_bullets_and_quote(self) -> None:
        report = build_report(_analysis())

        self.assert_discord_hierarchy(report)
        self.assertIn("> 기술 조건을 상당수 충족합니다.", report)

    def test_recommendation_uses_heading_hierarchy(self) -> None:
        report = build_recommendation_report([_analysis()], scanned_count=1)

        self.assert_discord_hierarchy(report)
        self.assertIn("### 1. NVDA | NVIDIA", report)

    def test_validation_reports_use_heading_hierarchy(self) -> None:
        group_report = build_validation_report([_validation()])
        single_report = build_single_validation_report(_analysis(), _validation())

        self.assert_discord_hierarchy(group_report)
        self.assert_discord_hierarchy(single_report)

    def test_performance_uses_heading_hierarchy(self) -> None:
        record = RecommendationRecord(
            batch_id="batch-1",
            recommended_at="2026-07-01T00:00:00+00:00",
            ticker="NVDA",
            name="NVIDIA",
            price=100.0,
            score=88,
            grade="A",
            min_score=65,
            technical_checks_passed=5,
        )
        evaluation = RecommendationEvaluation(
            record=record,
            current_price=110.0,
            return_pct=0.10,
            days_elapsed=15,
            verdict="성공",
            detail="목표 수익률 도달",
        )

        report = build_performance_report([evaluation])

        self.assert_discord_hierarchy(report)
        self.assertIn("### NVDA | 성공", report)
