# HS-Bot — Red Star Coordination Bot

## Overview

A lightweight Discord bot for coordinating Hades Star Red Star runs within a
corporation. Players opt into level-based notifications via a react-role message,
then schedule runs using a slash command wizard. The bot manages the run lifecycle
entirely in-channel with embeds, buttons, and timed reminders.

No database. Roles for level eligibility, in-memory dict for active runs,
`config.toml` for tunables.

---

## Project Structure

```
hs-bot/
├── bot/
│   ├── __init__.py        # empty
│   ├── main.py            # entry point, bot setup, cog loading, on_ready
│   ├── config.py          # loads .env + config.toml, exposes typed Config object
│   ├── roles.py           # Cog: pinned react-role message, reaction handlers
│   ├── wizard.py          # Cog: /rs command, arg parsing, ephemeral button wizard
│   ├── runs.py            # RunStore (in-memory), Run dataclass, join/leave logic
│   ├── embeds.py          # all embed/view builders (run embed, summary, etc.)
│   ├── reminders.py       # Cog: background task that fires T-5 and T-1 pings
│   └── cancel.py          # Cog: /rs_cancel command, ephemeral selection
├── config.toml
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── .gitignore
```

---

## Dependency Graph (import direction)

```
config.py        ← imported by everything
runs.py          ← imports config
embeds.py        ← imports runs, config
roles.py         ← imports config (Cog, reads config for level range)
wizard.py        ← imports config, runs, embeds (Cog)
reminders.py     ← imports runs, embeds (Cog)
cancel.py        ← imports runs (Cog)
main.py          ← imports config, loads all Cogs
```

No circular dependencies. `config`, `runs`, and `embeds` are pure library modules.
`roles`, `wizard`, `reminders`, and `cancel` are discord.py Cogs loaded by `main.py`.

---

## Component Specifications

### 1. config.py

**Purpose:** Load and validate configuration from `.env` and `config.toml`.

**Interface:**

```python
@dataclass(frozen=True)
class Config:
    token: str              # from DISCORD_TOKEN env var
    guild_id: int           # from GUILD_ID env var
    channel_id: int         # from CHANNEL_ID env var
    min_level: int          # default 6
    max_level: int          # always 12
    dark_min_level: int     # default 7
    max_players: int        # default 4
    default_lead_minutes: int   # default 30
    min_lead_minutes: int       # default 5
    max_lead_hours: int         # default 8
    reminder_minutes: list[int] # default [5, 1]
    role_prefix: str            # default "RS"

def load_config() -> Config:
    """Load from .env and config.toml. Raise on missing required values."""
```

**Behavior:**
- Uses `tomllib` (stdlib 3.11+) for config.toml.
- Uses `os.environ` for .env values (dotenv loaded in main.py before import).
- Validates: token non-empty, guild_id/channel_id are ints, min_level <= max_level,
  dark_min_level >= min_level, reminder_minutes sorted descending.
- Frozen dataclass — immutable after creation.

---

### 2. runs.py

**Purpose:** In-memory run state management. Pure data, no Discord API calls.

**Interface:**

```python
@dataclass
class Run:
    id: str                    # uuid4 hex, short (8 chars)
    level: int
    dark: bool
    organizer_id: int          # Discord user ID
    organizer_name: str        # Display name at creation time
    start_time: float          # Unix timestamp
    created_at: float          # Unix timestamp
    crew: list[int]            # user IDs, first max_players are confirmed
    crew_names: dict[int, str] # user_id -> display name
    message_id: int | None     # ID of the run embed message (set after posting)
    reminded: set[int]         # reminder minutes already sent (e.g. {5, 1})
    cancelled: bool

    @property
    def confirmed(self) -> list[int]:
        """First max_players from crew."""

    @property
    def standby(self) -> list[int]:
        """crew[max_players:]"""

    @property
    def is_full(self) -> bool:
        """len(crew) >= max_players"""


class RunStore:
    """Thread-safe in-memory run storage."""

    def create(self, level: int, dark: bool, organizer_id: int,
               organizer_name: str, start_time: float, max_players: int) -> Run: ...
    def get(self, run_id: str) -> Run | None: ...
    def remove(self, run_id: str) -> Run | None: ...
    def get_by_organizer(self, user_id: int) -> list[Run]: ...
    def get_by_message(self, message_id: int) -> Run | None: ...
    def active_runs(self) -> list[Run]: ...
    def join(self, run_id: str, user_id: int, display_name: str) -> bool:
        """Add user to crew. Returns False if already in crew."""
    def leave(self, run_id: str, user_id: int) -> bool:
        """Remove user from crew. Returns False if not in crew."""
    def cleanup_expired(self, grace_minutes: int = 45) -> list[Run]:
        """Remove runs whose start_time + grace is in the past."""
```

