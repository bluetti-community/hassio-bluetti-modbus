"""Bluetti Modbus Config Flow"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS, CONF_PORT, CONF_TYPE
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN
from .types import InitialDeviceConfig

_LOGGER = logging.getLogger(__name__)


class BluettiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Bluetti Modbus devices."""

    def __init__(self) -> None:
        _LOGGER.info("Initialize config flow")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user input."""

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            port = user_input.get(CONF_PORT, 502)
            dev_type = user_input.get(CONF_TYPE, "balco260")
            name = re.sub("[^A-Za-z0-9]+", "", address + str(port))

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

        # The input from this is not used, we use the discovered and known working address
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ADDRESS,
                ): str,
                vol.Required(
                    CONF_PORT,
                    default=502,
                ): int,
                vol.Required(
                    CONF_TYPE,
                    default="balco260",
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=["balco260", "ep2000"],
                        mode=SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )
