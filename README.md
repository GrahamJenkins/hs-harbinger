# Harbinger

A Discord bot for coordinating Hades Star Red Star runs within a corporation. Players subscribe to level-based notifications via a react-role message, then schedule runs using a slash command. The bot manages the full run lifecycle — crew joining, standby queue, timed reminders, and cancellation — entirely in-channel with embeds and buttons.

---

## Setup

### 1. Create a Discord Application

1. Go to https://discord.com/developers/applications and click **New Application**.
2. Give it a name (e.g. `Harbinger`) and click **Create**.

### 2. Create a Bot User

1. In the left sidebar, click **Bot**.
2. Click **Add Bot** and confirm.
3. Under **Token**, click **Reset Token**, copy it, and save it somewhere safe — you'll need it for `.env`.

### 3. Enable Privileged Gateway Intents

Still on the **Bot** page, scroll down to **Privileged Gateway Intents** and enable:

- **Server Members Intent** — required for role management
- **Message Content Intent** — required for typed time input in the run wizard

> **Note:** The Guild Messages intent is enabled by default and does not need to be toggled manually.

---

## Bot Permissions

The bot requires these permissions:

| Permission | Purpose |
|---|---|
| View Channels | See and access the configured channel |
| Manage Roles | Create and assign RS level roles |
| Send Messages | Post run embeds and reminders |
| Manage Messages | Delete temporary confirmations and user-typed input |
| Pin Messages | Pin the role subscription message |
| Embed Links | Post rich embeds |
| Add Reactions | Seed the react-role message with level emoji |
| Read Message History | Find the pinned role message on startup |

**Permissions integer:** `2251800082213952`

### Role Hierarchy

The OAuth2 invite creates a managed bot role (e.g. "Harbinger") with the correct permissions. After inviting, move this role **up** in the role list:

1. Go to **Server Settings → Roles**
2. Drag the Harbinger role above any member roles

Discord requires a bot's role to be higher than any roles it creates or assigns. The RS6–RS12 roles are created at the bottom of the list, so the bot's role just needs to not be the lowest.

> **If you change the permissions integer** (e.g. after a bot update), Discord won't update an existing bot role. You need to remove the bot (**Server Settings → Integrations → Harbinger → Remove**) and re-invite with the new URL. This is a Discord limitation.

### OAuth2 Invite URL

Use this URL to invite the bot to your server, replacing `YOUR_CLIENT_ID` with your Application ID (found on the **General Information** page — Discord labels this "Application ID", the OAuth2 URL parameter is `client_id`, they're the same value):

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2251800082213952&scope=bot%20applications.commands
```

---

## Configuration

### .env

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

```env
DISCORD_TOKEN=your-bot-token-here
GUILD_ID=your-guild-id-here
CHANNEL_ID=your-rs-channel-id-here
```

- `DISCORD_TOKEN` — the bot token from the Bot page
- `GUILD_ID` — your Discord server's ID (right-click the server icon → **Copy Server ID**)
- `CHANNEL_ID` — the ID of the channel where the bot should operate (right-click the channel → **Copy Channel ID**)

> **Can't see "Copy ID" in the right-click menu?** You need to enable Developer Mode:
> **User Settings** (gear icon) → **App Settings** → **Advanced** → toggle **Developer Mode** on.
> This applies to both Guild ID and Channel ID.

### config.toml

Tunables with their defaults:

```toml
[levels]
min = 6           # lowest RS level to support
max = 12          # highest RS level (always 12)
dark_min = 7      # minimum level at which Dark RS is available
max_players = 4   # confirmed crew size before standby queue starts

[timing]
default_lead_minutes = 30   # pre-selected default in the time wizard
min_lead_minutes = 5        # earliest a run can be scheduled
max_lead_hours = 8          # furthest out a run can be scheduled
reminder_minutes = [5, 1]   # ping crew at T-5m and T-1m (descending order)

[roles]
prefix = "RS"   # Discord role name prefix, e.g. "RS8"
```

---

## Running

### Direct

```bash
pip install .
python -m bot.main
```

### Docker

```bash
docker compose up -d
```

The `config.toml` is mounted as a volume so you can edit it without rebuilding.

### Development

```bash
pip install -e .
python -m bot.main
```

---

## Usage

### React-Role Message

On startup, the bot posts (or finds) a pinned message in the configured channel. Players react with the level emoji to subscribe to run notifications for that level:

| Emoji | Level |
|---|---|
| 6️⃣ – 9️⃣ | RS 6–9 |
| 🔟 | RS 10 |
| 🇦 | RS 11 |
| 🇧 | RS 12 |

After each reaction, the bot briefly confirms which RS levels you're now subscribed to.

The pinned message also includes a **Start a Run** button as a shortcut to the `/rs` wizard.

### `/rs` — Schedule a Run

Opens an ephemeral wizard to schedule a run. The wizard presents your subscribed levels as buttons — normal (RS) and dark (DRS) variants side by side — then asks for a time, and shows a confirmation summary.

You can pre-fill details with optional arguments to skip wizard steps:

```
/rs                  → full wizard (level/dark → time → confirm)
/rs 8                → RS8, skip to time selection
/rs d8 30m           → DRS8 in 30 minutes, skip to confirmation
/rs 8d 30m           → same as above (d prefix or suffix)
/rs 9 2h             → RS9, 2 hours from now
```

Accepted time formats: `30m`, `2h`, `2h30m`, `45m`. Dark prefix/suffix is case-insensitive (`d8`, `8D`, `D8`, `8d`). Level must be one you're subscribed to.

Once confirmed, the bot posts a public run embed in the channel and pings all players subscribed to that level or higher. Players join or leave via **Join** / **Leave** buttons. Crew beyond the max (default 4) are placed on standby.

Reminders are sent at T-5 and T-1 minutes, mentioning the confirmed crew. Each reminder replaces the previous one to keep the channel clean. Buttons are removed once the run starts.

### `/rs_cancel` — Cancel a Run

Cancels a run you organized. If you have multiple active runs, a selection menu appears. The run embed is updated to show the cancellation and the buttons are removed.

### `/setup` — Admin Setup

*(Requires Administrator permission)*

Pre-creates all RS roles (RS6–RS12) and posts/re-pins the role subscription message. Safe to run multiple times — skips existing roles and reuses existing messages.

### `/uninstall` — Admin Cleanup

*(Requires Administrator permission)*

Deletes all RS roles and removes the pinned role subscription message. Use this before removing the bot from the server.