**Behavior:**
- `RunStore` uses a plain `dict[str, Run]` internally. Access is single-threaded
  (asyncio), no lock needed.
- `create()` generates a short UUID, sets `created_at` to now, returns the Run.
- Organizer is automatically added as first crew member on create.
- `cleanup_expired` is called periodically by the reminders Cog.

---

### 3. embeds.py

**Purpose:** Build all Discord embeds and views (button layouts). No state mutation.

**Interface:**

```python
def build_run_embed(run: Run, config: Config) -> discord.Embed:
    """
    Build the main run embed shown in channel.

    Title format:
      - Normal: "⭐ Red Star {level}"
      - Dark:   "💀 Dark Red Star {level}"

    Fields:
      - "Organized by" — @mention of organizer
      - "Starts" — Discord relative timestamp <t:{unix}:R>
      - "Crew ({count}/{max})" — numbered list of display names (@mentions)
        1. DisplayName (@user)
        2. ...
      - "Standby" — if crew > max_players, numbered from max+1
        5. DisplayName (@user) (standby)

    Footer: Run ID for reference

    Color: red for dark, gold for normal
    """

def build_summary_embed(level: int, dark: bool, start_time: float,
                        config: Config) -> discord.Embed:
    """
    Ephemeral summary shown to organizer before confirming.
    Shows level, dark status, start time as relative timestamp.
    """


class RunView(discord.ui.View):
    """
    Persistent view attached to the run embed message.
    timeout=None (persistent across bot restarts via re-registration).

    Buttons:
      - "Join" (green, style=success) — custom_id="run_join:{run_id}"
      - "Leave" (red, style=danger)  — custom_id="run_leave:{run_id}"

    Callbacks:
      - on Join: call RunStore.join(), if success edit message with updated embed.
        If already in crew, ephemeral "You're already in this run."
      - on Leave: call RunStore.leave(), if success edit message with updated embed.
        If not in crew, ephemeral "You're not in this run."
      - On join when crew reaches max_players: embed updates to show "Full — join as standby"
      - On join when standby reaches max_players (8 total): ephemeral suggestion
        "This run is packed! Consider starting a second star."
    """


class WizardLevelView(discord.ui.View):
    """
    Ephemeral view for level selection in wizard.
    One button per level the user has roles for.
    Buttons labeled "RS6", "RS7", etc.
    Style: primary (blue).
    timeout=120 seconds.
    """


class WizardDarkView(discord.ui.View):
    """
    Ephemeral view for dark selection. Two buttons:
      - "Normal" (secondary/grey)
      - "Dark 💀" (danger/red)
    timeout=120 seconds.
    """


class WizardTimeView(discord.ui.View):
    """
    Ephemeral view for time selection. Preset buttons + text instruction:
      - "5 min" (secondary)
      - "15 min" (secondary)
      - "30 min" (primary) — highlighted as default
      - "1 hour" (secondary)
      - "2 hours" (secondary)
      - "4 hours" (secondary)
    Also include a text prompt: "Or type a time like `45m` or `2h30m`"
    timeout=120 seconds.

    For typed responses: the wizard Cog listens for a follow-up message from the
    same user in the same channel within the timeout, parses it, then deletes it.
    """


class WizardSummaryView(discord.ui.View):
    """
    Ephemeral confirmation view. Buttons:
      - "Confirm" (success/green)
      - "Edit Level" (secondary)
      - "Edit Time" (secondary)
      - "Cancel" (danger/red)
    timeout=120 seconds.
    """


class CancelSelectView(discord.ui.View):
    """
    Ephemeral view for /rs_cancel. One button per active run the user organized.
    Label: "RS{level}{'d' if dark} at <t:{time}:t>"
    Style: danger (red).
    Plus a "Never mind" secondary button.
    timeout=60 seconds.
    """
```

---

### 4. roles.py (Cog)

**Purpose:** Manage the pinned react-role message for level subscription.

**Behavior:**

- On bot ready (`on_ready` or `cog_load`):
  - Fetch the configured channel.
  - Look for an existing pinned message from this bot that matches the role message
    format (check pinned messages, match by content/embed pattern).
  - If not found, post a new one and pin it.
  - Ensure all level emoji reactions are present on the message (add any missing).

- **Role message format** (embed):
  - Title: "Red Star Level Subscription"
  - Description: "React to opt in to notifications for Red Star runs at each level.
    You'll be pinged when someone schedules a run you qualify for."
  - Fields: one per level, showing the emoji and "RS{N}"
  - Reactions: keycap digit emoji for 6-9 (6️⃣ 7️⃣ 8️⃣ 9️⃣),
    then 🔟 for 10.
    For 11 and 12: use regional indicator letters 🇦 (11) and 🇧 (12).
    Document the mapping clearly in the embed description.

