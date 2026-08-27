"""Config flow for the Bluetti Modbus integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from bluetti_modbus_lib import get_device
from modbus_connection import ModbusTcpParams
from modbus_connection.exceptions import ModbusError

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import CONF_DEVICE_TYPE, CONF_UNIT_ID, DEFAULT_PORT, DEFAULT_UNIT_ID, DEVICE_TYPES, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)),
            vol.Coerce(int),
        ),
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=247)),
            vol.Coerce(int),
        ),
        vol.Required(CONF_DEVICE_TYPE, default=DEVICE_TYPES[0]): SelectSelector(
            SelectSelectorConfig(options=DEVICE_TYPES, mode=SelectSelectorMode.DROPDOWN),
        ),
    }
)


class BluettiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Bluetti Modbus config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial connection step."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            params = ModbusTcpParams(host=user_input[CONF_HOST], port=user_input[CONF_PORT])
            device_type = user_input[CONF_DEVICE_TYPE]
            try:
                async with async_get_temporary_unit(
                    self.hass, params, user_input[CONF_UNIT_ID]
                ) as unit:
                    device = get_device(device_type, unit)
                    assert device is not None, "device_type is chosen from a fixed dropdown"
                    await device.async_update()
            except (ModbusError, HomeAssistantError) as err:
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)
            else:
                # None of the known Balco260/EP2000/SMeter registers expose a
                # device serial number (confirmed against every generated
                # device file in bluetti-modbus-lib) - unlike sofar's
                # device.serial_number, there's no stable per-device
                # identifier to key on. Falls back to host:port, which breaks
                # if the device's IP changes (e.g. no DHCP reservation) - a
                # known limitation to resolve before a real core submission.
                unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Bluetti {device_type} ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )
