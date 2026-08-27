"""Bluetti Modbus sensors."""

from __future__ import annotations

from enum import Enum
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BluettiConfigEntry, BluettiDataUpdateCoordinator
from .entity import BluettiEntity
from .field_metadata import metadata_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluettiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bluetti Modbus sensors from a config entry."""
    coordinator = entry.runtime_data
    device = coordinator.device

    entities = []
    for field_name in device.get_sensors():
        field = device.get_field(field_name)
        # get_sensors() only yields names that are keys in this same
        # device's registered fields, so get_field() always finds them.
        assert field is not None
        entities.append(BluettiSensor(coordinator, field_name, field))

    async_add_entities(entities)


class BluettiSensor(BluettiEntity, SensorEntity):
    """A single Bluetti Modbus register, exposed as a sensor."""

    def __init__(
        self, coordinator: BluettiDataUpdateCoordinator, field_name: str, field: Any
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, field_name)
        self._attr_translation_key = field_name
        self._attr_native_unit_of_measurement = field.unit

        metadata = metadata_for(field_name)
        if metadata.device_class is not None:
            self._attr_device_class = metadata.device_class
        if metadata.state_class is not None:
            self._attr_state_class = metadata.state_class
        if metadata.category is not None:
            # SensorEntity refuses entity_category=CONFIG - reserved for
            # entities that can be adjusted, and this integration only
            # exposes read-only sensors so far.
            self._attr_entity_category = (
                EntityCategory.DIAGNOSTIC
                if metadata.category == EntityCategory.CONFIG
                else metadata.category
            )

        self._update_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_value()
        self.async_write_ha_state()

    def _update_value(self) -> None:
        value = self.coordinator.data.get(self._field_name)
        if isinstance(value, Enum):
            self._attr_native_value = value.name
        else:
            self._attr_native_value = value
