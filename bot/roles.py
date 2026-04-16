import discord
from discord.ext import commands

from bot.config import Config


def _check_guild(interaction: discord.Interaction) -> bool:
    config = getattr(interaction.client, "config", None)
    if config is None or config.guild_id is None:
        return True
    return interaction.guild_id == config.guild_id


class StartRunView(discord.ui.View):
    """Persistent view with Start a Run and Manage Notifications buttons."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return _check_guild(interaction)

    @discord.ui.button(
        label="Start a Run (/rs)",
        style=discord.ButtonStyle.success,
        custom_id="start_run",
    )
    async def start_run(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        wizard_cog = interaction.client.cogs.get("WizardCog")
        if wizard_cog is None:
            await interaction.response.send_message(
                "Bot is still starting up, try again in a moment.", ephemeral=True
            )
            return
        await wizard_cog.start_wizard(interaction)

    @discord.ui.button(
        label="Manage Notifications",
        style=discord.ButtonStyle.primary,
        custom_id="manage_notifications",
    )
    async def manage_notifications(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        roles_cog = interaction.client.cogs.get("RolesCog")
        if roles_cog is None:
            await interaction.response.send_message(
                "Bot is still starting up, try again in a moment.", ephemeral=True
            )
            return
        await roles_cog.show_notification_wizard(interaction)


class NotificationToggleView(discord.ui.View):
    def __init__(self, roles_cog: "RolesCog", member: discord.Member) -> None:
        super().__init__(timeout=120)
        self.roles_cog = roles_cog
        config = roles_cog.config
        prefix = config.role_prefix

        subscribed = _get_subscribed_levels(member, prefix)

        levels = list(range(config.min_level, config.max_level + 1))
        for i, level in enumerate(levels):
            is_on = level in subscribed
            button = discord.ui.Button(
                label=f"RS{level} \u2713" if is_on else f"RS{level}",
                style=discord.ButtonStyle.success if is_on else discord.ButtonStyle.secondary,
                custom_id=f"notif_toggle:{level}",
                row=0 if i < 4 else 1,
            )
            button.callback = self._make_handler(level)
            self.add_item(button)

        close_button = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.danger,
            custom_id="notif_close",
            row=2,
        )
        close_button.callback = self._close_handler
        self.add_item(close_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return _check_guild(interaction)

    async def _close_handler(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()

    def _make_handler(self, level: int):
        async def handler(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            member = guild.get_member(interaction.user.id)
            if member is None:
                member = await guild.fetch_member(interaction.user.id)

            try:
                role = await self.roles_cog._get_or_create_role(guild, level)

                if role in member.roles:
                    await member.remove_roles(role)
                else:
                    await member.add_roles(role)
            except discord.Forbidden:
                bot_member = guild.me
                bot_top = bot_member.top_role.position if bot_member else 0
                await interaction.response.defer()
                await interaction.channel.send(
                    "\u26a0\ufe0f Missing permissions or RS roles outrank me. "
                    "Please move my role above the RS roles in **Server Settings > Roles**."
                )
                return
            except discord.HTTPException:
                await interaction.response.send_message(
                    "Something went wrong. Please try again.", ephemeral=True
                )
                return

            member = await guild.fetch_member(interaction.user.id)

            new_view = NotificationToggleView(self.roles_cog, member)
            embed = self.roles_cog._build_status_embed(member)
            await interaction.response.edit_message(embed=embed, view=new_view)

        return handler


def _get_subscribed_levels(member: discord.Member, prefix: str) -> set[int]:
    levels = set()
    for role in member.roles:
        if role.name.startswith(prefix):
            suffix = role.name[len(prefix):]
            if suffix.isdigit():
                levels.add(int(suffix))
    return levels


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        self.bot = bot
        self.config = config

    async def cog_load(self) -> None:
        self.bot.add_view(StartRunView())

    async def show_notification_wizard(self, interaction: discord.Interaction) -> None:
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            member = await interaction.guild.fetch_member(interaction.user.id)

        view = NotificationToggleView(self, member)
        embed = self._build_status_embed(member)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    def _build_status_embed(self, member: discord.Member) -> discord.Embed:
        subscribed = _get_subscribed_levels(member, self.config.role_prefix)

        lines = []
        for level in range(self.config.min_level, self.config.max_level + 1):
            marker = "\u2705" if level in subscribed else "\u274c"
            lines.append(f"{marker} **RS{level}**")

        embed = discord.Embed(
            title="Notification Preferences",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Toggle levels on or off with the buttons below.")
        return embed

    async def _get_or_create_role(
        self, guild: discord.Guild, level: int
    ) -> discord.Role:
        name = f"{self.config.role_prefix}{level}"
        role = discord.utils.get(guild.roles, name=name)
        if role is None:
            role = await guild.create_role(name=name, mentionable=True)
        return role
