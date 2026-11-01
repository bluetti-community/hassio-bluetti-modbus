"""Actions for reading a device's registers directly."""

from __future__ import annotations

import probatio
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from modbus_connection.exceptions import ModbusError

from .const import DOMAIN
from .coordinator import PollingCoordinator

SERVICE_READ_REGISTER = "read_register"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ADDRESS = "address"
ATTR_COUNT = "count"

READ_REGISTER_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required(ATTR_ADDRESS): probatio.All(
            probatio.Coerce(int), probatio.Range(min=0, max=65535)
        ),
        probatio.Optional(ATTR_COUNT, default=1): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=125)
        ),
    }
)

# An S Meter serves its data only on a connection's first read, which the
# poll takes a fresh link for - a read in between would get nothing useful.
_READ_REGISTER_UNSUPPORTED_DEV_TYPES = ("smeter",)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions, once for every entry."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_REGISTER,
        _async_read_register,
        schema=READ_REGISTER_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def _async_read_register(call: ServiceCall) -> ServiceResponse:
    """Read raw holding registers inside what the device's profile reads.

    The library refuses a read outside the profile's ranges or longer than
    its max_span before anything is sent; the read itself waits its turn
    behind the poll on the entry's shared connection, at the device's own
    unit id.
    """
    entry = service.async_get_config_entry(call.hass, DOMAIN, call.data[ATTR_CONFIG_ENTRY_ID])
    coordinator: PollingCoordinator = entry.runtime_data
    address: int = call.data[ATTR_ADDRESS]
    count: int = call.data[ATTR_COUNT]
    if coordinator.config.dev_type in _READ_REGISTER_UNSUPPORTED_DEV_TYPES:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="read_register_unsupported",
            translation_placeholders={"device": entry.title},
        )
    try:
        values = await coordinator.async_read_registers(address, count)
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_register_request",
            translation_placeholders={"error": str(err)},
        ) from err
    except ModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="communication_error",
            translation_placeholders={"error": str(err)},
        ) from err
    return {"address": address, "values": list(values)}
