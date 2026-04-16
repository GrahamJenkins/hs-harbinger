from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from bot.config import Config


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        self.bot = bot
        self.config = config

    @app_commands.command(name="setup", description="Set up RS level roles and post welcome message.")
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

        reminders_cog = self.bot.cogs.get("RemindersCog")
        if reminders_cog is not None:
            await reminders_cog._post_cta(interaction.channel)

        parts = []
        if created:
            parts.append(f"Created roles: {', '.join(created)}.")
        if skipped:
            parts.append(f"Skipped existing: {', '.join(skipped)}.")
        if not created and not skipped:
            parts.append("No roles to create.")
        parts.append("Welcome message posted.")
        await interaction.followup.send(" ".join(parts), ephemeral=True)

    @app_commands.command(name="uninstall", description="Remove RS level roles.")
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

        parts = []
        if deleted:
            parts.append(f"Deleted roles: {', '.join(deleted)}.")
        if not_found:
            parts.append(f"Roles not found: {', '.join(not_found)}.")
        if not deleted and not not_found:
            parts.append("No roles found to delete.")

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
