from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Run:
    id: str
    level: int
    dark: bool
    organizer_id: int
    organizer_name: str
    start_time: float
    created_at: float
    crew: list[int]
    crew_names: dict[int, str]
    message_id: int | None
    reminded: set[int]
    cancelled: bool
    _max_players: int = field(repr=False)

    @property
    def confirmed(self) -> list[int]:
        return self.crew[: self._max_players]

    @property
    def standby(self) -> list[int]:
        return self.crew[self._max_players :]

    @property
    def is_full(self) -> bool:
        return len(self.crew) >= self._max_players


class RunStore:
    def __init__(self, max_players: int) -> None:
        self._runs: dict[str, Run] = {}
        self._max_players = max_players

    def create(
        self,
        level: int,
        dark: bool,
        organizer_id: int,
        organizer_name: str,
        start_time: float,
        max_players: int,
    ) -> Run:
        run_id = uuid.uuid4().hex[:8]
        run = Run(
            id=run_id,
            level=level,
            dark=dark,
            organizer_id=organizer_id,
            organizer_name=organizer_name,
            start_time=start_time,
            created_at=time.time(),
            crew=[organizer_id],
            crew_names={organizer_id: organizer_name},
            message_id=None,
            reminded=set(),
            cancelled=False,
            _max_players=max_players,
        )
        self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def remove(self, run_id: str) -> Run | None:
        return self._runs.pop(run_id, None)

    def get_by_organizer(self, user_id: int) -> list[Run]:
        return [r for r in self._runs.values() if r.organizer_id == user_id]

    def get_by_message(self, message_id: int) -> Run | None:
        for run in self._runs.values():
            if run.message_id == message_id:
                return run
        return None

    def active_runs(self) -> list[Run]:
        return list(self._runs.values())

    def join(self, run_id: str, user_id: int, display_name: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        if user_id in run.crew:
            return False
        run.crew.append(user_id)
        run.crew_names[user_id] = display_name
        return True

    def leave(self, run_id: str, user_id: int) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        if user_id not in run.crew:
            return False
        run.crew.remove(user_id)
        run.crew_names.pop(user_id, None)
        return True

    def cleanup_expired(self, grace_minutes: int = 45) -> list[Run]:
        now = time.time()
        cutoff = grace_minutes * 60
        expired = [
            r for r in self._runs.values() if r.start_time + cutoff < now
        ]
        for run in expired:
            del self._runs[run.id]
        return expired