- **Level-emoji mapping** (defined in this module, importable):
  ```python
  LEVEL_EMOJI: dict[int, str] = {
      6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣",
      10: "🔟", 11: "🇦", 12: "🇧",
  }
  ```

- **on_raw_reaction_add / on_raw_reaction_remove:**
  - Ignore if message is not the role message.
  - Ignore if user is the bot.
  - Map emoji to level. If no match, remove the reaction (unknown emoji).
  - Ensure the Discord role `{prefix}{level}` exists in the guild. Create if missing.
  - Add/remove the role from the member.
  - Send an ephemeral-like response: since reactions don't support ephemeral replies,
    send a message in channel that auto-deletes after 5 seconds.
    Content: "✅ {member.display_name}, you will be notified for: **RS7, RS8, RS9**"
    (list all RS roles the member currently has, after the change).

- **Role creation:** If a role `RS{N}` doesn't exist, create it with no special
  permissions, mentionable=True (so the bot can ping it).

---

### 5. wizard.py (Cog)

**Purpose:** Handle `/rs` slash command with smart argument parsing and wizard flow.

**Slash command definition:**
```python
@app_commands.command(name="rs", description="Schedule a Red Star run")
@app_commands.describe(args="Optional: level, 'd' for dark, time (e.g. '8d 30m')")
async def rs(self, interaction: discord.Interaction, args: str = ""):
```

**Argument parsing (parse_rs_args function):**

Input: raw string like "8d 2h30m" or "9 15m" or "" or "7d" or "45m"
Output: `ParsedArgs(level: int | None, dark: bool | None, minutes: int | None)`

Rules:
- Token with digits 6-12 optionally followed by 'd' → level (and dark if 'd' present)
- Token matching `(\d+)h(?:(\d+)m)?` or `(\d+)m` → minutes
- Tokens are space-separated, order doesn't matter
- Unknown tokens are silently ignored (wizard asks for missing data)
- Level out of range (e.g. "13", "5") → treated as unknown, wizard asks
- Dark requested for level < dark_min_level → warn and ask to confirm level

**Wizard flow:**

1. Delete the invoking interaction's message (auto-delete the /rs command).
   Actually: use `interaction.response.send_message(ephemeral=True)` — the
   slash command invocation is inherently ephemeral to begin with in the sense
   that only the invoker sees the command. We respond ephemerally.

2. Determine what's known from args vs. what needs wizard steps.

3. **Level step** (if level unknown):
   - Check which RS roles the invoking user has.
   - If none: ephemeral error "You need to opt in to at least one RS level first.
     See the pinned message in this channel."
   - Show `WizardLevelView` with buttons only for levels the user has roles for.
   - User clicks → level is set.

4. **Dark step** (if dark unknown AND level >= dark_min_level):
   - Show `WizardDarkView`.
   - User clicks → dark is set.
   - If level < dark_min_level, dark defaults to False, skip this step.

5. **Time step** (if minutes unknown):
   - Show `WizardTimeView` with preset buttons.
   - User clicks a preset → minutes set.
   - OR user types a value → wizard parses it, deletes the typed message.
   - Validate: min_lead_minutes <= minutes <= max_lead_hours * 60.
     If out of range, show error and re-prompt.

6. **Summary step** (always shown):
   - Compute start_time = now + minutes (as Unix timestamp).
   - Show `WizardSummaryView` with the summary embed.
   - "Confirm" → proceed to run creation.
   - "Edit Level" → go back to level step.
   - "Edit Time" → go back to time step.
   - "Cancel" → ephemeral "Run cancelled." and clean up.

7. **Run creation:**
   - Create Run in RunStore.
   - Build run embed + RunView.
   - Send as a normal (non-ephemeral) message in the channel.
   - Ping relevant roles: mention `@RS{level}` through `@RS{max_level}` (higher
     level players can join lower runs — ping everyone at that level or above).
   - Store the message ID on the Run.
   - Edit the ephemeral wizard message to "Run created!" or delete it.

**Wizard state:** Stored as a simple dict keyed by `interaction.user.id`. Each entry
holds `{level, dark, minutes}` with None for unknowns. Cleaned up on confirm/cancel/timeout.

---

### 6. reminders.py (Cog)

**Purpose:** Background loop that checks active runs and sends reminder pings.

**Behavior:**

