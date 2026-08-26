"""Bluetti Modbus sensors."""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import Enum

from bluetti_modbus_lib import get_device
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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

    # Add sensors
    bluetti_device = get_device(config.dev_type)
    sensor_fields = [bluetti_device.get_field(f) for f in bluetti_device.get_sensors()]

    sensors_to_add = []

    for field in sensor_fields:
        sensors_to_add.append(
            BluettiSensor(
                coordinator,
                device_info,
                field.address,
                field.name,
                unit_of_measurement=field.unit,
                category=getattr(field, "category", None),
                device_class=getattr(field, "device_class", None),
                state_class=getattr(field, "state_class", None),
                logger=logger,
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
        device_class: Enum | None = None,
        state_class: Enum | None = None,
        category: Enum | None = None,
        options: list[str] | None = None,
        pack_num: int | None = None,
        cell_num: int | None = None,
        logger: logging.Logger | None = None,
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
            self._attr_device_class = device_class.value
        if state_class is not None:
            self._attr_state_class = state_class.value
        if category is not None:
            self._attr_entity_category = EntityCategory(category.value)
        self._options = options

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
