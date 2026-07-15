from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _get_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int | None
    default_tickers: list[str]
    min_market_cap_usd: float
    min_avg_dollar_volume_usd: float
    min_price_usd: float
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    tickers = [
        ticker.strip().upper()
        for ticker in os.getenv(
            "DEFAULT_TICKERS",
            "NVDA,AAPL,MSFT,AMZN,META,GOOGL,AVGO,TSLA",
        ).split(",")
        if ticker.strip()
    ]

    return Settings(
        discord_bot_token=token,
        discord_guild_id=_get_int("DISCORD_GUILD_ID"),
        default_tickers=tickers,
        min_market_cap_usd=_get_float("MIN_MARKET_CAP_USD", 2_000_000_000),
        min_avg_dollar_volume_usd=_get_float(
            "MIN_AVG_DOLLAR_VOLUME_USD",
            20_000_000,
        ),
        min_price_usd=_get_float("MIN_PRICE_USD", 10),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
        or "openai/gpt-oss-120b",
    )
