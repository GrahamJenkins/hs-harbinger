import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

_TOML_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int
    channel_id: int
    min_level: int
    max_level: int
    dark_min_level: int
    max_players: int
    default_lead_minutes: int
    min_lead_minutes: int
    max_lead_hours: int
    reminder_minutes: list[int]
    role_prefix: str


def load_config() -> Config:
    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is required and must not be empty")

    try:
        guild_id = int(os.environ["GUILD_ID"])
    except KeyError:
        raise ValueError("GUILD_ID environment variable is required")
    except (ValueError, TypeError):
        raise ValueError("GUILD_ID must be an integer")

    try:
        channel_id = int(os.environ["CHANNEL_ID"])
    except KeyError:
        raise ValueError("CHANNEL_ID environment variable is required")
    except (ValueError, TypeError):
        raise ValueError("CHANNEL_ID must be an integer")

    with open(_TOML_PATH, "rb") as f:
        toml = tomllib.load(f)

    levels = toml.get("levels", {})
    timing = toml.get("timing", {})
    roles = toml.get("roles", {})

    min_level = levels.get("min", 6)
    max_level = levels.get("max", 12)
    dark_min_level = levels.get("dark_min", 7)
    max_players = levels.get("max_players", 4)
    default_lead_minutes = timing.get("default_lead_minutes", 30)
    min_lead_minutes = timing.get("min_lead_minutes", 5)
    max_lead_hours = timing.get("max_lead_hours", 8)
    reminder_minutes = timing.get("reminder_minutes", [5, 1])
    role_prefix = roles.get("prefix", "RS")

    if min_level > max_level:
        raise ValueError(f"min_level ({min_level}) must be <= max_level ({max_level})")

    if dark_min_level < min_level:
        raise ValueError(f"dark_min_level ({dark_min_level}) must be >= min_level ({min_level})")

    if reminder_minutes != sorted(reminder_minutes, reverse=True):
        raise ValueError(f"reminder_minutes must be sorted descending, got {reminder_minutes}")

    return Config(
        token=token,
        guild_id=guild_id,
        channel_id=channel_id,
        min_level=min_level,
        max_level=max_level,
        dark_min_level=dark_min_level,
        max_players=max_players,
        default_lead_minutes=default_lead_minutes,
        min_lead_minutes=min_lead_minutes,
        max_lead_hours=max_lead_hours,
        reminder_minutes=reminder_minutes,
        role_prefix=role_prefix,
    )
