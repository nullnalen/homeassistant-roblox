from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CHILD_IDS, CONF_COOKIE, COORDINATOR_FAST, COORDINATOR_SLOW, DOMAIN
from .coordinator import RobloxFastCoordinator, RobloxSlowCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinators = hass.data[DOMAIN].get(entry.entry_id, {})
    slow: RobloxSlowCoordinator | None = coordinators.get(COORDINATOR_SLOW)
    fast: RobloxFastCoordinator | None = coordinators.get(COORDINATOR_FAST)

    data = dict(entry.data)
    # Redact the cookie — it is a full login token
    if CONF_COOKIE in data:
        data[CONF_COOKIE] = "**REDACTED**"

    slow_data = {}
    if slow and slow.data:
        for child_id, child_data in slow.data.items():
            slow_data[str(child_id)] = {
                "screentime_today": child_data.screentime_today,
                "screentime_week": child_data.screentime_week,
                "top_universes_count": len(child_data.top_universes),
                "blocked_universe_count": len(child_data.blocked_universe_ids),
                "daily_limit": child_data.daily_limit,
                "age_level": child_data.age_level,
                "playing_blocked": child_data.playing_blocked,
            }

    fast_data = {}
    if fast and fast.data:
        for child_id, child_data in fast.data.items():
            fast_data[str(child_id)] = {
                "online": child_data.online,
                "in_game": child_data.in_game,
                "current_game_name": child_data.current_game_name,
            }

    return {
        "entry_data": data,
        "options": dict(entry.options),
        "slow_coordinator": slow_data,
        "fast_coordinator": fast_data,
    }
