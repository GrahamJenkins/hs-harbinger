from __future__ import annotations

import time
import traceback

import discord
from discord.ext import commands, tasks

from bot.config import Config
from bot.runs import RunStore
from bot.embeds import build_run_text
from bot.roles import StartRunView


class RemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, run_store: RunStore) -> None:
        self.bot = bot
        self.config = config
        self.run_store = run_store
        self._reminder_messages: dict[str, discord.Message] = {}
        self._cta_message: discord.Message | None = None

    async def cog_load(self) -> None:
        self._check_reminders.start()

    async def cog_unload(self) -> None:
        self._check_reminders.cancel()

    @tasks.loop(seconds=1)
    async def _check_reminders(self) -> None:
        now = time.time()

        for run in self.run_store.active_runs():
            try:
                channel = self.bot.get_channel(run.channel_id)
                await self._process_run(run, now, channel)
            except Exception:
                traceback.print_exc()

        try:
            await self._process_expired()
        except Exception:
            traceback.print_exc()

    async def _process_run(
        self, run, now: float, channel: discord.abc.Messageable | None
    ) -> None:
        mentions = " ".join(f"<@{uid}>" for uid in run.confirmed)
        name = f"Dark Red Star {run.level}" if run.dark else f"Red Star {run.level}"
        label = f"**{name}**"
        ts = int(run.start_time)

        remaining = run.start_time - now
        for interval in sorted(self.config.reminder_minutes, reverse=True):
            if (
                remaining <= interval * 60
                and remaining > 0
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
            time_since_created = now - run.created_at
            if time_since_created < 30:
                run.reminded.add(0)
            else:
                if channel:
                    await self._delete_previous_reminder(run.id)
                    others = [uid for uid in run.confirmed if uid != run.organizer_id]
                    crew_list = "\n".join(f"<@{uid}>" for uid in others)
                    text = f"🚀 {label} — <@{run.organizer_id}> is scanning, join their star!"
                    if crew_list:
                        text += f"\n{crew_list}"
                    msg = await channel.send(text)
                    self._reminder_messages[run.id] = msg
            run.reminded.add(0)

        if now >= run.start_time and run.message_id and channel and "started" not in run.reminded:
            try:
                message = await channel.fetch_message(run.message_id)
                text = build_run_text(run, self.config, state="active")
                await message.edit(content=text)
            except Exception:
                pass
            run.reminded.add("started")

    async def _process_expired(self) -> None:
        expired = self.run_store.cleanup_expired(grace_minutes=self.config.round_minutes)
        for run in expired:
            await self._delete_previous_reminder(run.id)

            if run.message_id is None:
                continue
            try:
                channel = self.bot.get_channel(run.channel_id)
                if channel is None:
                    continue

                message = await channel.fetch_message(run.message_id)
                text = build_run_text(run, self.config, state="completed")
                await message.edit(content=text, view=None)
            except Exception:
                pass

        if expired:
            last = expired[-1]
            channel = self.bot.get_channel(last.channel_id)
            await self._post_cta(channel)

    async def _post_cta(self, channel: discord.abc.Messageable | None) -> None:
        if channel is None:
            return
        await self._delete_cta()
        try:
            self._cta_message = await channel.send(
                "### Red stars are more fun with friends!\n"
                "Hit **Start a Run** to schedule one, or tap **Manage Notifications** "
                "to pick which levels you want to be pinged for.\n"
                "*Signing up for pings lets your corp mates know when you're playing!*",
                view=StartRunView(),
                silent=True,
            )
        except Exception:
            traceback.print_exc()

    async def _delete_cta(self) -> None:
        if self._cta_message is not None:
            try:
                await self._cta_message.delete()
            except Exception:
                pass
            self._cta_message = None

    async def _delete_previous_reminder(self, run_id: str) -> None:
        msg = self._reminder_messages.pop(run_id, None)
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

    @_check_reminders.error
    async def _on_check_error(self, error: Exception) -> None:
        print(f"[reminders] LOOP ERROR: {type(error).__name__}: {error}", flush=True)
        traceback.print_exc()

    @_check_reminders.before_loop
    async def _before_check(self) -> None:
        await self.bot.wait_until_ready()
