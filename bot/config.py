import os
from dataclasses import dataclass


def _int(key: str, default: int) -> int:
    val = os.environ.get(key, "")
    return int(val) if val else default


def _int_list(key: str, default: list[int]) -> list[int]:
    val = os.environ.get(key, "")
    if not val:
        return default
    return [int(x.strip()) for x in val.split(",")]


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int | None
    min_level: int
    max_level: int
    dark_min_level: int
    max_players: int
    dark_max_players: int
    min_lead_minutes: int
    max_lead_hours: int
    reminder_minutes: list[int]
    round_minutes: int
    role_prefix: str


def load_config() -> Config:
    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        raise ValueError("DISCORD_TOKEN is required")

    guild_id_str = os.environ.get("GUILD_ID", "")
    guild_id = int(guild_id_str) if guild_id_str else None

    min_level = _int("MIN_LEVEL", 6)
    max_level = _int("MAX_LEVEL", 12)
    dark_min_level = _int("DARK_MIN_LEVEL", 7)
    max_players = _int("MAX_PLAYERS", 4)
    dark_max_players = _int("DARK_MAX_PLAYERS", 3)
    min_lead_minutes = _int("MIN_LEAD_MINUTES", 5)
    max_lead_hours = _int("MAX_LEAD_HOURS", 8)
    reminder_minutes = _int_list("REMINDER_MINUTES", [5, 1])
    round_minutes = _int("ROUND_MINUTES", 5)
    role_prefix = os.environ.get("ROLE_PREFIX", "RS")

    if min_level > max_level:
        raise ValueError(f"MIN_LEVEL ({min_level}) must be <= MAX_LEVEL ({max_level})")

    if dark_min_level < min_level:
        raise ValueError(f"DARK_MIN_LEVEL ({dark_min_level}) must be >= MIN_LEVEL ({min_level})")

    return Config(
        token=token,
        guild_id=guild_id,
        min_level=min_level,
        max_level=max_level,
        dark_min_level=dark_min_level,
        max_players=max_players,
        dark_max_players=dark_max_players,
        min_lead_minutes=min_lead_minutes,
        max_lead_hours=max_lead_hours,
        reminder_minutes=reminder_minutes,
        round_minutes=round_minutes,
        role_prefix=role_prefix,
    )
