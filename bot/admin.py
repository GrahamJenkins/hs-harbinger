from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord import app_commands

from bot.config import Config

if TYPE_CHECKING:
    from bot.roles import RolesCog


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, roles_cog: RolesCog) -> None:
        self.bot = bot
        self.config = config
        self.roles_cog = roles_cog

    @app_commands.command(name="setup", description="Set up roles and role message.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        created = []
        skipped = []

        for level in range(self.config.min_level, self.config.max_level + 1):
            name = f"{self.config.role_prefix}{level}"
            existing = discord.utils.get(guild.roles, name=name)
            if existing is not None:
                skipped.append(name)
            else:
                try:
                    await guild.create_role(name=name, mentionable=True)
                    created.append(name)
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"Missing permissions to create role {name}.", ephemeral=True
                    )
                    return

        message_exists = False
        if self.roles_cog.role_message_id is not None:
            channel = self.bot.get_channel(self.config.channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.config.channel_id)
                except (discord.NotFound, discord.Forbidden):
                    channel = None

            if channel is not None:
                try:
                    msg = await channel.fetch_message(self.roles_cog.role_message_id)
                    await self.roles_cog._ensure_reactions(msg)
                    message_exists = True
                except (discord.NotFound, discord.Forbidden):
                    self.roles_cog.role_message_id = None

        if not message_exists:
            try:
                await self.roles_cog._setup_role_message()
            except (discord.NotFound, discord.Forbidden) as e:
                await interaction.followup.send(
                    f"Failed to post role message: {e}", ephemeral=True
                )
                return

        parts = []
        if created:
            parts.append(f"Created roles: {', '.join(created)}.")
        if skipped:
            parts.append(f"Skipped existing: {', '.join(skipped)}.")
        if not created and not skipped:
            parts.append("No roles to create.")

        parts.append(f"Role message posted in <#{self.config.channel_id}>.")
        await interaction.followup.send(" ".join(parts), ephemeral=True)

    @app_commands.command(name="uninstall", description="Remove roles and role message.")
    @app_commands.checks.has_permissions(administrator=True)
    async def uninstall(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        deleted = []
        not_found = []

        for level in range(self.config.min_level, self.config.max_level + 1):
            name = f"{self.config.role_prefix}{level}"
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                not_found.append(name)
            else:
                try:
                    await role.delete()
                    deleted.append(name)
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"Missing permissions to delete role {name}.", ephemeral=True
                    )
                    return

        message_removed = False
        if self.roles_cog.role_message_id is not None:
            channel = self.bot.get_channel(self.config.channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.config.channel_id)
                except (discord.NotFound, discord.Forbidden):
                    channel = None

            if channel is not None:
                try:
                    msg = await channel.fetch_message(self.roles_cog.role_message_id)
                    await msg.unpin()
                    await msg.delete()
                    message_removed = True
                except (discord.NotFound, discord.Forbidden):
                    pass

            self.roles_cog.role_message_id = None

        parts = []
        if deleted:
            parts.append(f"Deleted roles: {', '.join(deleted)}.")
        if not_found:
            parts.append(f"Roles not found: {', '.join(not_found)}.")
        if not deleted and not not_found:
            parts.append("No roles found to delete.")

        if message_removed:
            parts.append("Removed role message.")
        else:
            parts.append("No role message found.")

        await interaction.followup.send(" ".join(parts), ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            if interaction.response.is_done():
                await interaction.followup.send(
                    "This command requires administrator permissions.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "This command requires administrator permissions.", ephemeral=True
                )
        else:
            raise error
