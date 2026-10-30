"""BLUETTI Modbus binary sensors."""

from __future__ import annotations

import logging

# Home Assistant 2026.10 re-exports the device class without declaring it.
from homeassistant.components.binary_sensor import (  # type: ignore[attr-defined,unused-ignore]
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FullDeviceConfig, _unique_id_for
from . import device_info as dev_info
from .coordinator import PollingCoordinator
from .network import NetworkStatusCoordinator

# Read-only: the coordinator does every read.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup binary sensor entities."""

    config = FullDeviceConfig.from_dict(entry.data)
    coordinator = entry.runtime_data

    if config is None or not isinstance(coordinator, PollingCoordinator):
        logging.getLogger(__name__).error("No coordinator found")
        return

    device_info = dev_info(entry)
    # dev_info() re-parses entry.data itself; it can only return None for the
    # same "invalid data" case already ruled out by the config check above.
    assert device_info is not None

    entities: list[BinarySensorEntity] = []
    # d_status (55111, online status) only exists on S Meter - see
    # const.py's FIELDS_SHOWN_VIA_BINARY_SENSOR.
    if config.dev_type == "smeter":
        entities.append(BluettiOnlineBinarySensor(coordinator, device_info))
    network = getattr(coordinator, "network", None)
    if isinstance(network, NetworkStatusCoordinator):
        entities.append(
            BluettiCloudConnectionBinarySensor(
                network,
                device_info,
                _unique_id_for(coordinator, device_info.get("name"), "cloud_connected", "binary_sensor"),
            )
        )
        entities.extend(
            BluettiNetworkBinarySensor(
                network,
                device_info,
                _unique_id_for(coordinator, device_info.get("name"), field, "binary_sensor"),
                field,
            )
            for field in NETWORK_FLAGS
        )
    async_add_entities(entities)


# The page's other yes/no network fields, each a diagnostic entity. Wi-Fi and
# the local network can only read "on": the page itself is reached through
# them, so they start disabled; the internet one can go off on its own.
NETWORK_FLAGS = ("wifi_connected", "lan_reachable", "wan_reachable")
_ENABLED_BY_DEFAULT = frozenset({"wan_reachable"})


class BluettiNetworkBinarySensor(
    CoordinatorEntity[NetworkStatusCoordinator], BinarySensorEntity
):
    """One yes/no field of the device's network status, from its web page."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: NetworkStatusCoordinator,
        device_info: DeviceInfo,
        unique_id: str,
        field: str,
    ) -> None:
        """Init the binary sensor."""
        super().__init__(coordinator)
        self._field = field
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._attr_translation_key = field
        self._attr_entity_registry_enabled_default = field in _ENABLED_BY_DEFAULT

    @property
    def is_on(self) -> bool | None:
        """The field's value, or unknown when the page did not say."""
        data = self.coordinator.data
        value: bool | None = getattr(data, self._field) if data else None
        return value


class BluettiCloudConnectionBinarySensor(
    CoordinatorEntity[NetworkStatusCoordinator], BinarySensorEntity
):
    """Whether the device is connected to BLUETTI's cloud, from its web page."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "cloud_connected"

    def __init__(
        self, coordinator: NetworkStatusCoordinator, device_info: DeviceInfo, unique_id: str
    ) -> None:
        """Init the binary sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id

    @property
    def is_on(self) -> bool | None:
        """Connected, or unknown when the page did not say."""
        return self.coordinator.data.cloud_connected if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, bool | None]:
        """Whether the cloud link is enabled at all on the device."""
        enabled = self.coordinator.data.cloud_enabled if self.coordinator.data else None
        return {"cloud_enabled": enabled}


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
        self._attr_unique_id = _unique_id_for(
            coordinator, device_info.get("name"), "d_status", "binary_sensor"
        )

    async def async_added_to_hass(self) -> None:
        """Prime is_on from whatever the coordinator already has.

        CoordinatorEntity.async_added_to_hass() only registers a listener for
        FUTURE updates (confirmed against homeassistant's update_coordinator.py) -
        it never calls _handle_coordinator_update() itself. Since
        async_config_entry_first_refresh() already ran before this entity was
        created (see __init__.py), coordinator.data is already populated;
        without this, is_on would stay unknown until the coordinator's next
        scheduled poll, up to update_interval (15 s) later.
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
