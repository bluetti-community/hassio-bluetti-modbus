"""Coordinator for Bluetti integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .types import FullDeviceConfig
from .vendor.bluetti_modbus_lib.modbus.client import BluettiModbusClient


class PollingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polling coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        config: FullDeviceConfig,
    ):
        """Initialize coordinator."""
        super().__init__(
            hass,
            logging.getLogger(f"{__name__}.{config.address}"),
            config_entry=config_entry,
            name="Bluetti polling coordinator",
            # Bluetti's Modbus TCP stack is fragile under frequent connections -
            # a rapid burst of TCP connections during testing once made the
            # device's web interface unresponsive and required a factory
            # reset to recover. Keep this conservative.
            update_interval=timedelta(seconds=30),
        )

        self.config = config
        # One persistent client for the lifetime of this coordinator, not one
        # per poll - a fresh connection on every poll is exactly the pattern
        # that has made the device's Modbus TCP stack unresponsive under load.
        self._client = BluettiModbusClient(
            config.address,
            config.port,
            config.dev_type,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device."""
        data = await self._client.read()

        return {k: v for k, v in [[d.name, d.value] for d in data]}

    async def aclose(self) -> None:
        """Close the underlying Modbus connection."""
        await self._client.aclose()