- `@tasks.loop(seconds=15)` — runs every 15 seconds to check timing.
- For each active run in RunStore:
  - For each reminder interval in `config.reminder_minutes` (e.g. [5, 1]):
    - If `start_time - now <= interval_minutes * 60` AND interval not in `run.reminded`:
      - Send a message in the channel mentioning confirmed crew members:
        "⏰ **RS{level}{'💀' if dark}** starting <t:{start_time}:R>!
        {mentions of confirmed crew}"
      - Add interval to `run.reminded`.
  - If `now >= start_time`:
    - Send final "🚀 **RS{level}{'💀' if dark}** — GO TIME! {mentions}"
    - Do NOT immediately remove the run — keep it for `grace_minutes` so the
      embed stays visible and people can still reference it.
  - Call `RunStore.cleanup_expired()` to remove stale runs.
    When a run is cleaned up, edit its embed to show "Run completed" and remove
    the buttons (edit view to None).

---

### 7. cancel.py (Cog)

**Purpose:** Handle run cancellation by the organizer.

**Slash command:**
```python
@app_commands.command(name="rs_cancel", description="Cancel a Red Star run you organized")
async def rs_cancel(self, interaction: discord.Interaction):
```

**Flow:**
1. Respond ephemerally.
2. Look up active runs organized by this user via `RunStore.get_by_organizer()`.
3. If none: "You don't have any active runs to cancel."
4. If one: show confirmation — "Cancel RS{level}{'💀' if dark} at <t:...>? [Yes] [No]"
5. If multiple: show `CancelSelectView` with a button per run.
6. On confirm:
   - Mark run as cancelled.
   - Edit the run embed in channel to show "❌ Run cancelled by {organizer}"
   - Remove buttons from the embed message.
   - Remove from RunStore.
   - Ephemeral: "Run cancelled."

---

### 8. main.py

**Purpose:** Bot entry point. Loads env, creates bot, registers Cogs, runs.

**Behavior:**
```python
import os
from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from bot.config import load_config

config = load_config()

intents = discord.Intents.default()
intents.members = True          # needed for role management
intents.message_content = True  # needed for typed time input in wizard
intents.reactions = True        # needed for react-roles

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.add_cog(RolesCog(bot, config))
    await bot.add_cog(WizardCog(bot, config, run_store))
    await bot.add_cog(RemindersCog(bot, config, run_store))
    await bot.add_cog(CancelCog(bot, config, run_store))
    await bot.tree.sync(guild=discord.Object(id=config.guild_id))
    print(f"Logged in as {bot.user}")

run_store = RunStore(max_players=config.max_players)
bot.run(config.token)
```

Key points:
- Guild-scoped command sync (instant, no 1-hour global cache).
- RunStore created once, shared across Cogs.
- `python-dotenv` for .env loading.

---

## Deployment Files

### pyproject.toml
- Python >=3.11
- Dependencies: `discord.py>=2.3`, `python-dotenv>=1.0`, `tomli` (only if <3.11, but we target 3.11+ so use `tomllib`)
- Entry point: `python -m bot.main`

### Dockerfile
- Base: `python:3.12-slim`
- Copy requirements, install deps
- Copy source
- CMD: `python -m bot.main`

### docker-compose.yml
- Single service, env_file: .env, restart: unless-stopped
- Mount config.toml as a volume for easy editing

### .env.example
```
DISCORD_TOKEN=your-bot-token-here
GUILD_ID=your-guild-id-here
CHANNEL_ID=your-rs-channel-id-here
```

### .gitignore
Standard Python + .env

---

## Discord Permissions Required

The bot needs these gateway intents:
- `GUILD_MEMBERS` (manage roles)
- `GUILD_MESSAGE_REACTIONS` (react-role)
- `MESSAGE_CONTENT` (typed time input)

And these permissions:
- Manage Roles (create/assign RS roles)
- Send Messages
- Manage Messages (delete user's typed time input, auto-delete confirmations)
- Embed Links
- Add Reactions (seed react-role message)
- Read Message History (find pinned message on startup)

---

## Edge Cases and Notes

- **Bot restart:** Active runs are lost. This is acceptable. The role message persists
  because it's a real Discord message — the bot re-discovers it on startup by scanning
  pinned messages.
- **Persistent views:** discord.py supports re-registering persistent views on startup
  using `bot.add_view()` with known custom_ids. Since runs are lost on restart, we
  don't re-register RunViews — orphaned buttons will just do nothing (interaction
  fails silently or shows "interaction failed"). The reminders Cog won't clean these
  up since it has no Run data. Acceptable for v1.
- **Race conditions:** asyncio is single-threaded, so RunStore operations are atomic.
  No locking needed.
- **Role emoji for 11/12:** Using 🇦 and 🇧 (regional indicators) is a pragmatic
  choice since Discord doesn't have keycap emoji above 10. The embed description
  explains the mapping.
