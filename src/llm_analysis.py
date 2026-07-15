from __future__ import annotations

import json
import re
from typing import Any

from .config import Settings
from .models import AnalysisResult


class LLMConfigurationError(RuntimeError):
    """Raised when the optional LLM feature has not been configured."""


def _snapshot(result: AnalysisResult) -> dict[str, Any]:
    metric_keys = (
        "current_price",
        "ma50",
        "ma150",
        "ma200",
        "week52_high",
        "week52_low",
        "price_to_52w_high",
        "recent_volume_ratio",
        "market_cap",
        "avg_dollar_volume_50",
        "revenue_growth",
        "operating_margin",
        "debt_to_assets",
        "trailing_pe",
        "forward_pe",
        "sector",
        "industry",
    )
    return {
        "ticker": result.ticker,
        "company_name": result.name,
        "quant_score": result.score,
        "quant_grade": result.grade,
        "quant_summary": result.summary,
        "metrics": {key: result.metrics.get(key) for key in metric_keys},
        "checks": [
            {
                "label": check.label,
                "passed": check.passed,
                "detail": check.detail,
            }
            for check in result.checks
        ],
        "positives": result.positives,
        "cautions": result.cautions,
    }


def _trim_discord(text: str, limit: int = 1750) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 28].rstrip() + "\n\n※ 긴 분석은 일부 생략됐습니다."


def _normalize_section_headings(text: str) -> str:
    headings = {
        "한줄 판단": "## 한줄 판단",
        "추세 근거": "## 추세 근거",
        "반전·무효화 신호": "## 반전·무효화 신호",
        "리스크": "## 리스크",
    }
    normalized: list[str] = []
    for line in text.splitlines():
        candidate = re.sub(r"^\s*(?:#{1,3}\s*)?(?:[1-4](?:️⃣|[.)])?\s*)?", "", line)
        candidate = candidate.strip().strip("*").strip()
        matched = next(
            (heading for label, heading in headings.items() if candidate == label or candidate.startswith(f"{label} (")),
            None,
        )
        normalized.append(matched or line)
    return "\n".join(normalized)


def generate_trend_analysis(
    result: AnalysisResult,
    settings: Settings,
    client: Any | None = None,
) -> str:
    """Explain the existing quantitative snapshot without inventing new market data."""
    if result.errors:
        raise ValueError("가격 데이터가 부족해 LLM 추세 분석을 만들 수 없습니다.")
    if not settings.groq_api_key and client is None:
        raise LLMConfigurationError(
            ".env에 GROQ_API_KEY를 설정해야 추세분석 기능을 사용할 수 있습니다."
        )

    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMConfigurationError(
                "Groq 호환 클라이언트 패키지가 없습니다. `pip install -r requirements.txt`를 실행하세요."
            ) from exc
        groq_client = OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    else:
        groq_client = client
    response = groq_client.responses.create(
        model=settings.groq_model,
        instructions=(
            "당신은 미국 주식의 기술적 추세를 설명하는 분석가입니다. "
            "제공된 정량 스냅샷만 근거로 사용하고, 최신 뉴스·실적 발표·거시환경·미래 가격을 "
            "알고 있다고 주장하지 마세요. 매수·매도 지시나 목표가를 제시하지 마세요. "
            "지표가 없으면 없다고 밝히고, 정량 점수를 그대로 반복하기보다 지표 사이의 관계를 설명하세요. "
            "한국어 Discord Markdown으로 작성하고 다음 형식을 정확히 지키세요:\n"
            "## 한줄 판단\n한 문단\n\n"
            "## 추세 근거\n- 근거 목록\n\n"
            "## 반전·무효화 신호\n- 확인할 신호 목록\n\n"
            "## 리스크\n### 주요 위험\n- 중요도 순 목록\n"
            "제목 앞에 숫자나 숫자 이모지를 붙이지 말고, 각 목록은 짧은 문장으로 작성하세요. "
            "전체 1,300자 이내로 답하세요."
        ),
        input=(
            "다음은 Honey-Finder가 방금 계산한 종목 스냅샷입니다. 이 데이터의 시점 이후 정보는 "
            "추정하지 말고 추세를 해석하세요.\n\n"
            + json.dumps(_snapshot(result), ensure_ascii=False, separators=(",", ":"))
        ),
        max_output_tokens=900,
    )
    body = _trim_discord(_normalize_section_headings(response.output_text))
    return "\n".join(
        [
            f"# {result.ticker} | LLM 추세 분석",
            f"### 분석 모델\n`{settings.groq_model}` (Groq)",
            "",
            body,
            "",
            "### 안내",
            "입력된 가격·거래량·재무 보조 지표의 해석이며 투자자문이나 미래 예측이 아닙니다.",
        ]
    )
