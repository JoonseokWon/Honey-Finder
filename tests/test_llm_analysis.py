from types import SimpleNamespace
from unittest import TestCase

from src.config import Settings
from src.llm_analysis import (
    LLMConfigurationError,
    _normalize_section_headings,
    generate_trend_analysis,
)
from src.models import AnalysisResult, CheckResult


def _settings(api_key: str = "test-key") -> Settings:
    return Settings(
        discord_bot_token="",
        discord_guild_id=None,
        default_tickers=["NVDA"],
        min_market_cap_usd=2_000_000_000,
        min_avg_dollar_volume_usd=20_000_000,
        min_price_usd=10,
        groq_api_key=api_key,
        groq_model="test-model",
    )


def _result() -> AnalysisResult:
    return AnalysisResult(
        ticker="NVDA",
        name="NVIDIA",
        score=88,
        grade="A",
        summary="기술 조건을 상당수 충족합니다.",
        checks=[CheckResult("현재가가 장기선 위", True, "현재가 120, 200일선 100", 16)],
        positives=["유동성 기준을 충족합니다."],
        cautions=["밸류에이션 부담이 있을 수 있습니다."],
        metrics={"current_price": 120.0, "ma200": 100.0, "recent_volume_ratio": 1.2},
    )


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output_text="**한줄 판단**\n상승 추세가 우세하지만 리스크 확인이 필요합니다.")


class LLMTrendAnalysisTest(TestCase):
    def test_normalizes_numbered_section_labels_to_markdown_headings(self) -> None:
        text = "1️⃣ 한줄 판단\n강한 추세\n4️⃣ 리스크 (중요도 순)\n- 거래량 약화"

        normalized = _normalize_section_headings(text)

        self.assertIn("## 한줄 판단", normalized)
        self.assertIn("## 리스크", normalized)
        self.assertNotIn("1️⃣", normalized)

    def test_uses_snapshot_and_wraps_disclaimer(self) -> None:
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)

        report = generate_trend_analysis(_result(), _settings(), client=client)

        self.assertEqual(responses.kwargs["model"], "test-model")
        self.assertIn('"current_price":120.0', responses.kwargs["input"])
        self.assertIn("# NVDA | LLM 추세 분석", report)
        self.assertIn("### 분석 모델", report)
        self.assertIn("투자자문이나 미래 예측이 아닙니다", report)

    def test_requires_api_key_without_injected_client(self) -> None:
        with self.assertRaises(LLMConfigurationError):
            generate_trend_analysis(_result(), _settings(api_key=""))
