from __future__ import annotations

from typing import Callable, Awaitable

import discord
import discord.ui

from bot.runs import Run, RunStore
from bot.config import Config
from bot.roles import _check_guild


def build_run_text(run: Run, config: Config, state: str = "upcoming") -> str:
    """Build run message text.

    state: "upcoming" (H1), "active" (H2), or "completed" (H3)
    """
    name = f"Dark Red Star {run.level}" if run.dark else f"Red Star {run.level}"
    icon = "\U0001f480" if run.dark else "\u2b50"
    ts = int(run.start_time)

    headers = {"upcoming": "#", "active": "##", "completed": "###"}
    header = headers.get(state, "###")

    lines = [f"{header} {icon} {name}"]
    lines.append(f"**Scanner:** <@{run.organizer_id}>")

    if state == "upcoming":
        lines.append(f"**Scan starts:** <t:{ts}:R> (<t:{ts}:t>)")
        lines.append("*Join the scanner's star when it's time.*")
    else:
        lines.append(f"**Scanned:** <t:{ts}:t>")

    lines.append("")

    confirmed = run.confirmed
    crew_label = f"**Crew ({len(confirmed)}/{run._max_players})**"
    if run.is_full and run.standby:
        crew_label += " \u2014 Full, join as standby"
    lines.append(crew_label)

    if confirmed:
        for i, uid in enumerate(confirmed, start=1):
            name = run.crew_names.get(uid, str(uid))
            lines.append(f"{i}. {name} (<@{uid}>)")
    else:
        lines.append("No crew yet")

    standby = run.standby
    if standby:
        lines.append("")
        lines.append("**Standby**")
        for i, uid in enumerate(standby, start=len(confirmed) + 1):
            name = run.crew_names.get(uid, str(uid))
            lines.append(f"{i}. {name} (<@{uid}>) (standby)")

    return "\n".join(lines)


def build_summary_text(
    level: int, dark: bool, minutes: int, start_time: float, config: Config
) -> str:
    name = f"Dark Red Star {level}" if dark else f"Red Star {level}"
    icon = "\U0001f480" if dark else "\u2b50"
    start = "Now" if minutes == 0 else f"<t:{int(start_time)}:R>"

    lines = [
        f"### {icon} {name} \u2014 Preview",
        f"**Type:** {'Dark' if dark else 'Normal'}",
        f"**Starts:** {start}",
    ]
    return "\n".join(lines)


