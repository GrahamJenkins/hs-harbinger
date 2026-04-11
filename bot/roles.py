import asyncio

import discord
from discord.ext import commands

from bot.config import Config

class StartRunView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Start a Run",
        style=discord.ButtonStyle.success,
        custom_id="start_run",
    )
    async def start_run(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        wizard_cog = interaction.client.cogs.get("WizardCog")
        if wizard_cog is None:
            await interaction.response.send_message(
                "Bot is still starting up, try again in a moment.", ephemeral=True
            )
            return
        await wizard_cog.start_wizard(interaction)


LEVEL_EMOJI: dict[int, str] = {
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
    10: "🔟",
    11: "🇦",
    12: "🇧",
}

EMOJI_LEVEL: dict[str, int] = {v: k for k, v in LEVEL_EMOJI.items()}


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        self.bot = bot
        self.config = config
        self.role_message_id: int | None = None
        self.active_emoji: dict[int, str] = {
            level: emoji
            for level, emoji in LEVEL_EMOJI.items()
            if config.min_level <= level <= config.max_level
        }

    async def cog_load(self) -> None:
        self.bot.add_view(StartRunView())
        self.bot.loop.create_task(self._setup_with_retry())

    async def _setup_with_retry(self) -> None:
        for attempt in range(5):
            try:
                await self._setup_role_message()
                return
            except discord.DiscordServerError as e:
                wait = 5 * (attempt + 1)
                print(f"[roles] Discord API error ({e.status}), retrying in {wait}s...")
                await asyncio.sleep(wait)
            except Exception as e:
                print(f"[roles] Setup failed: {type(e).__name__}: {e}")
                return
        print("[roles] Setup failed after 5 retries. Run /setup manually when Discord API recovers.")

    async def _setup_role_message(self) -> None:
        try:
            channel = self.bot.get_channel(self.config.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(self.config.channel_id)
        except discord.NotFound:
            print(f"[roles] Channel {self.config.channel_id} not found. Check CHANNEL_ID in .env.")
            return
        except discord.Forbidden:
            print(f"[roles] Bot cannot access channel {self.config.channel_id}. Check bot permissions (View Channel).")
            return

        try:
            pinned = await channel.pins()
        except discord.Forbidden:
            print(f"[roles] Bot cannot read pins in #{channel.name}. Check bot permissions (Read Message History).")
            return

        for msg in pinned:
            if msg.author.id == self.bot.user.id and msg.embeds:
                embed = msg.embeds[0]
                if embed.title == "Red Star Level Subscription":
                    self.role_message_id = msg.id
                    await self._ensure_reactions(msg)
                    return

        embed = self._build_embed()
        view = StartRunView()
        try:
            msg = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            print(f"[roles] Bot cannot send messages in #{channel.name}. Check bot permissions (Send Messages, Embed Links).")
            return

        try:
            await msg.pin()
        except discord.Forbidden:
            print(f"[roles] Bot cannot pin messages in #{channel.name}. Check bot permissions (Pin Messages).")

        self.role_message_id = msg.id
        await self._ensure_reactions(msg)

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Red Star Level Subscription",
            description=(
                "React to opt in to notifications for Red Star runs at each level.\n"
                "You'll be pinged when someone schedules a run you qualify for.\n\n"
                "Note: 🇦 = RS11, 🇧 = RS12"
            ),
            color=discord.Color.gold(),
        )
        for level, emoji in self.active_emoji.items():
            embed.add_field(name=f"{emoji}  RS{level}", value="\u200b", inline=True)
        return embed

    async def _ensure_reactions(self, message: discord.Message) -> None:
        existing = {str(r.emoji) for r in message.reactions}
        for emoji in self.active_emoji.values():
            if emoji not in existing:
                await message.add_reaction(emoji)

    async def _get_or_create_role(self, guild: discord.Guild, level: int) -> discord.Role:
        name = f"{self.config.role_prefix}{level}"
        role = discord.utils.get(guild.roles, name=name)
        if role is None:
            role = await guild.create_role(name=name, mentionable=True)
        return role

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self.role_message_id is None or payload.message_id != self.role_message_id:
            return
        if payload.user_id == self.bot.user.id:
            return

        emoji_str = str(payload.emoji)
        level = EMOJI_LEVEL.get(emoji_str)

        guild = self.bot.get_guild(payload.guild_id)
        channel = self.bot.get_channel(payload.channel_id)
        member = payload.member or await guild.fetch_member(payload.user_id)

        if level is None or level not in self.active_emoji:
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, member)
            return

        role = await self._get_or_create_role(guild, level)
        await member.add_roles(role)
        member = await guild.fetch_member(member.id)
        asyncio.create_task(self._send_confirmation(channel, member))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if self.role_message_id is None or payload.message_id != self.role_message_id:
            return
        if payload.user_id == self.bot.user.id:
            return

        emoji_str = str(payload.emoji)
        level = EMOJI_LEVEL.get(emoji_str)
        if level is None or level not in self.active_emoji:
            return

        guild = self.bot.get_guild(payload.guild_id)
        channel = self.bot.get_channel(payload.channel_id)
        member = await guild.fetch_member(payload.user_id)

        role = discord.utils.get(guild.roles, name=f"{self.config.role_prefix}{level}")
        if role is not None:
            await member.remove_roles(role)

        member = await guild.fetch_member(member.id)
        asyncio.create_task(self._send_confirmation(channel, member))

    async def _send_confirmation(
        self, channel: discord.abc.Messageable, member: discord.Member
    ) -> None:
        prefix = self.config.role_prefix
        rs_roles = sorted(
            [
                r.name
                for r in member.roles
                if r.name.startswith(prefix) and r.name[len(prefix):].isdigit()
            ],
            key=lambda name: int(name[len(prefix):]),
        )
        if rs_roles:
            role_list = ", ".join(rs_roles)
            content = f"✅ {member.display_name}, you will be notified for: **{role_list}**"
        else:
            content = f"✅ {member.display_name}, you are not subscribed to any RS levels."

        msg = await channel.send(content)
        await asyncio.sleep(5)
        await msg.delete()
