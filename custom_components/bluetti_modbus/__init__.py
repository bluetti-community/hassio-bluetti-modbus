"""Bluetti Modbus Integration"""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DATA_COORDINATOR,
    DEVICE_TYPE_DISPLAY_NAMES,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import PollingCoordinator
from .types import FullDeviceConfig as FullDeviceConfig

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
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

    # Create coordinator for polling
    logger.debug("Creating coordinator")
    coordinator = PollingCoordinator(
        hass,
        entry,
        config,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id].setdefault(DATA_COORDINATOR, coordinator)

    # Registered explicitly, before the platforms below create any entity:
    # S Meter's per-phase sub-devices (see phase_device_info()) link back to
    # this device via via_device_id, which only resolves against a device
    # already in the registry - matches home-assistant/core's shelly
    # integration, which registers its own main device the same way before
    # forwarding to platforms (ShellyRpcCoordinator.async_setup()).
    main_device_info = device_info(entry)
    if main_device_info is not None:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, **main_device_info
        )

    logger.debug("Creating entities")
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    logger.debug("Setup done")

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current version.

    1 -> 2: d_timestamp (S Meter, register 55112) switched to disabled by
    default (field_metadata.py), but entity_registry_enabled_default only
    applies the first time an entity is ever registered - an entry set up
    before that change already has the entity registered as enabled, and
    nothing about bumping this integration's version changes that on its
    own (confirmed against home-assistant/core's entity_registry.py:
    async_get_or_create() only passes disabled_by down the "create" path,
    never "update"). Disable it explicitly, once, here instead - and only
    if it's still enabled, so this never fights a user who re-enables it
    themselves afterward (this whole function doesn't run again once
    entry.version reaches CURRENT_VERSION).
    """
    if entry.version == 1:
        config = FullDeviceConfig.from_dict(entry.data)
        if config is not None and config.dev_type == "smeter":
            registry = er.async_get(hass)
            unique_id = get_unique_id(f"{entry.title} d_timestamp")
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                existing = registry.async_get(entity_id)
                if existing is not None and existing.disabled_by is None:
                    registry.async_update_entity(
                        entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )

        hass.config_entries.async_update_entry(entry, version=2)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator: PollingCoordinator = data[DATA_COORDINATOR]
        await coordinator.async_shutdown()
        await coordinator.aclose()

    return unloaded


def device_info(entry: ConfigEntry) -> DeviceInfo | None:
    """Device info."""
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    return DeviceInfo(
        identifiers={(DOMAIN, config.address)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_DISPLAY_NAMES.get(config.dev_type, config.dev_type),
        # The device's own local web server, the same one Modbus TCP has to
        # be enabled through in the first place - see the README's setup
        # steps. Port 80: the Modbus port (config.port) is a different,
        # unrelated service on the same device.
        configuration_url=f"http://{config.address}",
    )


def phase_device_info(
    hass: HomeAssistant, entry: ConfigEntry, phase: str
) -> DeviceInfo | None:
    """Device info for one of S Meter's per-phase sub-devices (phase: 'a'/'b'/'c')."""
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    return DeviceInfo(
        identifiers={(DOMAIN, f"{config.address}-phase-{phase}")},
        name=f"{entry.title} Phase {phase.upper()}",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_DISPLAY_NAMES.get(config.dev_type, config.dev_type),
        # Groups this sub-device under the main S Meter device on the
        # Devices page, the same way home-assistant/core's shelly
        # integration groups its own per-channel energy-meter sub-devices
        # under one physical Shelly Pro 3EM (get_rpc_device_info() there).
        # The main device is registered explicitly in async_setup_entry()
        # above before this can ever be resolved.
        via_device_id=dr.async_get_device_id_by_identifier(
            hass, (DOMAIN, config.address), config_entry_id=entry.entry_id
        ),
    )


def get_unique_id(name: str, sensor_type: str | None = None) -> str:
    """Generate an unique id."""
    res = re.sub("[^A-Za-z0-9]+", "_", name).lower()
    if sensor_type is not None:
        return f"{sensor_type}.{res}"
    return res
