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
            logging.getLogger(f"{__name__}.{config.address.replace('.', '_')}"),
            name="Bluetti polling coordinator",
            update_interval=timedelta(seconds=10),
        )

        self.config = config

        # Create client
        self.logger.info("Creating client for %s", config.name)

        self.reader = BluettiModbusClient(
            config.address,
            config.port,
            config.dev_type,
        )

    async def _async_update_data(self):
        """Fetch data from device."""

        return await self.reader.read()
