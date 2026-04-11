import os
from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from bot.config import load_config
from bot.roles import RolesCog
from bot.wizard import WizardCog
from bot.reminders import RemindersCog
from bot.cancel import CancelCog
from bot.admin import AdminCog
from bot.runs import RunStore

config = load_config()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

run_store = RunStore(max_players=config.max_players)
_ready = False


@bot.event
async def on_ready():
    global _ready
    if _ready:
        print(f"Reconnected as {bot.user}")
        return

    try:
        roles_cog = RolesCog(bot, config)
        await bot.add_cog(roles_cog)
        print("[startup] RolesCog loaded")

        await bot.add_cog(WizardCog(bot, config, run_store))
        print("[startup] WizardCog loaded")

        await bot.add_cog(RemindersCog(bot, config, run_store))
        print("[startup] RemindersCog loaded")

        await bot.add_cog(CancelCog(bot, config, run_store))
        print("[startup] CancelCog loaded")

        await bot.add_cog(AdminCog(bot, config, roles_cog))
        print("[startup] AdminCog loaded")

        guild = discord.Object(id=config.guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[startup] Synced {len(synced)} commands to guild {config.guild_id}: {[c.name for c in synced]}")

        _ready = True
        print(f"Logged in as {bot.user}")
    except Exception as e:
        print(f"[startup] FATAL: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def main():
    bot.run(config.token)


if __name__ == "__main__":
    main()
