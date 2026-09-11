from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RobloxApiError, RobloxAuthError, RobloxParentalClient, RobloxRateLimitError
from .const import DEFAULT_FAST_POLL_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChildSlowData:
    screentime_today: int = 0
    screentime_week: int = 0
    top_universes: list[dict] = field(default_factory=list)
    blocked_universe_ids: set[int] = field(default_factory=set)
    daily_limit: int | None = None
    age_level: str | None = None
    playing_blocked: bool = False
    prev_blocked_ids: set[int] = field(default_factory=set)


@dataclass
class ChildFastData:
    online: bool = False
    in_game: bool = False
    current_game_name: str | None = None
    universe_id: int | None = None


class RobloxSlowCoordinator(DataUpdateCoordinator[dict[int, ChildSlowData]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: RobloxParentalClient,
        child_ids: list[int],
        interval_minutes: int = DEFAULT_SLOW_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_slow",
            update_interval=timedelta(minutes=interval_minutes),
        )
        self._client = client
        self._child_ids = child_ids
        self._prev_blocked: dict[int, set[int]] = {}

    async def _async_update_data(self) -> dict[int, ChildSlowData]:
        result: dict[int, ChildSlowData] = {}

        for child_id in self._child_ids:
            try:
                data = await self._fetch_child(child_id)
                result[child_id] = data
            except RobloxAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except RobloxRateLimitError:
                _LOGGER.warning("Rate limited on slow coordinator for child %s", child_id)
                if self.data and child_id in self.data:
                    result[child_id] = self.data[child_id]
            except RobloxApiError as err:
                raise UpdateFailed(f"API error for child {child_id}: {err}") from err

        return result

    async def _fetch_child(self, child_id: int) -> ChildSlowData:
        screentime_days = await self._client.get_weekly_screentime(child_id)
        today_minutes = 0
        week_minutes = 0
        for entry in screentime_days:
            mins = entry.get("minutesPlayed", 0)
            week_minutes += mins
            if entry.get("daysAgo", -1) == 0:
                today_minutes = mins

        top_universes_raw = await self._client.get_top_universes(child_id)
        universe_ids = [int(u["universeId"]) for u in top_universes_raw if "universeId" in u]
        names = await self._client.resolve_names(universe_ids)

        blocked_ids = await self._client.get_blocked(child_id)

        top_universes = [
            {
                "universe_id": int(u["universeId"]),
                "name": names.get(int(u["universeId"]), str(u["universeId"])),
                "minutes": u.get("weeklyMinutes", 0),
                "blocked": int(u["universeId"]) in blocked_ids,
            }
            for u in top_universes_raw
            if "universeId" in u
        ]

        settings = await self._client.get_child_settings(child_id)
        daily_limit = (settings.get("dailyScreenTimeLimit") or {}).get("currentValue")
        age_level = (settings.get("contentAgeRestriction") or {}).get("currentValue")

        prev = self._prev_blocked.get(child_id, set())
        playing_blocked = any(
            u["blocked"] and u["minutes"] > 0
            and int(u["universe_id"]) not in prev
            for u in top_universes
        )
        # Only flag new blocked play since last poll
        currently_blocked_with_play = {u["universe_id"] for u in top_universes if u["blocked"] and u["minutes"] > 0}
        playing_blocked = bool(currently_blocked_with_play - prev)
        self._prev_blocked[child_id] = currently_blocked_with_play

        return ChildSlowData(
            screentime_today=today_minutes,
            screentime_week=week_minutes,
            top_universes=top_universes,
            blocked_universe_ids=blocked_ids,
            daily_limit=daily_limit,
            age_level=age_level,
            playing_blocked=playing_blocked,
        )


class RobloxFastCoordinator(DataUpdateCoordinator[dict[int, ChildFastData]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: RobloxParentalClient,
        child_ids: list[int],
        interval_minutes: int = DEFAULT_FAST_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_fast",
            update_interval=timedelta(minutes=interval_minutes),
        )
        self._client = client
        self._child_ids = child_ids

    async def _async_update_data(self) -> dict[int, ChildFastData]:
        result: dict[int, ChildFastData] = {}

        for child_id in self._child_ids:
            try:
                data = await self._fetch_presence(child_id)
                result[child_id] = data
            except RobloxAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except RobloxRateLimitError:
                _LOGGER.warning("Rate limited on fast coordinator for child %s", child_id)
                if self.data and child_id in self.data:
                    result[child_id] = self.data[child_id]
            except RobloxApiError as err:
                _LOGGER.warning("Presence error for child %s: %s", child_id, err)
                result[child_id] = ChildFastData()

        return result

    async def _fetch_presence(self, child_id: int) -> ChildFastData:
        presence = await self._client.get_presence(child_id)
        presence_type = presence.get("userPresenceType", 0)
        # 0=Offline, 1=Online, 2=InGame, 3=InStudio
        online = presence_type in (1, 2, 3)
        in_game = presence_type == 2

        universe_id: int | None = None
        game_name: str | None = None

        if in_game:
            uid = presence.get("universeId")
            if uid:
                universe_id = int(uid)
                names = await self._client.resolve_names([universe_id])
                game_name = names.get(universe_id)
            else:
                game_name = presence.get("lastLocation")

        return ChildFastData(
            online=online,
            in_game=in_game,
            current_game_name=game_name,
            universe_id=universe_id,
        )
