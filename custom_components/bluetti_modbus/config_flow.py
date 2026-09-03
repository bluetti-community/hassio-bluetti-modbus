"""Bluetti Modbus Config Flow"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_PORT, CONF_TYPE
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from modbus_connection.exceptions import ModbusError

from .const import DEVICE_TYPE_DISPLAY_NAMES, DOMAIN
from .types import InitialDeviceConfig
from .vendor.bluetti_modbus_lib.modbus.client import BluettiModbusClient

_LOGGER = logging.getLogger(__name__)


class BluettiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Bluetti Modbus devices."""

    # Bumped for the one-time d_timestamp-disable, d_serial/d_ver_arm/
    # d_ver_dsp-removal, legible-default-title, title-spacing,
    # drop-serial-from-title, switch-entities, and b_ver_1-removal
    # migrations - see __init__.py's async_migrate_entry(). Must stay in
    # sync with _CURRENT_VERSION there - this is what HA stamps a newly
    # created entry's version with.
    VERSION = 8

    def __init__(self) -> None:
        _LOGGER.info("Initialize config flow")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user input."""

        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            port = user_input.get(CONF_PORT, 502)
            dev_type = user_input.get(CONF_TYPE, "balco260")

            client = BluettiModbusClient(address, port, dev_type)
            try:
                await client.read()
            except (ModbusError, TimeoutError) as err:
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)
            finally:
                await client.aclose()

            if not errors:
                # Plain product name, matching how other integrations name a
                # single device (e.g. "SLZB-06M") - the serial number belongs
                # in DeviceInfo.serial_number (see device_info()), not
                # crammed into the display name. A user with more than one
                # device of the same type can still tell them apart via the
                # device page or by renaming one themselves.
                name = DEVICE_TYPE_DISPLAY_NAMES.get(dev_type, dev_type)

                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                data = InitialDeviceConfig(
                    address,
                    port,
                    name,
                    dev_type,
                )

                return self.async_create_entry(
                    title=name,
                    data={
                        **data.as_dict,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): TextSelector(),
                vol.Required(CONF_PORT, default=502): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
                    ),
                    vol.Coerce(int),
                ),
                vol.Required(
                    CONF_TYPE,
                    default="balco260",
                ): SelectSelector(
                    SelectSelectorConfig(
                        # Product's real names are "Balco 260" and "S Meter"
                        # (both two words) - the stored values stay
                        # "balco260"/"smeter" (match dev_type elsewhere),
                        # only the dropdown's display labels differ.
                        options=[
                            SelectOptionDict(value="balco260", label="Balco 260"),
                            SelectOptionDict(value="smeter", label="S Meter"),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )
