"""Bluetti Modbus binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FullDeviceConfig, get_unique_id
from . import device_info as dev_info
from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import PollingCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup binary sensor entities."""

    config = FullDeviceConfig.from_dict(entry.data)
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    if config is None or not isinstance(coordinator, PollingCoordinator):
        logging.getLogger(__name__).error("No coordinator found")
        return

    # d_status (55111, online status) only exists on S Meter - see
    # const.py's FIELDS_SHOWN_VIA_BINARY_SENSOR.
    if config.dev_type != "smeter":
        return

    device_info = dev_info(entry)
    # dev_info() re-parses entry.data itself; it can only return None for the
    # same "invalid data" case already ruled out by the config check above.
    assert device_info is not None

    async_add_entities([BluettiOnlineBinarySensor(coordinator, device_info)])


class BluettiOnlineBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Whether S Meter reports itself online (d_status, register 55111, bit2).

    bluetti_modbus_lib decodes this to a bool already (bit_flag() in
    custom_fields.py) - protocol/register decoding belongs in that library,
    not here.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "d_status"

    def __init__(self, coordinator: PollingCoordinator, device_info: DeviceInfo) -> None:
        """Init binary sensor entity."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        # entry_id prefix: two config entries for the same device type
        # default to the same title (see config_flow.py's own comment on
        # why), which without this would make every field's unique_id
        # collide across them - confirmed on real hardware, a second
        # Balco260 added with its entities all silently rejected ("does
        # not generate unique IDs") because the first already claimed
        # every one of them. entry_id is HA's own guaranteed-unique,
        # stable-for-life config entry identifier.
        e_name = f"{coordinator.config_entry.entry_id} {device_info.get('name')} d_status"
        self._attr_unique_id = get_unique_id(e_name)

    async def async_added_to_hass(self) -> None:
        """Prime is_on from whatever the coordinator already has.

        CoordinatorEntity.async_added_to_hass() only registers a listener for
        FUTURE updates (confirmed against homeassistant's update_coordinator.py) -
        it never calls _handle_coordinator_update() itself. Since
        async_config_entry_first_refresh() already ran before this entity was
        created (see __init__.py), coordinator.data is already populated;
        without this, is_on would stay unknown until the coordinator's next
        scheduled poll, up to update_interval (30s) later.
        """
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Entity availability is CoordinatorEntity's own (coordinator.
        last_update_success) - not overridden here. d_status missing from an
        otherwise-successful update is a narrower, separate condition: is_on
        just goes back to unknown (None) rather than dragging the whole
        entity unavailable over one field.
        """
        data = self.coordinator.data
        if isinstance(data, dict) and isinstance(data.get("d_status"), bool):
            self._attr_is_on = data["d_status"]
        else:
            self._attr_is_on = None
        self.async_write_ha_state()
