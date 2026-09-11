from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CHILD_IDS, COORDINATOR_SLOW, DOMAIN
from .coordinator import ChildSlowData, RobloxSlowCoordinator


@dataclass(frozen=True, kw_only=True)
class RobloxSensorDescription(SensorEntityDescription):
    value_fn: Any = None
    attr_fn: Any = None


SENSOR_DESCRIPTIONS: tuple[RobloxSensorDescription, ...] = (
    RobloxSensorDescription(
        key="screentime_today",
        translation_key="screentime_today",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.screentime_today,
    ),
    RobloxSensorDescription(
        key="screentime_week",
        translation_key="screentime_week",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.screentime_week,
    ),
    RobloxSensorDescription(
        key="top_game",
        translation_key="top_game",
        value_fn=lambda d: d.top_universes[0]["name"] if d.top_universes else None,
        attr_fn=lambda d: {"games": d.top_universes},
    ),
    RobloxSensorDescription(
        key="unique_games_week",
        translation_key="unique_games_week",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.top_universes),
    ),
    RobloxSensorDescription(
        key="daily_limit",
        translation_key="daily_limit",
        native_unit_of_measurement="min",
        value_fn=lambda d: d.daily_limit,
    ),
    RobloxSensorDescription(
        key="age_level",
        translation_key="age_level",
        value_fn=lambda d: d.age_level,
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

    entities = [
        RobloxSensor(slow_coordinator, child_id, description)
        for child_id in child_ids
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class RobloxSensor(CoordinatorEntity[RobloxSlowCoordinator], SensorEntity):
    entity_description: RobloxSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RobloxSlowCoordinator,
        child_id: int,
        description: RobloxSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{child_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(child_id))},
        )

    @property
    def _child_data(self) -> ChildSlowData | None:
        if self.coordinator.data:
            return self.coordinator.data.get(self._child_id)
        return None

    @property
    def native_value(self) -> Any:
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
