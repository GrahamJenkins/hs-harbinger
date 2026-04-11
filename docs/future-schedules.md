# Future: Recurring Schedules

Status: **Planned** — implement after core bot is tested and deployed.

## Problem

Ad-hoc `/rs` runs work for spontaneous coordination, but many corps have regular
play windows (e.g. "DRS8 every evening at 10pm"). Without recurring schedules,
someone has to manually `/rs` every day.

## Design

### Storage: `schedules.toml`

A flat TOML file alongside `config.toml`. Human-editable, version-controllable,
no database required.

```toml
[[schedule]]
level = 8
dark = true
cron = "0 22 * * *"       # 10pm UTC daily
label = "Daily DRS8"

[[schedule]]
level = 9
dark = false
cron = "0 18 * * 1,3,5"   # MWF 6pm UTC
label = "RS9 MWF"

[[schedule]]
level = 7
dark = false
cron = "0 14 * * 6,0"     # Weekends 2pm UTC
label = "Weekend RS7"
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `level` | int | yes | Red Star level (6-12) |
| `dark` | bool | no | Dark variant, default false |
| `cron` | string | yes | Standard 5-field cron expression (minute hour day month weekday), UTC |
| `label` | string | no | Human-readable label shown in the run embed |
| `lead_minutes` | int | no | How far before the scheduled time to post the run. Default: config.default_lead_minutes |

### Implementation

**New Cog: `scheduler.py`**

- On `cog_load`: parse `schedules.toml`, create one `asyncio.Task` per schedule entry.
- Each task: compute next fire time from cron expression, sleep until
  `fire_time - lead_minutes`, then create a Run in RunStore and post the embed
  (same as wizard's `_create_run` — extract to a shared helper in `runs.py` or a
  utility module).
- After posting, compute next fire time and loop.
- On `cog_unload`: cancel all tasks.

**Cron parsing:** Use a lightweight cron library (e.g. `croniter`) or write a
minimal parser — the subset we need is simple (no seconds, no year, just
minute/hour/day/month/weekday).

**Admin commands:**

- `/schedules` — list active recurring schedules with next fire times.
- `/reload_schedules` (admin only) — re-read `schedules.toml` without restart.

### Why not SQLite

Recurring schedules are configuration, not runtime state. They change rarely,
are reviewed by humans, and the dataset is tiny. A TOML file is:
- Editable with any text editor
- Diffable in git
- Readable without tooling
- Zero additional dependencies

### What this does NOT solve

**Ad-hoc run persistence across restarts.** Active runs created via `/rs` are
still in-memory and lost on restart. This is acceptable for v1 — ad-hoc runs are
short-lived (5min to 8hr max lead time), restarts are infrequent, and the cost of
rescheduling is one `/rs` command. If this becomes a pain point, add SQLite for
the RunStore at that time.
