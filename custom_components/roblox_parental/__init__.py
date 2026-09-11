from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import RobloxParentalClient
from .const import (
    CONF_CHILD_IDS,
    CONF_COOKIE,
    CONF_FAST_INTERVAL,
    CONF_PRESENCE_ENABLED,
    CONF_SLOW_INTERVAL,
    COORDINATOR_FAST,
    COORDINATOR_SLOW,
    DEFAULT_FAST_POLL_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import RobloxFastCoordinator, RobloxSlowCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cookie: str = entry.data[CONF_COOKIE]
    child_ids: list[int] = entry.data[CONF_CHILD_IDS]
    options = entry.options

    name_cache: dict[int, str] = {}
    client = RobloxParentalClient(cookie, name_cache=name_cache)

    slow_interval = int(options.get(CONF_SLOW_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL))
    fast_interval = int(options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_POLL_INTERVAL))
    presence_enabled = options.get(CONF_PRESENCE_ENABLED, True)

    slow_coordinator = RobloxSlowCoordinator(hass, client, child_ids, slow_interval)
    await slow_coordinator.async_config_entry_first_refresh()

    coordinators: dict = {COORDINATOR_SLOW: slow_coordinator}

    if presence_enabled:
        fast_coordinator = RobloxFastCoordinator(hass, client, child_ids, fast_interval)
        await fast_coordinator.async_config_entry_first_refresh()
        coordinators[COORDINATOR_FAST] = fast_coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators

    # Register devices for each child — use display name from slow coordinator data
    device_reg = dr.async_get(hass)
    children_info = await client.get_children()
    child_name_map = {
        int(c["userId"]): c.get("displayName", c.get("name", str(c["userId"])))
        for c in children_info
    }

    for child_id in child_ids:
        name = child_name_map.get(child_id, str(child_id))
        device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(child_id))},
            name=name,
            manufacturer="Roblox",
            model="Parental Controls",
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinators = hass.data[DOMAIN].pop(entry.entry_id, {})
        slow: RobloxSlowCoordinator | None = coordinators.get(COORDINATOR_SLOW)
        if slow:
            await slow._client.close()
    return unload_ok
