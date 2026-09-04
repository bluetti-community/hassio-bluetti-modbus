"""Bluetti Modbus switch entities."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FullDeviceConfig, get_unique_id
from . import device_info as dev_info
from .const import DATA_COORDINATOR, DOMAIN, FIELDS_SHOWN_VIA_SWITCH
from .coordinator import PollingCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup switch entities."""

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
    for field_name in FIELDS_SHOWN_VIA_SWITCH:
        field = coordinator.device.get_field(field_name)
        # Only where bluetti_modbus_lib actually marks the field writable -
        # currently Balco260 only (see that library's import.py). Not every
        # device declares every field in FIELDS_SHOWN_VIA_SWITCH at all.
        if field is not None and field.writable:
            entities.append(BluettiSwitchEntity(coordinator, device_info, field_name))

    async_add_entities(entities)


class BluettiSwitchEntity(CoordinatorEntity[PollingCoordinator], SwitchEntity):
    """A writable Bluetti Modbus register, e.g. the AC output switch."""

    _attr_has_entity_name = True
    # Generic SWITCH, not OUTLET - these control internal AC/grid relays on
    # the inverter, not a literal power outlet a user plugs something into.
    # Only sets the default icon; the user can still override it per-entity
    # (Settings -> Devices & services -> Entities -> entity -> icon) same as
    # any other HA entity, device_class or not.
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: PollingCoordinator,
        device_info: DeviceInfo,
        field_name: str,
    ) -> None:
        """Init switch entity."""
        super().__init__(coordinator)
        self._field_name = field_name
        self._attr_device_info = device_info
        self._attr_translation_key = field_name
        # entry_id prefix: two config entries for the same device type
        # default to the same title (see config_flow.py's own comment on
        # why), which without this would make every field's unique_id
        # collide across them - confirmed on real hardware, a second
        # Balco260 added with its entities all silently rejected ("does
        # not generate unique IDs") because the first already claimed
        # every one of them. entry_id is HA's own guaranteed-unique,
        # stable-for-life config entry identifier.
        e_name = f"{coordinator.config_entry.entry_id} {device_info.get('name')} {field_name}"
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

    async def async_turn_on(self, **kwargs: object) -> None:
        """Write 1 to the device."""
        await self._async_write(1)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Write 0 to the device."""
        await self._async_write(0)

    async def _async_write(self, value: int) -> None:
        await self.coordinator.device.write(self._field_name, value)
        # Optimistic - the next poll (30s) reconciles with what the device
        # actually accepted, same as every other write-capable HA entity.
        self._attr_is_on = bool(value)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if isinstance(data, dict) and isinstance(data.get(self._field_name), int):
            self._attr_is_on = bool(data[self._field_name])
        else:
            self._attr_is_on = None
        self.async_write_ha_state()
