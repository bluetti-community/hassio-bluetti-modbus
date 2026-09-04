"""Diagnostics support for the Bluetti Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import PollingCoordinator

# address is the device's local network IP - a diagnostics dump is meant to
# be attached to a public GitHub issue (see CONTRIBUTING.md's own
# diagnostics download steps), so this shouldn't leak a user's LAN layout
# any more than a credential would.
_TO_REDACT_ENTRY = {"address"}


def _is_serial_field(field_name: str) -> bool:
    """d_serial/d_iot_serial (main device) and b_serial/pack_N_b_serial (the
    built-in battery/BC200 packs) are the device's real BLUETTI serial
    numbers, tied to ownership/warranty - same reasoning as the address
    above, not something a diagnostics dump attached to a public issue
    should expose in the clear.
    """
    return field_name in ("d_serial", "d_iot_serial", "b_serial") or field_name.endswith(
        "_b_serial"
    )


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    One physical device (plus, for Balco260, its built-in battery and any
    BC200 packs - sub-devices of this same entry, see coordinator.py) per
    config entry - unlike some integrations, there's no multi-device
    aliasing to do here, just this one entry's own data. Only ever called
    while the entry is loaded (HA only offers the download button then), so
    DATA_COORDINATOR is always already set - see async_setup_entry().
    """
    coordinator: PollingCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    data = coordinator.data if isinstance(coordinator.data, dict) else {}

    return {
        "entry_data": async_redact_data(dict(entry.data), _TO_REDACT_ENTRY),
        "entry_version": entry.version,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            # The live field -> value snapshot from the device's last
            # successful Modbus read - exactly what's needed to debug "why
            # is field X missing for this model" (see CONTRIBUTING.md): this
            # integration has no dynamic per-model discovery, so a field
            # absent here means the device's own static schema
            # (bluetti_modbus_lib, generated from bluetti-registers) either
            # doesn't declare it for this model, or the read for it hasn't
            # succeeded yet.
            "data": async_redact_data(
                data, {name for name in data if _is_serial_field(name)}
            ),
        },
    }
