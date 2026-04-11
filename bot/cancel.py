from __future__ import annotations

import asyncio

import discord
from discord.ext import commands
from discord import app_commands

from bot.config import Config
from bot.runs import RunStore
from bot.embeds import CancelSelectView


class CancelCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, run_store: RunStore) -> None:
        self.bot = bot
        self.config = config
        self.run_store = run_store

    @app_commands.command(name="rs_cancel", description="Cancel a Red Star run you organized")
    async def rs_cancel(self, interaction: discord.Interaction) -> None:
        runs = self.run_store.get_by_organizer(interaction.user.id)

        if not runs:
            await interaction.response.send_message(
                "You don't have any active runs to cancel.", ephemeral=True
            )
            return

        if len(runs) == 1:
            run = runs[0]
            prefix = "DRS" if run.dark else "RS"
            label = f"{prefix}{run.level}"

            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

            class ConfirmView(discord.ui.View):
                def __init__(self) -> None:
                    super().__init__(timeout=60)

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
                async def yes(self, intr: discord.Interaction, button: discord.ui.Button) -> None:
                    if not future.done():
                        future.set_result(True)
                    self.stop()
                    await intr.response.defer()

                @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
                async def no(self, intr: discord.Interaction, button: discord.ui.Button) -> None:
                    if not future.done():
                        future.set_result(False)
                    self.stop()
                    await intr.response.defer()

            view = ConfirmView()
            await interaction.response.send_message(
                f"Cancel **{label}** at <t:{int(run.start_time)}:f>?",
                view=view,
                ephemeral=True,
            )

            try:
                confirmed = await asyncio.wait_for(future, timeout=60)
            except asyncio.TimeoutError:
                confirmed = False

            if not confirmed:
                await interaction.edit_original_response(content="Cancelled.", view=None)
                return

            await self._do_cancel(interaction, run.id)

        else:
            future2: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()

            async def select_callback(intr: discord.Interaction, run_id: str | None) -> None:
                if not future2.done():
                    future2.set_result(run_id)
                await intr.response.defer()

            view = CancelSelectView(runs, select_callback)
            await interaction.response.send_message(
                "Which run would you like to cancel?", view=view, ephemeral=True
            )

            try:
                chosen_id = await asyncio.wait_for(future2, timeout=60)
            except asyncio.TimeoutError:
                chosen_id = None

            if chosen_id is None:
                await interaction.edit_original_response(content="No run cancelled.", view=None)
                return

            await self._do_cancel(interaction, chosen_id)

    async def _do_cancel(self, interaction: discord.Interaction, run_id: str) -> None:
        run = self.run_store.get(run_id)
        if run is None:
            await interaction.edit_original_response(
                content="That run no longer exists.", view=None
            )
            return

        run.cancelled = True
        organizer = interaction.user.display_name

        if run.message_id is not None:
            try:
                channel = self.bot.get_channel(self.config.channel_id)
                if channel:
                    message = await channel.fetch_message(run.message_id)
                    prefix = "DRS" if run.dark else "RS"
                    embed = discord.Embed(
                        title=f"❌ {prefix}{run.level} — Run cancelled",
                        description=f"Cancelled by {organizer}",
                        color=0x808080,
                    )
                    await message.edit(embed=embed, view=None)
            except Exception:
                pass

        self.run_store.remove(run_id)
        await interaction.edit_original_response(content="Run cancelled.", view=None)
