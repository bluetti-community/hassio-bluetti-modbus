"""Coordinator for Bluetti integration."""

from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from bluetti_modbus_lib.modbus.client import BluettiModbusClient
from .types import FullDeviceConfig


class PollingCoordinator(DataUpdateCoordinator):
    """Polling coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: FullDeviceConfig,
        lock: asyncio.Lock,
    ):
        """Initialize coordinator."""
        super().__init__(
            hass,
            logging.getLogger(f"{__name__}.{config.address}"),
            name="Bluetti polling coordinator",
            update_interval=timedelta(seconds=10),
        )

        self.config = config

    async def _async_update_data(self):
        """Fetch data from device."""

        # Create client
        self.logger.debug("Creating client for %s", self.config.name)
        self.logger.debug("Address: %s, Port: %s, Device Type: %s", self.config.address, str(self.config.port), self.config.dev_type)

        reader = BluettiModbusClient(
            self.config.address,
            self.config.port,
            self.config.dev_type,
        )

        data = await reader.read()

        return {k:v for k,v in [[d.name, d.value] for d in data]}
