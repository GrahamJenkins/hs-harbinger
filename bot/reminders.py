from __future__ import annotations

import time

import discord
from discord.ext import commands, tasks

from bot.config import Config
from bot.runs import RunStore
from bot.embeds import build_run_embed


class RemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, run_store: RunStore) -> None:
        self.bot = bot
        self.config = config
        self.run_store = run_store
        self._reminder_messages: dict[str, discord.Message] = {}

    async def cog_load(self) -> None:
        self._check_reminders.start()

    async def cog_unload(self) -> None:
        self._check_reminders.cancel()

    @tasks.loop(seconds=15)
    async def _check_reminders(self) -> None:
        now = time.time()
        channel = self.bot.get_channel(self.config.channel_id)

        for run in self.run_store.active_runs():
            mentions = " ".join(f"<@{uid}>" for uid in run.confirmed)
            prefix = "DRS" if run.dark else "RS"
            label = f"**{prefix}{run.level}**"
            ts = int(run.start_time)

            for interval in sorted(self.config.reminder_minutes, reverse=True):
                if (
                    run.start_time - now <= interval * 60
                    and interval not in run.reminded
                ):
                    if channel:
                        await self._delete_previous_reminder(run.id)
                        msg = await channel.send(
                            f"⏰ {label} starting in **{interval} minute{'s' if interval != 1 else ''}**! {mentions}"
                        )
                        self._reminder_messages[run.id] = msg
                    run.reminded.add(interval)

            if now >= run.start_time and 0 not in run.reminded:
                if channel:
                    await self._delete_previous_reminder(run.id)
                    msg = await channel.send(f"🚀 {label} — GO TIME! {mentions}")
                    self._reminder_messages[run.id] = msg
                run.reminded.add(0)

            if now >= run.start_time and run.message_id and channel and "started" not in run.reminded:
                try:
                    message = await channel.fetch_message(run.message_id)
                    embed = build_run_embed(run, self.config)
                    embed.set_field_at(
                        1,
                        name="Started",
                        value=f"<t:{ts}:t>",
                        inline=False,
                    )
                    await message.edit(embed=embed, view=None)
                except Exception:
                    pass
                run.reminded.add("started")

        expired = self.run_store.cleanup_expired(grace_minutes=5)
        for run in expired:
            await self._delete_previous_reminder(run.id)

            if run.message_id is None:
                continue
            try:
                ch = self.bot.get_channel(self.config.channel_id)
                if ch is None:
                    continue
                message = await ch.fetch_message(run.message_id)
                embed = build_run_embed(run, self.config)
                embed.title = f"✅ Run completed — {embed.title}"
                embed.set_field_at(
                    1,
                    name="Started",
                    value=f"<t:{int(run.start_time)}:t>",
                    inline=False,
                )
                await message.edit(embed=embed, view=None)
            except Exception:
                pass

    async def _delete_previous_reminder(self, run_id: str) -> None:
        msg = self._reminder_messages.pop(run_id, None)
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

    @_check_reminders.before_loop
    async def _before_check(self) -> None:
        await self.bot.wait_until_ready()