class RunView(discord.ui.View):
    def __init__(self, run_store: RunStore, config: Config, run_id: str) -> None:
        super().__init__(timeout=None)
        self.run_store = run_store
        self.config = config
        self.run_id = run_id

        join_button = discord.ui.Button(
            label="Join",
            style=discord.ButtonStyle.success,
            custom_id=f"run_join:{run_id}",
        )
        join_button.callback = self._join_callback
        self.add_item(join_button)

        leave_button = discord.ui.Button(
            label="Leave",
            style=discord.ButtonStyle.danger,
            custom_id=f"run_leave:{run_id}",
        )
        leave_button.callback = self._leave_callback
        self.add_item(leave_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return _check_guild(interaction)

    async def _join_callback(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        joined = self.run_store.join(self.run_id, user.id, user.display_name)
        if not joined:
            await interaction.response.send_message(
                "You're already in this run.", ephemeral=True
            )
            return

        run = self.run_store.get(self.run_id)
        if run is None:
            await interaction.response.send_message(
                "This run no longer exists.", ephemeral=True
            )
            return

        text = build_run_text(run, self.config)
        await interaction.response.edit_message(content=text, view=self)

        total = len(run.crew)
        if total == self.config.max_players * 2:
            await interaction.followup.send(
                "This run is packed! Consider starting a second star.",
                ephemeral=True,
            )

    async def _leave_callback(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        left = self.run_store.leave(self.run_id, user.id)
        if not left:
            await interaction.response.send_message(
                "You're not in this run.", ephemeral=True
            )
            return

        run = self.run_store.get(self.run_id)
        if run is None:
            await interaction.response.send_message(
                "This run no longer exists.", ephemeral=True
            )
            return

        if user.id == run.organizer_id and not run.crew:
            self.run_store.remove(self.run_id)
            name = "Dark Red Star" if run.dark else "Red Star"
            await interaction.response.edit_message(
                content=f"### \u274c {name} {run.level} \u2014 Run cancelled\nScanner left with no crew.",
                view=None,
            )
            return

        text = build_run_text(run, self.config)
        await interaction.response.edit_message(content=text, view=self)


class WizardLevelView(discord.ui.View):
    def __init__(
        self,
        levels: list[int],
        dark_min_level: int,
        callback: Callable[[discord.Interaction, int, bool], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=120)
        self._callback = callback

        groups: list[list[tuple[str, int, bool, discord.ButtonStyle]]] = []
        for level in levels:
            group = [(f"RS{level}", level, False, discord.ButtonStyle.primary)]
            if level >= dark_min_level:
                group.append((f"\U0001f480 DRS{level}", level, True, discord.ButtonStyle.danger))
            groups.append(group)

        one_per_row = len(groups) <= 5
        for i, group in enumerate(groups):
            if one_per_row:
                row = i
            else:
                row = i // 2
            if row > 4:
                break
            for label, level, dark, style in group:
                button = discord.ui.Button(
                    label=label,
                    style=style,
                    custom_id=f"wizard_level:{level}{'d' if dark else ''}",
                    row=row,
                )
                button.callback = self._make_handler(level, dark)
                self.add_item(button)

    def _make_handler(
        self, level: int, dark: bool
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def handler(interaction: discord.Interaction) -> None:
            await self._callback(interaction, level, dark)

        return handler


class WizardTimeView(discord.ui.View):
    _PRESETS: list[tuple[str, int]] = [
        ("Now", 0),
        ("5 min", 5),
        ("10 min", 10),
        ("15 min", 15),
        ("20 min", 20),
        ("30 min", 30),
        ("1 hour", 60),
        ("2 hours", 120),
        ("4 hours", 240),
    ]

    def __init__(
        self,
        callback: Callable[[discord.Interaction, int], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=120)
        self._callback = callback
        for label, minutes in self._PRESETS:
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"wizard_time:{minutes}",
            )
            button.callback = self._make_handler(minutes)
            self.add_item(button)

    def _make_handler(
        self, minutes: int
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def handler(interaction: discord.Interaction) -> None:
            await self._callback(interaction, minutes)

        return handler


class WizardSummaryView(discord.ui.View):
    def __init__(
        self,
        callback: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=120)
        self._callback = callback

        confirm_button = discord.ui.Button(
            label="Confirm",
            style=discord.ButtonStyle.success,
            custom_id="wizard_summary:confirm",
        )
        confirm_button.callback = self._make_handler("confirm")
        self.add_item(confirm_button)

        edit_level_button = discord.ui.Button(
            label="Edit Level",
            style=discord.ButtonStyle.secondary,
            custom_id="wizard_summary:edit_level",
        )
        edit_level_button.callback = self._make_handler("edit_level")
        self.add_item(edit_level_button)

        edit_time_button = discord.ui.Button(
            label="Edit Time",
            style=discord.ButtonStyle.secondary,
            custom_id="wizard_summary:edit_time",
        )
        edit_time_button.callback = self._make_handler("edit_time")
        self.add_item(edit_time_button)

        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="wizard_summary:cancel",
        )
        cancel_button.callback = self._make_handler("cancel")
        self.add_item(cancel_button)

    def _make_handler(
        self, action: str
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def handler(interaction: discord.Interaction) -> None:
            await self._callback(interaction, action)

        return handler


class CancelSelectView(discord.ui.View):
    def __init__(
        self,
        runs: list[Run],
        callback: Callable[[discord.Interaction, str | None], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=60)
        self._callback = callback

        for run in runs:
            prefix = "DRS" if run.dark else "RS"
            label = f"{prefix}{run.level} at <t:{int(run.start_time)}:t>"
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.danger,
                custom_id=f"cancel_run:{run.id}",
            )
            button.callback = self._make_run_handler(run.id)
            self.add_item(button)

        nevermind_button = discord.ui.Button(
            label="Never mind",
            style=discord.ButtonStyle.secondary,
            custom_id="cancel_run:nevermind",
        )
        nevermind_button.callback = self._nevermind_handler
        self.add_item(nevermind_button)

    def _make_run_handler(
        self, run_id: str
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def handler(interaction: discord.Interaction) -> None:
            await self._callback(interaction, run_id)

        return handler

    async def _nevermind_handler(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, None)
