"""Diagnostics support for the BLUETTI Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from modbus_connection.exceptions import ModbusError

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import PollingCoordinator

# address is the device's local network IP - a diagnostics dump is meant to
# be attached to a public GitHub issue (see CONTRIBUTING.md's own
# diagnostics download steps), so this shouldn't leak a user's LAN layout
# any more than a credential would.
_TO_REDACT_ENTRY = {"address"}


def _is_serial_field(field_name: str) -> bool:
    """d_serial/d_iot_serial (main device) and b_serial/pack_N_b_serial (the
    built-in battery/BC260 packs) are the device's real BLUETTI serial
    numbers, tied to ownership/warranty - same reasoning as the address
    above, not something a diagnostics dump attached to a public issue
    should expose in the clear.
    """
    return field_name in ("d_serial", "d_iot_serial", "b_serial") or field_name.endswith(
        "_b_serial"
    )


def _serial_addresses(coordinator: PollingCoordinator) -> set[int]:
    """Every holding-register address a serial field occupies on this device.

    Derived from the device's own field declarations rather than listed by
    hand, so a raw dump redacts exactly the words the decoded snapshot
    redacts (see _is_serial_field) - whatever address/width a model
    declares its serials at. Only fields with a fixed address and count
    (the RegisterField family) can be mapped to addresses; any other kind
    of field is not a serial anyway.
    """
    addresses: set[int] = set()
    for name in coordinator.device.field_names():
        if not _is_serial_field(name):
            continue
        field = coordinator.device.get_field(name)
        address = getattr(field, "address", None)
        count = getattr(field, "count", None)
        if isinstance(address, int) and isinstance(count, int):
            addresses.update(range(address, address + count))
    return addresses


async def _raw_registers(coordinator: PollingCoordinator) -> dict[str, Any]:
    """The undecoded register words behind coordinator.data, serials redacted.

    A failed read must not fail the whole diagnostics download - the
    decoded snapshot above is still worth having, and the error itself is
    part of what a dump is for. So it lands under "error" instead.
    """
    try:
        raw = await coordinator.async_read_raw_registers()
    except (ModbusError, TimeoutError) as err:
        return {"error": f"{type(err).__name__}: {err}"}
    serials = _serial_addresses(coordinator)
    return {
        component: {
            space: {
                address: (REDACTED if address in serials else word)
                for address, word in words.items()
            }
            for space, words in spaces.items()
        }
        for component, spaces in raw.items()
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    One physical device (plus, for Balco260, its built-in battery and any
    BC260 packs - sub-devices of this same entry, see coordinator.py) per
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
        # The same registers undecoded - see async_read_raw_registers(). A
        # width/sign/word-order question about any value in "data" above
        # is answered here without another round trip to the reporter;
        # and modbus_connection's mock can load this map back as a fixture
        # (load_raw() accepts JSON's string keys since 4.12.0), so a real
        # device's dump can become a regression test verbatim.
        "raw_registers": await _raw_registers(coordinator),
    }
