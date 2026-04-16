from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

import discord
from discord.ext import commands
from discord import app_commands

from bot.config import Config
from bot.runs import RunStore
from bot.embeds import (
    build_run_text,
    build_summary_text,
    RunView,
    WizardLevelView,
    WizardTimeView,
    WizardSummaryView,
)

_TIME_HM = re.compile(r"^(\d+)h(?:(\d+)m)?$")
_TIME_M = re.compile(r"^(\d+)m$")
_LEVEL = re.compile(r"^(d)?(\d{1,2})(d)?$", re.IGNORECASE)


@dataclass
class ParsedArgs:
    level: int | None
    dark: bool | None
    minutes: int | None


def parse_rs_args(args_str: str, config: Config) -> ParsedArgs:
    level: int | None = None
    dark: bool | None = None
    minutes: int | None = None

    if not args_str:
        return ParsedArgs(level=None, dark=None, minutes=None)

    for token in args_str.strip().split():
        if token.lower() == "now":
            minutes = 0
            continue

        m = _LEVEL.match(token)
        if m:
            n = int(m.group(2))
            if config.min_level <= n <= config.max_level:
                level = n
                dark = bool(m.group(1) or m.group(3))
            continue

        m = _TIME_HM.match(token)
        if m:
            hours = int(m.group(1))
            mins = int(m.group(2)) if m.group(2) else 0
            minutes = hours * 60 + mins
            continue

        m = _TIME_M.match(token)
        if m:
            minutes = int(m.group(1))
            continue

    if dark is True and level is not None and level < config.dark_min_level:
        level = None
        dark = None

    return ParsedArgs(level=level, dark=dark, minutes=minutes)


class WizardCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, run_store: RunStore) -> None:
        self.bot = bot
        self.config = config
        self.run_store = run_store
        self._wizards: dict[int, dict] = {}

    @app_commands.command(name="rs", description="Schedule a Red Star run")
    @app_commands.describe(args="Optional: level, 'd' for dark, time (e.g. '8d 30m')")
    async def rs(self, interaction: discord.Interaction, args: str = "") -> None:
        await self.start_wizard(interaction, args)

    async def start_wizard(self, interaction: discord.Interaction, args: str = "") -> None:
        parsed = parse_rs_args(args, self.config)
        user_id = interaction.user.id

        self._wizards[user_id] = {
            "level": parsed.level,
            "dark": parsed.dark,
            "minutes": parsed.minutes,
        }

        try:
            await interaction.response.send_message(
                "Starting wizard...", ephemeral=True
            )
        except discord.NotFound:
            self._wizards.pop(user_id, None)
            return

        try:
            await self._run_wizard(interaction)
        except asyncio.TimeoutError:
            self._wizards.pop(user_id, None)
            await interaction.edit_original_response(
                content="Wizard timed out. Run `/rs` again to start over.",
                view=None,
                embed=None,
            )
        except Exception:
            self._wizards.pop(user_id, None)
            raise

    async def _run_wizard(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        config = self.config
        state = self._wizards[user_id]

        while True:
            # --- Level step ---
            if state["level"] is None:
                all_levels = list(range(config.min_level, config.max_level + 1))

                level_future: asyncio.Future[tuple[discord.Interaction, int, bool]] = (
                    interaction.client.loop.create_future()
                )

                async def level_callback(
                    btn_interaction: discord.Interaction,
                    chosen_level: int,
                    chosen_dark: bool,
                    _fut: asyncio.Future = level_future,
                ) -> None:
                    if not _fut.done():
                        _fut.set_result((btn_interaction, chosen_level, chosen_dark))

                view = WizardLevelView(all_levels, config.dark_min_level, level_callback)
                await interaction.edit_original_response(
                    content="Select your Red Star run:",
                    view=view,
                    embed=None,
                )

                btn_interaction, chosen_level, chosen_dark = await asyncio.wait_for(
                    level_future, timeout=120
                )
                state["level"] = chosen_level
                state["dark"] = chosen_dark
                await btn_interaction.response.defer()

            level: int = state["level"]
            dark: bool = state["dark"]

            # --- Time step ---
            if state["minutes"] is None:
                time_future: asyncio.Future[
                    tuple[discord.Interaction, int]
                ] = interaction.client.loop.create_future()

                async def time_callback(
                    btn_interaction: discord.Interaction,
                    chosen_minutes: int,
                    _fut: asyncio.Future = time_future,
                ) -> None:
                    if not _fut.done():
                        _fut.set_result((btn_interaction, chosen_minutes))

                view = WizardTimeView(time_callback)
                await interaction.edit_original_response(
                    content="When does the run start?",
                    view=view,
                    embed=None,
                )

                btn_interaction, chosen_minutes = await asyncio.wait_for(
                    time_future, timeout=120
                )

                min_m = config.min_lead_minutes
                max_m = config.max_lead_hours * 60
                if chosen_minutes != 0 and (chosen_minutes < min_m or chosen_minutes > max_m):
                    await btn_interaction.response.send_message(
                        f"Time must be between {min_m} minutes and "
                        f"{config.max_lead_hours} hours. Use `/rs` to try again.",
                        ephemeral=True,
                    )
                    self._wizards.pop(user_id, None)
                    return

                state["minutes"] = chosen_minutes
                await btn_interaction.response.defer()

            minutes: int = state["minutes"]

            # --- Summary step ---
            preview_time = time.time() + minutes * 60

            summary_future: asyncio.Future[tuple[discord.Interaction, str]] = (
                interaction.client.loop.create_future()
            )

            async def summary_callback(
                btn_interaction: discord.Interaction,
                action: str,
                _fut: asyncio.Future = summary_future,
            ) -> None:
                if not _fut.done():
                    _fut.set_result((btn_interaction, action))

            summary = build_summary_text(level, dark, minutes, preview_time, config)
            view = WizardSummaryView(summary_callback)
            await interaction.edit_original_response(
                content=summary,
                view=view,
            )

            btn_interaction, action = await asyncio.wait_for(summary_future, timeout=120)

            if action == "confirm":
                start_time = time.time() + minutes * 60
                await btn_interaction.response.defer()
                await self._create_run(interaction, btn_interaction, level, dark, minutes, start_time)
                self._wizards.pop(user_id, None)
                return

            elif action == "edit_level":
                state["level"] = None
                state["dark"] = None
                await btn_interaction.response.defer()
                continue

            elif action == "edit_time":
                state["minutes"] = None
                await btn_interaction.response.defer()
                continue

            elif action == "cancel":
                await btn_interaction.response.edit_message(
                    content="Run cancelled.", embed=None, view=None
                )
                self._wizards.pop(user_id, None)
                return

    async def _create_run(
        self,
        interaction: discord.Interaction,
        btn_interaction: discord.Interaction,
        level: int,
        dark: bool,
        minutes: int,
        start_time: float,
    ) -> None:
        config = self.config
        user = interaction.user

        run = self.run_store.create(
            level=level,
            dark=dark,
            organizer_id=user.id,
            organizer_name=user.display_name,
            start_time=start_time,
            max_players=config.dark_max_players if dark else config.max_players,
            channel_id=interaction.channel.id,
        )

        text = build_run_text(run, config)
        run_view = RunView(self.run_store, config, run.id)

        guild = interaction.guild
        role_name = f"{config.role_prefix}{level}"
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            text = f"{role.mention}\n{text}"

        reminders_cog = self.bot.cogs.get("RemindersCog")
        if reminders_cog is not None:
            await reminders_cog._delete_cta()

        channel = interaction.channel
        message = await channel.send(content=text, view=run_view)
        run.message_id = message.id

        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass
