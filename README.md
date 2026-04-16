# Harbinger

A Discord bot for coordinating Hades Star Red Star runs within a corporation. Players manage level-based notifications via buttons, then schedule runs using a slash command wizard. The bot manages the full run lifecycle — crew joining, standby queue, timed reminders, and cancellation — entirely in-channel with embeds and buttons.

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

---

## Bot Permissions

The bot requires these permissions:

| Permission | Purpose |
|---|---|
| View Channels | See and access channels |
| Manage Roles | Create and assign RS level roles |
| Send Messages | Post run messages, reminders, and CTA messages |

**Permissions integer:** `268438528`

> **Note:** The bot creates RS roles at the bottom of the role list. Its own managed role (created on invite) is typically above them already. If role assignment fails, check that the bot's role is higher than the RS roles in **Server Settings > Roles**.

### OAuth2 Invite URL

Use this URL to invite the bot to your server, replacing `YOUR_CLIENT_ID` with your Application ID (found on the **General Information** page):

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=268438528&scope=bot%20applications.commands
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
```

- `DISCORD_TOKEN` (required) — the bot token from the Bot page

#### Optional: Guild Filtering

```env
GUILD_ID=your-guild-id-here
```

- `GUILD_ID` (optional) — restrict the bot to a single Discord server. When set, the bot ignores all interactions from other servers and syncs slash commands only to that guild (instant availability). When omitted, the bot responds to all servers it's been invited to and syncs commands globally (may take up to an hour to propagate).

This is useful for development (run a dev bot alongside production on the same token) or for private single-server deployments.

> **Finding your Guild ID:** Right-click the server icon and select **Copy Server ID**. If you don't see this option, enable Developer Mode: **User Settings** (gear icon) > **App Settings** > **Advanced** > toggle **Developer Mode** on.

#### Optional: Tuning

All game settings have sensible defaults and can be overridden in `.env`. See `.env.example` for the full list. Most users won't need to change anything.

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

### Development

```bash
python -m bot.main
```

---

## Usage

### First-Time Setup

Run `/setup` in the channel where you want the bot to operate. This:

1. Creates RS level roles (RS6-RS12) if they don't already exist
2. Posts a welcome message with **Start a Run** and **Manage Notifications** buttons

The bot operates in whatever channel interactions happen in — there's no fixed channel. The `/setup` command just gives you a convenient starting point.

### Notification Management

Click the **Manage Notifications** button (available on welcome messages, CTA prompts, and the pinned message) to open an ephemeral notification wizard. Toggle RS levels on or off — each level corresponds to a Discord role. When someone schedules a run at your level, you'll be pinged.

### `/rs` — Schedule a Run

Opens an ephemeral wizard to schedule a run. All available levels are shown regardless of your notification preferences.

You can pre-fill details with optional arguments to skip wizard steps:

```
/rs                  -> full wizard (level -> time -> confirm)
/rs 8                -> RS8, skip to time selection
/rs d8 30m           -> DRS8 in 30 minutes, skip to confirmation
/rs 8d 30m           -> same as above (d prefix or suffix)
/rs 9 2h             -> RS9, 2 hours from now
```

Accepted time formats: `30m`, `2h`, `2h30m`, `45m`. Dark prefix/suffix is case-insensitive (`d8`, `8D`, `D8`, `8d`).

Once confirmed, the bot posts a run embed in the channel and pings the relevant RS role. Players join or leave via **Join** / **Leave** buttons. Crew beyond the max (default 4) are placed on standby.

Reminders are sent at T-5 and T-1 minutes, mentioning the confirmed crew. Each reminder replaces the previous one to keep the channel clean.

After a run completes and is cleaned up, the bot posts a silent CTA message with Start a Run and Manage Notifications buttons to keep the channel active.

### `/rs_cancel` — Cancel a Run

Cancels a run you organized. If you have multiple active runs, a selection menu appears. The run embed is updated to show the cancellation and buttons are removed.

### `/setup` — Admin Setup

*(Requires Administrator permission)*

Creates all RS level roles (RS6-RS12) and posts the welcome/CTA message in the current channel. Safe to run multiple times — skips existing roles.

### `/uninstall` — Admin Cleanup

*(Requires Administrator permission)*

Deletes all RS level roles (RS6-RS12). Use this before removing the bot from the server.
