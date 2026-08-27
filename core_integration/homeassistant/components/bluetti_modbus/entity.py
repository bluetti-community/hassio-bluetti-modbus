"""Base entity for Bluetti Modbus devices."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BluettiDataUpdateCoordinator


class BluettiEntity(CoordinatorEntity[BluettiDataUpdateCoordinator]):
    """Defines a base Bluetti Modbus entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BluettiDataUpdateCoordinator, field_name: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._field_name = field_name
        self._attr_translation_key = field_name
        host = coordinator.config_entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_{field_name}"
        self._attr_device_info = dr.DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def available(self) -> bool:
        """Whether this field was present in the most recent successful update."""
        return super().available and self._field_name in self.coordinator.data
