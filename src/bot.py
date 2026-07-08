from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands

from .analysis import analyze_ticker, recommend_minervini_candidates
from .charting import create_price_chart
from .config import Settings, load_settings
from .filters import SECTOR_LABELS, STYLE_LABELS, describe_filters
from .models import RecommendationFilters
from .performance import evaluate_recommendations, record_recommendations
from .reporting import (
    build_performance_report,
    build_recommendation_report,
    build_report,
    build_single_validation_report,
    build_validation_report,
)
from .validation import validate_candidate

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
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

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        logger.exception("Unhandled Discord client error in %s", event_method)


class MinerviniFilterView(discord.ui.View):
    def __init__(
        self,
        settings: Settings,
        owner_id: int,
        limit: int,
        min_score: int,
        timeout: float = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        self.settings = settings
        self.owner_id = owner_id
        self.filters = RecommendationFilters(limit=limit, min_score=min_score)
        self.add_item(SectorSelect(self))
        self.add_item(StyleSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("이 필터는 명령어를 실행한 사용자만 조작할 수 있습니다.", ephemeral=True)
        return False

    def panel_text(self) -> str:
        return "\n".join(
            [
                "**미너비니 종목 추천 필터**",
                "상위 분류에서 섹터를 고르고, 하위 기준에서 세부 스타일을 고른 뒤 `추천 보기`를 누르세요.",
                "",
                describe_filters(self.filters),
                "",
                "**하위 기준 설명**",
                "- 균형형: 기본 미너비니 검증 기준",
                "- 공격형: 75점 이상 강한 모멘텀",
                "- 보수형: 시가총액 50억 달러, 거래대금 5천만 달러 이상",
                "- 52주 고점 근접: 현재가가 52주 고점의 85% 이상",
                "- 거래량 증가: 최근 거래량이 50일 평균보다 10% 이상 많음",
                "- 재무 품질: 매출 성장과 10% 이상 영업이익률. 이 기준은 정밀 조회라 더 오래 걸릴 수 있습니다.",
            ]
        )

    def refresh_select_defaults(self) -> None:
        for item in self.children:
            if isinstance(item, SectorSelect):
                for option in item.options:
                    option.default = option.value == self.filters.sector
            if isinstance(item, StyleSelect):
                for option in item.options:
                    option.default = option.value == self.filters.style

    async def update_panel(self, interaction: discord.Interaction) -> None:
        self.refresh_select_defaults()
        await interaction.response.edit_message(content=self.panel_text(), view=self)

    @discord.ui.button(label="추천 보기", style=discord.ButtonStyle.primary, row=2)
    async def run_recommendation(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        try:
            results = await asyncio.to_thread(
                recommend_minervini_candidates,
                self.settings.default_tickers,
                self.settings,
                self.filters.limit,
                self.filters.min_score,
                self.filters,
            )
            batch_id = await asyncio.to_thread(record_recommendations, results, self.filters.min_score)
            await interaction.followup.send(
                build_recommendation_report(
                    results,
                    scanned_count=len(self.settings.default_tickers),
                    min_score=self.filters.min_score,
                    batch_id=batch_id,
                    filter_summary=describe_filters(self.filters),
                )
            )
        except Exception as exc:
            logger.exception("Filtered recommendation failed")
            await interaction.followup.send(f"후보 선별 중 오류가 발생했습니다: `{exc}`")

    @discord.ui.button(label="초기화", style=discord.ButtonStyle.secondary, row=2)
    async def reset_filters(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.filters = RecommendationFilters(limit=self.filters.limit, min_score=self.filters.min_score)
        await self.update_panel(interaction)

    @discord.ui.button(label="닫기", style=discord.ButtonStyle.danger, row=2)
    async def close_panel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="미너비니 추천 필터를 닫았습니다.", view=self)


class SectorSelect(discord.ui.Select):
    def __init__(self, view: MinerviniFilterView) -> None:
        self.parent_view = view
        options = [
            discord.SelectOption(label=label, value=value, default=value == view.filters.sector)
            for value, label in SECTOR_LABELS.items()
        ]
        super().__init__(
            placeholder="상위 분류: 섹터 선택",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.filters = RecommendationFilters(
            sector=self.values[0],
            style=self.parent_view.filters.style,
            min_score=self.parent_view.filters.min_score,
            limit=self.parent_view.filters.limit,
        )
        await self.parent_view.update_panel(interaction)


class StyleSelect(discord.ui.Select):
    def __init__(self, view: MinerviniFilterView) -> None:
        self.parent_view = view
        options = [
            discord.SelectOption(label=label, value=value, default=value == view.filters.style)
            for value, label in STYLE_LABELS.items()
        ]
        super().__init__(
            placeholder="하위 기준: 세부 필터 선택",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.filters = RecommendationFilters(
            sector=self.parent_view.filters.sector,
            style=self.values[0],
            min_score=self.parent_view.filters.min_score,
            limit=self.parent_view.filters.limit,
        )
        await self.parent_view.update_panel(interaction)


settings = load_settings()
bot = HoneyFinderBot(settings)


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)


@minervini_group.command(name="종목추천", description="섹터와 세부 기준을 골라 미너비니 후보를 추천합니다.")
@app_commands.describe(
    limit="표시할 후보 개수입니다. 기본값은 5개입니다.",
    min_score="후보로 인정할 최소 점수입니다. 기본값은 85점입니다.",
)
@app_commands.rename(limit="개수", min_score="최소점수")
async def recommend(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 10] = 5,
    min_score: app_commands.Range[int, 0, 100] = 85,
) -> None:
    await interaction.response.defer(thinking=True)
    view = MinerviniFilterView(
        settings=bot.settings,
        owner_id=interaction.user.id,
        limit=limit,
        min_score=min_score,
    )
    await interaction.followup.send(view.panel_text(), view=view)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    logger.exception("Application command failed", exc_info=error)
    message = f"명령어 처리 중 오류가 발생했습니다: `{error}`"
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


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
