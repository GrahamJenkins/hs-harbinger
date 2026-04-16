# Harbinger — Red Star Coordination Bot

## Overview

A Discord bot for coordinating Hades Star Red Star runs within a corporation.
Players manage level-based notifications via an ephemeral button wizard, then
schedule runs using a slash command. The bot manages the run lifecycle entirely
in-channel with markdown messages, buttons, and timed reminders.

No database. Roles for level notifications, in-memory dict for active runs,
`.env` for tunables.

---

## Project Structure

```
harbinger/
├── bot/
│   ├── __init__.py        # empty
│   ├── main.py            # entry point, bot setup, cog loading, guild filter
│   ├── config.py          # loads .env, exposes typed Config object
│   ├── roles.py           # Cog: notification wizard, persistent button views
│   ├── wizard.py          # Cog: /rs command, arg parsing, ephemeral button wizard
│   ├── runs.py            # RunStore (in-memory), Run dataclass, join/leave logic
│   ├── embeds.py          # all message builders and views (run text, summary, etc.)
│   ├── reminders.py       # Cog: background task for reminders and CTA messages
│   ├── cancel.py          # Cog: /rs_cancel command
│   └── admin.py           # Cog: /setup and /uninstall commands
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
config.py        <- imported by everything
runs.py          <- imports nothing (pure data)
roles.py         <- imports config (guild filter, notification views)
embeds.py        <- imports runs, config, roles (guild filter)
wizard.py        <- imports config, runs, embeds (Cog)
reminders.py     <- imports config, runs, embeds, roles (Cog)
cancel.py        <- imports config, runs, embeds (Cog)
admin.py         <- imports config, roles (Cog)
main.py          <- imports config, loads all Cogs
```

---

## Component Specifications

### 1. config.py

**Purpose:** Load and validate configuration from `.env`.

```python
@dataclass(frozen=True)
class Config:
    token: str              # from DISCORD_TOKEN env var
    guild_id: int | None    # from GUILD_ID env var (optional)
    min_level: int          # default 6
    max_level: int          # always 12
    dark_min_level: int     # default 7
    max_players: int        # default 4
    dark_max_players: int   # default 3
    default_lead_minutes: int   # default 30
    min_lead_minutes: int       # default 5
    max_lead_hours: int         # default 8
    reminder_minutes: list[int] # default [5, 1]
    role_prefix: str            # default "RS"
```

- `guild_id` is optional. When set, the bot only responds to that guild.

---

### 2. runs.py

**Purpose:** In-memory run state management. Pure data, no Discord API calls.

```python
@dataclass
class Run:
    id: str                    # uuid4 hex (8 chars)
    level: int
    dark: bool
    organizer_id: int
    organizer_name: str
    start_time: float          # Unix timestamp
    created_at: float          # Unix timestamp
    crew: list[int]
    crew_names: dict[int, str]
    channel_id: int            # channel where the run was created
    message_id: int | None     # run embed message ID
    reminded: set
    cancelled: bool
```

---

### 3. roles.py (Cog)

**Purpose:** Notification management via ephemeral button wizard.

- **StartRunView** — persistent view with "Start a Run" and "Manage Notifications"
  buttons. Used on CTA messages and welcome messages.
- **NotificationToggleView** — ephemeral per-user view showing toggle buttons for
  each RS level. Green = subscribed, grey = not. Includes a Close button.
- **Guild filtering** — `_check_guild()` helper checks interactions against
  `config.guild_id`. Used by all persistent views.
- On startup, registers `StartRunView` as a persistent view.
- No pinned messages or reactions.

---

### 4. wizard.py (Cog)

**Purpose:** `/rs` slash command with smart argument parsing and wizard flow.

- Shows all available levels (min through max), not restricted by user roles.
- Dark variants shown for levels >= `dark_min_level`.
- Time presets: Now, 5m, 10m, 15m, 20m, 30m, 1h, 2h, 4h (uniform button style).
- Users can also type a time (e.g. `45m`, `2h30m`).
- On confirm: creates run, posts message with role ping, stores channel_id on run.
- For "now" runs, the reminder loop skips the launch message since the wizard's
  role ping serves as the notification.

---

### 5. reminders.py (Cog)

**Purpose:** Background loop for reminders, run lifecycle, and CTA messages.

- `@tasks.loop(seconds=15)` checks all active runs.
- Interval reminders (T-5m, T-1m) only fire when `remaining > 0` (prevents
  duplicate pings on immediate runs).
- Launch message skipped for runs created < 30 seconds ago.
- On run start: edits message to show "Scanned" time, clears role mention.
- On run expiry (configurable grace): updates message to completed state, removes buttons.
- After expiry: posts a silent CTA message with Start a Run / Manage
  Notifications buttons. Previous CTA is deleted first.
- Each run's channel_id is used for posting — no global channel config needed.
- Error handling: each run is processed in its own try/except, loop has an
  error handler to prevent crashes from killing the task.

---

### 6. cancel.py (Cog)

**Purpose:** `/rs_cancel` command for organizers.

---

### 7. admin.py (Cog)

**Purpose:** `/setup` and `/uninstall` admin commands.

- `/setup` — creates RS level roles and posts the welcome/CTA message in the
  current channel.
- `/uninstall` — deletes RS level roles.

---

### 8. main.py

**Purpose:** Bot entry point.

- Loads config, creates bot, registers cogs.
- `bot.config` stores the config for access from views.
- Global `interaction_check` on the command tree filters by guild_id (if set).
- Command sync: guild-scoped if guild_id is set (instant), global otherwise.

---

## Edge Cases

- **Bot restart:** Active runs are lost (in-memory). Persistent views
  (StartRunView) survive via custom_id re-registration. Orphaned RunView
  buttons fail silently.
- **Race conditions:** asyncio is single-threaded, so RunStore operations are
  atomic. No locking needed.
- **Multiple instances on same token:** Use GUILD_ID filtering to isolate dev
  and production instances. Both receive all Discord events, but each only
  responds to its configured guild.
