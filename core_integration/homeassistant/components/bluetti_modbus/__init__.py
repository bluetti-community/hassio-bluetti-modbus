"""The Bluetti Modbus integration."""

from __future__ import annotations

from bluetti_modbus_lib import get_device
from modbus_connection import ModbusTcpParams

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .const import CONF_DEVICE_TYPE, CONF_UNIT_ID, DOMAIN
from .coordinator import BluettiConfigEntry, BluettiDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BluettiConfigEntry) -> bool:
    """Set up Bluetti Modbus from a config entry."""
    try:
        unit = async_get_unit(
            hass,
            entry,
            ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT]),
            entry.data[CONF_UNIT_ID],
        )
    except HomeAssistantError as err:
        # Another config entry already holds this host/port with different
        # link settings (e.g. a different unit id) - not something retrying
        # this entry's own setup would ever resolve on its own.
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="conflicting_connection",
            translation_placeholders={"error": str(err)},
        ) from err

    device = get_device(entry.data[CONF_DEVICE_TYPE], unit)
    if device is None:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_device_type",
            translation_placeholders={"device_type": entry.data[CONF_DEVICE_TYPE]},
        )

    coordinator = BluettiDataUpdateCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_HOST])},
        name=entry.title,
        manufacturer="Bluetti",
        model=entry.data[CONF_DEVICE_TYPE],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BluettiConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
