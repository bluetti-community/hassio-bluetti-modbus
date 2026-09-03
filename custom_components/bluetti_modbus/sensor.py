"""Bluetti Modbus sensors."""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import Enum

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FullDeviceConfig, get_unique_id, pack_device_info, phase_device_info
from . import device_info as dev_info
from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    FIELDS_SHOWN_VIA_BINARY_SENSOR,
    FIELDS_SHOWN_VIA_DEVICE_INFO,
    FIELDS_SHOWN_VIA_NUMBER,
    FIELDS_SHOWN_VIA_SWITCH,
    SMETER_PHASE_FIELDS,
)
from .coordinator import PollingCoordinator
from .field_metadata import metadata_for
from .vendor.bluetti_modbus_lib import MAX_BATTERY_PACKS, PACK_INFO_FIELDS, get_device

# field name -> phase, the reverse of SMETER_PHASE_FIELDS's phase -> fields.
_PHASE_FOR_FIELD = {
    field_name: phase
    for phase, field_names in SMETER_PHASE_FIELDS.items()
    for field_name in field_names
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup sensor entities."""

    config = FullDeviceConfig.from_dict(entry.data)
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    if config is None or not isinstance(coordinator, PollingCoordinator):
        logging.getLogger(__name__).error("No coordinator found")
        return

    logger = logging.getLogger(f"{__name__}.{config.address}")

    # Generate device info
    logger.info("Creating sensors for device with address %s", config.address)
    device_info = dev_info(entry)
    # dev_info() re-parses entry.data itself; it can only return None for the
    # same "invalid data" case already ruled out by the config check above.
    assert device_info is not None

    # S Meter's per-phase fields get their own sub-device (see
    # phase_device_info()'s docstring) - built once per phase, not per field.
    phase_device_infos: dict[str, DeviceInfo] = {}
    if config.dev_type == "smeter":
        for phase in SMETER_PHASE_FIELDS:
            info = phase_device_info(hass, entry, phase)
            assert info is not None  # same guarantee as dev_info() above
            phase_device_infos[phase] = info

    # BC200 packs beyond the first get their own sub-device (see
    # pack_device_info()'s docstring and coordinator.py's
    # _async_update_battery_packs()) - Balco260 only, and only for however
    # many packs the device's own first refresh already found. Pack 1's data
    # is shown on the main device.
    pack_device_infos: dict[int, DeviceInfo] = {}
    if config.dev_type == "balco260":
        num_packs = coordinator.data.get("d_num_battery_packs")
        if isinstance(num_packs, int):
            for pack_num in range(2, min(num_packs, MAX_BATTERY_PACKS) + 1):
                info = pack_device_info(hass, entry, pack_num)
                assert info is not None  # same guarantee as dev_info() above
                pack_device_infos[pack_num] = info

    # Add sensors
    bluetti_device = get_device(config.dev_type)
    # get_device() only returns None for a dev_type it doesn't recognize -
    # config.dev_type was chosen from config_flow's fixed dropdown of known
    # types when this entry was set up, so it's always one of those.
    assert bluetti_device is not None
    sensor_fields = []
    for f in bluetti_device.get_sensors():
        if f in FIELDS_SHOWN_VIA_BINARY_SENSOR:
            continue
        if f in FIELDS_SHOWN_VIA_DEVICE_INFO:
            continue
        field = bluetti_device.get_field(f)
        # get_sensors() only yields names that are keys in this same
        # device's registered fields, so get_field() always finds them.
        assert field is not None
        # Only skip if number.py/switch.py will actually create an entity for
        # it on this device - a field in FIELDS_SHOWN_VIA_NUMBER/_SWITCH that
        # isn't writable here (e.g. EP2000 today) stays a normal read-only
        # sensor, same as before this field existed in that set at all.
        if f in FIELDS_SHOWN_VIA_NUMBER and field.writable:
            continue
        if f in FIELDS_SHOWN_VIA_SWITCH and field.writable:
            continue
        sensor_fields.append(field)

    sensors_to_add = []

    for field in sensor_fields:
        metadata = metadata_for(field.name)
        field_phase = _PHASE_FOR_FIELD.get(field.name)
        field_device_info = phase_device_infos[field_phase] if field_phase else device_info
        sensors_to_add.append(
            BluettiSensor(
                coordinator,
                field_device_info,
                field.address,
                field.name,
                unit_of_measurement=field.unit,
                category=metadata.category,
                device_class=metadata.device_class,
                state_class=metadata.state_class,
                enabled_by_default=metadata.enabled_by_default,
                logger=logger,
            )
        )

    for pack_num, pack_info in pack_device_infos.items():
        for name in PACK_INFO_FIELDS:
            # Same field object as pack 1's own instance of this field on
            # the main device - packs share the exact same schema, just at
            # a different Modbus slave address (see battery_pack()'s
            # docstring in bluetti_modbus_lib).
            field = bluetti_device.get_field(name)
            assert field is not None  # PACK_INFO_FIELDS names are Balco260 fields
            metadata = metadata_for(name)
            sensors_to_add.append(
                BluettiSensor(
                    coordinator,
                    pack_info,
                    field.address,
                    field.name,
                    unit_of_measurement=field.unit,
                    category=metadata.category,
                    device_class=metadata.device_class,
                    state_class=metadata.state_class,
                    enabled_by_default=metadata.enabled_by_default,
                    logger=logger,
                    pack_num=pack_num,
                )
            )

    async_add_entities(sensors_to_add)


class BluettiSensor(CoordinatorEntity, SensorEntity):
    """Bluetti universal sensor."""

    def __init__(
        self,
        coordinator: PollingCoordinator,
        device_info: DeviceInfo,
        address: int,
        response_key: str,
        unit_of_measurement: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        category: EntityCategory | None = None,
        options: list[str] | None = None,
        pack_num: int | None = None,
        cell_num: int | None = None,
        logger: logging.Logger | None = None,
        enabled_by_default: bool = True,
    ) -> None:
        """Init sensor entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._pack_num = pack_num
        self._cell_num = cell_num
        self._logger = logger or logging.getLogger(__name__)

        self._attr_has_entity_name = True
        e_name = f"{device_info.get('name')} {response_key}"

        if cell_num is not None:
            e_name = f"{device_info.get('name')} {response_key} {cell_num}"

        self._address = address
        self._response_key = (
            f"pack_{pack_num}_{response_key}" if pack_num else response_key
        )
        self._unavailable_counter = 0

        self._attr_device_info = device_info
        self._attr_translation_key = (
            f"pack_{response_key}" if pack_num else response_key
        )

        if cell_num is not None:
            self._attr_translation_key = f"pack_{response_key}"
            self._attr_translation_placeholders = {"cell_num": str(cell_num)}

        self._attr_available = False
        self._attr_unique_id = get_unique_id(e_name)
        self._attr_native_unit_of_measurement = unit_of_measurement
        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class
        if category is not None:
            # SensorEntity refuses to be added with entity_category CONFIG
            # (homeassistant/components/sensor/__init__.py) - it's reserved
            # for entities that can be adjusted, and this integration only
            # exposes read-only sensors today (no number/switch entities
            # for writeable registers yet). Surface config-tagged fields as
            # diagnostic instead of crashing entity registration.
            self._attr_entity_category = (
                EntityCategory.DIAGNOSTIC if category == EntityCategory.CONFIG else category
            )
        self._options = options
        self._attr_entity_registry_enabled_default = enabled_by_default

    async def async_added_to_hass(self) -> None:
        """Prime state from whatever the coordinator already has.

        CoordinatorEntity.async_added_to_hass() only registers a listener for
        FUTURE updates (confirmed against homeassistant's update_coordinator.py) -
        it never calls _handle_coordinator_update() itself. Since
        async_config_entry_first_refresh() already ran before this entity was
        created (see __init__.py), coordinator.data is already populated;
        without this, this sensor would stay unavailable (_attr_available
        starts False in __init__) until the coordinator's next scheduled
        poll, up to update_interval (30s) later.
        """
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._attr_available

    def _set_available(self) -> None:
        """Set sensor as available."""
        self._attr_available = True
        self._unavailable_counter = 0
        self._attr_extra_state_attributes = {
            "register": self._address,
        }
        self.async_write_ha_state()

    def _set_unavailable(self, cause: str = "Unknown") -> None:
        """Set sensor as unavailable."""
        self._unavailable_counter += 1

        self._attr_extra_state_attributes = {
            "register": self._address,
            "unavailable_counter": self._unavailable_counter,
            "unavailable_cause": cause,
        }

        if self._unavailable_counter >= 5:
            self._attr_available = False

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        if self.coordinator.data is None:
            self._logger.debug(
                "Data from coordinator is None",
            )
            self._set_unavailable("Data is None")
            return

        if not isinstance(self.coordinator.data, dict):
            self._logger.warning(
                "Invalid data from coordinator (sensor.%s)",
                self._attr_unique_id,
            )
            self._set_unavailable("Invalid data")
            return

        self._logger.debug(
            "Coordinator data: %s",
            self.coordinator.data,
        )

        response_data = self.coordinator.data.get(self._response_key)
        if response_data is None:
            self._logger.debug("No data for available for (%s)", self._response_key)
            self._set_unavailable("No data")
            return

        if (
            not isinstance(response_data, int)
            and not isinstance(response_data, float)
            and not isinstance(response_data, Decimal)
            and not isinstance(response_data, Enum)
            and not isinstance(response_data, str)
            and not isinstance(response_data, list)
        ):
            self._logger.warning(
                "Invalid response data type from coordinator (sensor.%s): %s has type %s",
                self._attr_unique_id,
                response_data,
                type(response_data),
            )
            self._set_unavailable("Invalid data type")
            return

        cell_num = self._cell_num
        if isinstance(response_data, list) and (
            cell_num is None or len(response_data) < cell_num
        ):
            self._set_unavailable("Invalid list length")
            return

        self._set_available()

        # Different for enum and numeric
        if isinstance(response_data, Enum):
            # Enum
            self._attr_native_value = response_data.name
        elif isinstance(response_data, list):
            assert cell_num is not None
            self._attr_native_value = response_data[cell_num - 1]
        else:
            # Numeric
            self._attr_native_value = response_data
        self.async_write_ha_state()
