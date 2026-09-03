"""Bluetti Modbus number entities."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FullDeviceConfig, get_unique_id
from . import device_info as dev_info
from .const import DATA_COORDINATOR, DOMAIN, FIELDS_SHOWN_VIA_NUMBER
from .coordinator import PollingCoordinator

# b_soc_low/b_soc_high (57016/57017): both 0-100%, matching bluetti-
# registers' own num_min/num_max for these fields - bluetti_modbus_lib's
# Range validator already enforces this at write time; this is only the
# number entity's own displayed slider/box bounds.
_MIN_VALUE = 0
_MAX_VALUE = 100


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup number entities."""

    config = FullDeviceConfig.from_dict(entry.data)
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    if config is None or not isinstance(coordinator, PollingCoordinator):
        logging.getLogger(__name__).error("No coordinator found")
        return

    device_info = dev_info(entry)
    # dev_info() re-parses entry.data itself; it can only return None for the
    # same "invalid data" case already ruled out by the config check above.
    assert device_info is not None

    entities = []
    for field_name in FIELDS_SHOWN_VIA_NUMBER:
        field = coordinator.device.get_field(field_name)
        # Only where bluetti_modbus_lib actually marks the field writable -
        # currently Balco260 only (see that library's import.py). Not every
        # device declares every field in FIELDS_SHOWN_VIA_NUMBER at all.
        if field is not None and field.writable:
            entities.append(BluettiNumberEntity(coordinator, device_info, field_name))

    async_add_entities(entities)


class BluettiNumberEntity(CoordinatorEntity[PollingCoordinator], NumberEntity):
    """A writable Bluetti Modbus register, e.g. a battery SOC threshold."""

    _attr_has_entity_name = True
    _attr_native_min_value = _MIN_VALUE
    _attr_native_max_value = _MAX_VALUE
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: PollingCoordinator,
        device_info: DeviceInfo,
        field_name: str,
    ) -> None:
        """Init number entity."""
        super().__init__(coordinator)
        self._field_name = field_name
        self._attr_device_info = device_info
        self._attr_translation_key = field_name
        e_name = f"{device_info.get('name')} {field_name}"
        self._attr_unique_id = get_unique_id(e_name)

    async def async_set_native_value(self, value: float) -> None:
        """Write the new value to the device."""
        await self.coordinator.device.write(self._field_name, int(value))
        # Optimistic - the next poll (30s) reconciles with what the device
        # actually accepted, same as every other write-capable HA entity.
        self._attr_native_value = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if isinstance(data, dict) and isinstance(data.get(self._field_name), int):
            self._attr_native_value = data[self._field_name]
        else:
            self._attr_native_value = None
        self.async_write_ha_state()
