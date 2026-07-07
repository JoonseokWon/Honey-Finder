from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands

from .analysis import analyze_ticker, recommend_minervini_candidates
from .charting import create_price_chart
from .config import Settings, load_settings
from .performance import evaluate_recommendations, record_recommendations
from .reporting import (
    build_performance_report,
    build_recommendation_report,
    build_report,
    build_single_validation_report,
    build_validation_report,
)
from .validation import validate_candidate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("honey-finder")

minervini_group = app_commands.Group(name="미너비니", description="미너비니 조건으로 미국 주식 후보를 선별합니다.")


class HoneyFinderBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.settings = settings
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.tree.add_command(minervini_group)
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %s guild commands", len(synced))
        else:
            synced = await self.tree.sync()
            logger.info("Synced %s global commands", len(synced))


settings = load_settings()
bot = HoneyFinderBot(settings)


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)


@minervini_group.command(name="종목추천", description="관심 종목군에서 검증 기준을 통과한 미너비니 후보를 보여줍니다.")
@app_commands.describe(
    limit="표시할 후보 개수입니다. 기본값은 5개입니다.",
    min_score="후보로 인정할 최소 점수입니다. 기본값은 65점입니다.",
)
@app_commands.rename(limit="개수", min_score="최소점수")
async def recommend(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 10] = 5,
    min_score: app_commands.Range[int, 0, 100] = 65,
) -> None:
    await interaction.response.defer(thinking=True)

    try:
        results = await asyncio.to_thread(
            recommend_minervini_candidates,
            bot.settings.default_tickers,
            bot.settings,
            limit,
            min_score,
        )
        batch_id = await asyncio.to_thread(record_recommendations, results, min_score)
        await interaction.followup.send(
            build_recommendation_report(
                results,
                scanned_count=len(bot.settings.default_tickers),
                min_score=min_score,
                batch_id=batch_id,
            )
        )
    except Exception as exc:
        logger.exception("Recommendation command failed")
        await interaction.followup.send(f"후보 선별 중 오류가 발생했습니다: `{exc}`")


@minervini_group.command(name="진단", description="특정 티커의 미너비니 조건과 재무 보조 지표를 확인합니다.")
@app_commands.describe(ticker="예: NVDA, AAPL, MSFT")
@app_commands.rename(ticker="티커")
async def diagnose(interaction: discord.Interaction, ticker: str) -> None:
    await interaction.response.defer(thinking=True)

    try:
        result = await asyncio.to_thread(analyze_ticker, ticker, bot.settings)
        chart_path = await asyncio.to_thread(create_price_chart, result)
        report = build_report(result)

        if chart_path and Path(chart_path).exists():
            await interaction.followup.send(report, file=discord.File(chart_path))
        else:
            await interaction.followup.send(report)
    except Exception as exc:
        logger.exception("Diagnosis command failed")
        await interaction.followup.send(f"진단 중 오류가 발생했습니다: `{exc}`")


@minervini_group.command(name="검증", description="후보군 전체 또는 특정 티커가 추천 검증 기준을 통과하는지 확인합니다.")
@app_commands.describe(ticker="비워두면 DEFAULT_TICKERS 전체를 검증합니다.", min_score="검증에 사용할 최소 점수입니다.")
@app_commands.rename(ticker="티커", min_score="최소점수")
async def validate(
    interaction: discord.Interaction,
    ticker: str | None = None,
    min_score: app_commands.Range[int, 0, 100] = 65,
) -> None:
    await interaction.response.defer(thinking=True)

    try:
        if ticker:
            result = await asyncio.to_thread(analyze_ticker, ticker, bot.settings)
            validation = validate_candidate(result, bot.settings, min_score=min_score)
            await interaction.followup.send(build_single_validation_report(result, validation))
            return

        validations = []
        for default_ticker in bot.settings.default_tickers:
            result = await asyncio.to_thread(analyze_ticker, default_ticker, bot.settings)
            validations.append(validate_candidate(result, bot.settings, min_score=min_score))
        await interaction.followup.send(build_validation_report(validations))
    except Exception as exc:
        logger.exception("Validation command failed")
        await interaction.followup.send(f"검증 중 오류가 발생했습니다: `{exc}`")


@minervini_group.command(name="사후검증", description="과거 추천 기록이 이후 성과로 이어졌는지 확인합니다.")
@app_commands.describe(
    ticker="비워두면 최근 추천 기록 전체를 평가합니다.",
    target_return="성공으로 볼 목표 수익률입니다. 기본값은 0.10입니다.",
    fail_return="실패로 볼 손실률입니다. 기본값은 -0.08입니다.",
)
@app_commands.rename(ticker="티커", target_return="목표수익률", fail_return="실패수익률")
async def performance_check(
    interaction: discord.Interaction,
    ticker: str | None = None,
    target_return: app_commands.Range[float, 0.0, 1.0] = 0.10,
    fail_return: app_commands.Range[float, -1.0, 0.0] = -0.08,
) -> None:
    await interaction.response.defer(thinking=True)

    try:
        evaluations = await asyncio.to_thread(
            evaluate_recommendations,
            bot.settings,
            ticker,
            target_return,
            fail_return,
        )
        await interaction.followup.send(build_performance_report(evaluations))
    except Exception as exc:
        logger.exception("Performance check command failed")
        await interaction.followup.send(f"사후 검증 중 오류가 발생했습니다: `{exc}`")


def main() -> None:
    if not settings.discord_bot_token:
        raise RuntimeError(".env에 DISCORD_BOT_TOKEN을 설정해야 합니다.")
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
