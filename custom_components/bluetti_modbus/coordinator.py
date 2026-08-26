"""Coordinator for Bluetti integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from bluetti_modbus_lib.modbus.client import BluettiModbusClient
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .types import FullDeviceConfig


class PollingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polling coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        config: FullDeviceConfig,
        lock: asyncio.Lock,
    ):
        """Initialize coordinator."""
        super().__init__(
            hass,
            logging.getLogger(f"{__name__}.{config.address}"),
            config_entry=config_entry,
            name="Bluetti polling coordinator",
            update_interval=timedelta(seconds=10),
        )

        self.config = config

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device."""

        # Create client
        self.logger.debug("Creating client for %s", self.config.name)
        self.logger.debug(
            "Address: %s, Port: %s, Device Type: %s",
            self.config.address,
            str(self.config.port),
            self.config.dev_type,
        )

        reader = BluettiModbusClient(
            self.config.address,
            self.config.port,
            self.config.dev_type,
        )

        data = await reader.read()

        return {k: v for k, v in [[d.name, d.value] for d in data]}
