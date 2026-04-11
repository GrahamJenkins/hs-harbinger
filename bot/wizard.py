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
    build_run_embed,
    build_summary_embed,
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


def _parse_time_str(s: str) -> int | None:
    m = _TIME_HM.match(s)
    if m:
        hours = int(m.group(1))
        mins = int(m.group(2)) if m.group(2) else 0
        return hours * 60 + mins
    m = _TIME_M.match(s)
    if m:
        return int(m.group(1))
    return None


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

        await interaction.response.send_message(
            "Setting up your Red Star run...", ephemeral=True
        )

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
                member = interaction.guild.get_member(user_id)
                if member is None:
                    try:
                        member = await interaction.guild.fetch_member(user_id)
                    except discord.NotFound:
                        member = None

                user_levels = []
                if member is not None:
                    for role in member.roles:
                        if role.name.startswith(config.role_prefix):
                            suffix = role.name[len(config.role_prefix):]
                            if suffix.isdigit():
                                n = int(suffix)
                                if config.min_level <= n <= config.max_level:
                                    user_levels.append(n)
                user_levels.sort()

                if not user_levels:
                    await interaction.edit_original_response(
                        content=(
                            "You need to opt in to at least one RS level first. "
                            "See the pinned message in this channel."
                        ),
                        view=None,
                        embed=None,
                    )
                    self._wizards.pop(user_id, None)
                    return

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

                view = WizardLevelView(user_levels, config.dark_min_level, level_callback)
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
                while True:
                    time_future: asyncio.Future[
                        tuple[discord.Interaction | None, int]
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
                        content=(
                            "When does the run start? Pick a preset or type a time "
                            "like `45m` or `2h30m` in this channel."
                        ),
                        view=view,
                        embed=None,
                    )

                    def message_check(msg: discord.Message) -> bool:
                        return (
                            msg.author.id == user_id
                            and msg.channel.id == interaction.channel_id
                        )

                    button_task = asyncio.ensure_future(
                        asyncio.wait_for(time_future, timeout=120)
                    )
                    message_task = asyncio.ensure_future(
                        asyncio.wait_for(
                            self.bot.wait_for("message", check=message_check),
                            timeout=120,
                        )
                    )

                    done, pending = await asyncio.wait(
                        [button_task, message_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()

                    chosen_btn_interaction: discord.Interaction | None = None
                    chosen_minutes: int | None = None

                    completed = done.pop()
                    if completed.exception():
                        raise asyncio.TimeoutError()

                    result = completed.result()

                    if completed is button_task:
                        chosen_btn_interaction, chosen_minutes = result
                    else:
                        msg: discord.Message = result
                        try:
                            await msg.delete()
                        except discord.HTTPException:
                            pass
                        parsed_time = _parse_time_str(msg.content.strip())
                        if parsed_time is None:
                            await interaction.edit_original_response(
                                content=(
                                    "Couldn't parse that time. "
                                    "Try something like `30m` or `1h15m`. "
                                    "When does the run start?"
                                ),
                                view=view,
                                embed=None,
                            )
                            time_future.cancel()
                            continue
                        chosen_minutes = parsed_time

                    if chosen_minutes is not None:
                        min_m = config.min_lead_minutes
                        max_m = config.max_lead_hours * 60
                        if chosen_minutes != 0 and (chosen_minutes < min_m or chosen_minutes > max_m):
                            msg_text = (
                                f"Time must be between {min_m} minutes and "
                                f"{config.max_lead_hours} hours. Try again."
                            )
                            if chosen_btn_interaction is not None:
                                await chosen_btn_interaction.response.send_message(
                                    msg_text, ephemeral=True
                                )
                            else:
                                await interaction.edit_original_response(
                                    content=msg_text,
                                    view=None,
                                    embed=None,
                                )
                            continue

                        state["minutes"] = chosen_minutes
                        if chosen_btn_interaction is not None:
                            await chosen_btn_interaction.response.defer()
                        break

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

            embed = build_summary_embed(level, dark, minutes, preview_time, config)
            view = WizardSummaryView(summary_callback)
            await interaction.edit_original_response(
                content="Here's your run summary:",
                embed=embed,
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
        )

        embed = build_run_embed(run, config)
        run_view = RunView(self.run_store, config, run.id)

        ping_parts = []
        guild = interaction.guild
        for lvl in range(level, config.max_level + 1):
            role_name = f"{config.role_prefix}{lvl}"
            role = discord.utils.get(guild.roles, name=role_name)
            if role is not None:
                ping_parts.append(role.mention)

        ping_text = " ".join(ping_parts)
        content = ping_text if ping_text else None

        channel = interaction.channel
        message = await channel.send(content=content, embed=embed, view=run_view)
        run.message_id = message.id

        await interaction.delete_original_response()
