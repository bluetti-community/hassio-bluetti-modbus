"""BLUETTI Modbus select entities."""

from __future__ import annotations

import logging
from enum import IntEnum

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from modbus_connection.exceptions import ModbusError

from . import FullDeviceConfig, _unique_id_for
from . import device_info as dev_info
from .const import DOMAIN, FIELDS_SHOWN_VIA_SELECT
from .coordinator import PollingCoordinator
from .sensor import _snake_case

# One write at a time: the device takes one Modbus request at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup select entities."""

    config = FullDeviceConfig.from_dict(entry.data)
    coordinator = entry.runtime_data

    if config is None or not isinstance(coordinator, PollingCoordinator):
        logging.getLogger(__name__).error("No coordinator found")
        return

    device_info = dev_info(entry)
    # dev_info() re-parses entry.data itself; it can only return None for the
    # same "invalid data" case already ruled out by the config check above.
    assert device_info is not None

    entities = []
    for field_name in FIELDS_SHOWN_VIA_SELECT:
        field = coordinator.device.get_field(field_name)
        convert = getattr(field, "convert", None)
        # Only a writable field backed by an IntEnum - its members are the
        # options, and a write needs their integer values.
        if field is not None and field.writable and isinstance(convert, type) and issubclass(convert, IntEnum):
            entities.append(BluettiSelectEntity(coordinator, device_info, field_name, convert))

    async_add_entities(entities)


class BluettiSelectEntity(CoordinatorEntity[PollingCoordinator], SelectEntity):
    """A writable BLUETTI Modbus mode register, e.g. the AC charging mode."""

    _attr_has_entity_name = True
    # No entity_category: a mode switched day to day, like the AC/DC output
    # switches, so it sits under Controls rather than Configuration.
    # No write to a mode register has been confirmed on a real unit yet (see
    # FIELDS_SHOWN_VIA_SELECT): the owner turns it on from the device page.
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: PollingCoordinator,
        device_info: DeviceInfo,
        field_name: str,
        enum_type: type[IntEnum],
    ) -> None:
        """Init select entity."""
        super().__init__(coordinator)
        self._field_name = field_name
        self._attr_device_info = device_info
        self._device_name = device_info.get("name")
        self._attr_translation_key = field_name
        self._attr_unique_id = _unique_id_for(coordinator, self._device_name, field_name, "select")
        # Options are the same snake_case keys sensor.py derives for enum
        # states, so the translations' state blocks name them.
        self._members = {_snake_case(member.name): member for member in enum_type}
        self._attr_options = list(self._members)

    async def async_added_to_hass(self) -> None:
        """Prime current_option from whatever the coordinator already has."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Write the chosen mode to the device."""
        member = self._members[option]
        try:
            await self.coordinator.async_write(self._field_name, member)
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={
                    "device": str(self._device_name),
                    "field": self._field_name,
                    "error": str(err),
                },
            ) from err
        # Optimistic, confirmed on the first poll after the device has
        # settled - same as switch.py.
        self._attr_current_option = option
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        value = data.get(self._field_name) if isinstance(data, dict) else None
        current: str | None = None
        if isinstance(value, int):
            for option, member in self._members.items():
                if member == value:
                    current = option
        self._attr_current_option = current
        self.async_write_ha_state()
