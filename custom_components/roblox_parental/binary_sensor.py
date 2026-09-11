from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CHILD_IDS, CONF_PRESENCE_ENABLED, COORDINATOR_FAST, COORDINATOR_SLOW, DOMAIN
from .coordinator import ChildFastData, ChildSlowData, RobloxFastCoordinator, RobloxSlowCoordinator


@dataclass(frozen=True, kw_only=True)
class RobloxBinarySensorDescription(BinarySensorEntityDescription):
    coordinator_key: str = COORDINATOR_SLOW
    value_fn: Any = None
    attr_fn: Any = None


SLOW_DESCRIPTIONS: tuple[RobloxBinarySensorDescription, ...] = (
    RobloxBinarySensorDescription(
        key="over_daily_limit",
        translation_key="over_daily_limit",
        coordinator_key=COORDINATOR_SLOW,
        value_fn=lambda d: (
            d.daily_limit is not None and d.screentime_today >= d.daily_limit
        ),
    ),
    RobloxBinarySensorDescription(
        key="playing_blocked_game",
        translation_key="playing_blocked_game",
        coordinator_key=COORDINATOR_SLOW,
        value_fn=lambda d: d.playing_blocked,
    ),
)

FAST_DESCRIPTIONS: tuple[RobloxBinarySensorDescription, ...] = (
    RobloxBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        coordinator_key=COORDINATOR_FAST,
        value_fn=lambda d: d.online,
    ),
    RobloxBinarySensorDescription(
        key="in_game",
        translation_key="in_game",
        coordinator_key=COORDINATOR_FAST,
        value_fn=lambda d: d.in_game,
        attr_fn=lambda d: {"game": d.current_game_name} if d.in_game else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    slow_coordinator: RobloxSlowCoordinator = coordinators[COORDINATOR_SLOW]
    child_ids: list[int] = entry.data[CONF_CHILD_IDS]
    presence_enabled: bool = entry.options.get(CONF_PRESENCE_ENABLED, True)

    entities: list[BinarySensorEntity] = [
        RobloxSlowBinarySensor(slow_coordinator, child_id, description)
        for child_id in child_ids
        for description in SLOW_DESCRIPTIONS
    ]

    if presence_enabled and COORDINATOR_FAST in coordinators:
        fast_coordinator: RobloxFastCoordinator = coordinators[COORDINATOR_FAST]
        entities += [
            RobloxFastBinarySensor(fast_coordinator, child_id, description)
            for child_id in child_ids
            for description in FAST_DESCRIPTIONS
        ]

    async_add_entities(entities)


class RobloxSlowBinarySensor(CoordinatorEntity[RobloxSlowCoordinator], BinarySensorEntity):
    entity_description: RobloxBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RobloxSlowCoordinator,
        child_id: int,
        description: RobloxBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{child_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, str(child_id))})

    @property
    def _child_data(self) -> ChildSlowData | None:
        if self.coordinator.data:
            return self.coordinator.data.get(self._child_id)
        return None

    @property
    def is_on(self) -> bool | None:
        data = self._child_data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._child_data
        if data is None or self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(data)


class RobloxFastBinarySensor(CoordinatorEntity[RobloxFastCoordinator], BinarySensorEntity):
    entity_description: RobloxBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RobloxFastCoordinator,
        child_id: int,
        description: RobloxBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{child_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, str(child_id))})

    @property
    def _child_data(self) -> ChildFastData | None:
        if self.coordinator.data:
            return self.coordinator.data.get(self._child_id)
        return None

    @property
    def is_on(self) -> bool | None:
        data = self._child_data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._child_data
        if data is None or self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(data)
