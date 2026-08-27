"""Data update coordinator for Bluetti Modbus devices."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from bluetti_modbus_lib.base_devices import BluettiDevice
from modbus_connection.exceptions import ModbusError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type BluettiConfigEntry = ConfigEntry[BluettiDataUpdateCoordinator]


class BluettiDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a Bluetti device over a shared Modbus connection."""

    config_entry: BluettiConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: BluettiConfigEntry, device: BluettiDevice
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            # Bluetti's Modbus TCP stack is fragile under frequent connections -
            # a rapid burst of TCP connections during testing once made the
            # device's web interface unresponsive and required a factory
            # reset to recover. Keep this conservative.
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.device = device

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            await self.device.async_update()
        except ModbusError as err:
            # bluetti-modbus-lib already retries once on the transient
            # ACKNOWLEDGE/SERVER_DEVICE_BUSY responses this device is known
            # to occasionally return - reaching here means either a real
            # connectivity problem or a second consecutive transient one.
            # Surface it as an ordinary failed update rather than letting it
            # fall through to DataUpdateCoordinator's "unexpected exception"
            # path, which would log a full traceback for an expected,
            # recoverable condition.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="modbus_error",
                translation_placeholders={"error": str(err)},
            ) from err

        return {name: value for name, value in self.device._values.items()}
