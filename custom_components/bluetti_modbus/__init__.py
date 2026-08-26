"""Bluetti Modbus Integration"""

from __future__ import annotations

import asyncio
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DATA_COORDINATOR,
    DATA_LOCK,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import PollingCoordinator
from .types import FullDeviceConfig

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bluetti Powerstation from a config entry."""

    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return False

    logger = logging.getLogger(f"{__name__}.{config.address}")

    logger.debug("Init Bluetti Modbus Integration")

    # Create data structure
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})

    # Create lock
    lock = asyncio.Lock()

    # Create coordinator for polling
    logger.debug("Creating coordinator")
    coordinator = PollingCoordinator(
        hass,
        entry,
        config,
        lock,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id].setdefault(DATA_COORDINATOR, coordinator)
    hass.data[DOMAIN][entry.entry_id].setdefault(DATA_LOCK, lock)

    logger.debug("Creating entities")
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    logger.debug("Setup done")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator: PollingCoordinator = data[DATA_COORDINATOR]
        await coordinator.async_shutdown()

    return unloaded


def device_info(entry: ConfigEntry):
    """Device info."""
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    return DeviceInfo(
        identifiers={(DOMAIN, config.address)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=config.dev_type,
    )


def get_unique_id(name: str, sensor_type: str | None = None):
    """Generate an unique id."""
    res = re.sub("[^A-Za-z0-9]+", "_", name).lower()
    if sensor_type is not None:
        return f"{sensor_type}.{res}"
    return res
