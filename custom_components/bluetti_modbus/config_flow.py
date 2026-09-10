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
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from modbus_connection.exceptions import ModbusError

from .const import (
    AC500_CONFIRMED,
    BALCO500_CONFIRMED,
    DEVICE_TYPE_DISPLAY_NAMES,
    DOMAIN,
)
from .smeter_ws import async_query_smeter
from .types import InitialDeviceConfig
from .vendor.bluetti_modbus_lib.modbus.client import BluettiModbusClient

_LOGGER = logging.getLogger(__name__)


class BluettiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Bluetti Modbus devices."""

    # Bumped for the one-time d_timestamp-disable, d_serial/d_ver_arm/
    # d_ver_dsp-removal, legible-default-title, title-spacing,
    # drop-serial-from-title, switch-entities, b_ver_1-removal,
    # d_iot_ver-removal, battery-sub-device, unique_id-entry_id-prefix,
    # d_serial-replaces-d_iot_serial-as-identity, fault/warning-entity-
    # removal, and ac500-pv-type-disable migrations - see __init__.py's
    # async_migrate_entry(). Must stay in sync with _CURRENT_VERSION there -
    # this is what HA stamps a newly created entry's version with (a fresh
    # entry created at a stale VERSION here would otherwise immediately
    # trigger a real migration step on its very next setup, for no reason).
    VERSION = 14

    def __init__(self) -> None:
        _LOGGER.info("Initialize config flow")
        # Only ever set by async_step_zeroconf, read back by
        # async_step_zeroconf_confirm - the two always run as one flow
        # instance, in that order.
        self._discovered_host: str = ""
        self._discovered_serial: str = ""
        self._discovered_firmware_version: str | None = None

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
            serial: object = None
            try:
                await client.read()
                # S Meter declares no serial-equivalent field over Modbus at
                # all (see _modbus_identity()'s own docstring) - .get()
                # simply finds nothing there, no dev_type check needed here.
                serial = client.device.values.get("d_serial")
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

                # IP addresses are explicitly against HA's own unique_id
                # guidance (they can change - DHCP lease renewal, network
                # reconfiguration) - prefer the device's own real serial
                # number, same policy _unique_id_for() already uses at the
                # entity level. Falls back to the address for S Meter (no
                # serial available over Modbus) or if this read genuinely
                # didn't return one. _async_abort_entries_match catches a
                # duplicate-by-address even when an *existing* entry hasn't
                # been reconciled from its own older, address-only unique_id
                # yet (see _reconcile_config_entry_unique_id() in
                # __init__.py) - the two would otherwise not match.
                self._async_abort_entries_match({CONF_ADDRESS: address})
                await self.async_set_unique_id(
                    str(serial) if serial is not None else address,
                    raise_on_progress=False,
                )
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
                        #
                        # AC500 only appears here while AC500_CONFIRMED is
                        # True - see that constant's own comment in const.py
                        # for why this can't just be a version/beta-release
                        # matter. Not yet BLUETTI-support-confirmed like the
                        # other two either way (bluetti-official/bluetti-
                        # modbus-tcp-slave#5, bluetti-registers#13) - a
                        # smaller register set (no BC260 expansion-pack
                        # support yet, see bluetti_modbus_lib's own README).
                        #
                        # Balco 500 (BALCO500_CONFIRMED) is gated the same
                        # way, but entirely untested - see that constant's
                        # own comment.
                        options=[
                            *(
                                [SelectOptionDict(value="ac500", label="AC500")]
                                if AC500_CONFIRMED
                                else []
                            ),
                            SelectOptionDict(value="balco260", label="Balco 260"),
                            *(
                                [SelectOptionDict(value="balco500", label="Balco 500")]
                                if BALCO500_CONFIRMED
                                else []
                            ),
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

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle an S Meter discovered via mDNS (_bluetti._tcp).

        S Meter is the only device type that advertises this service today
        (confirmed via avahi-browse against real hardware) - manifest.json's
        zeroconf matcher ("smeter*", lowercase - HA lowercases the instance
        name before matching, see homeassistant/components/zeroconf/
        discovery.py) only ever routes here for a name that starts with the
        product line.

        The instance name is the product name immediately followed by the
        device's own real serial number, e.g. "SMeter1234567890123" -
        confirmed against a real S Meter's own local web UI ("SN:
        1234567890123" for that exact instance). S Meter has no
        serial-equivalent Modbus register at all (see
        _modbus_identity()'s docstring in __init__.py), so this mDNS name
        is the only way to learn its serial before ever connecting to it.

        The advertised port (80, the device's own web UI) is not used for
        the Modbus connectivity check below - Modbus TCP is always port 502
        here. It is used, though, for a best-effort query (see smeter_ws.py)
        against the same device's own undocumented WebSocket API - real
        hardware confirms it answers there unauthenticated, unlike
        Balco260's own equivalent. A confirmed-disabled Modbus TCP setting
        aborts early with a specific reason instead of the connectivity
        check's own generic one; any other outcome (including the query
        itself failing or timing out) never blocks this flow - see
        async_query_smeter's own docstring for why.
        """
        host = discovery_info.host
        serial = discovery_info.name.split(".")[0][len("smeter") :]

        # Catches a duplicate-by-address even against an existing entry
        # still on its own older, address-only unique_id (see
        # _reconcile_config_entry_unique_id() in __init__.py) - plain
        # _abort_if_unique_id_configured alone wouldn't, if that entry
        # hasn't been reconciled to this same serial yet.
        self._async_abort_entries_match({CONF_ADDRESS: host})
        await self.async_set_unique_id(serial, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        ws_info = await async_query_smeter(self.hass, host, discovery_info.port or 80)
        if ws_info.modbus_tcp_enabled is False:
            return self.async_abort(reason="modbus_tcp_disabled")

        client = BluettiModbusClient(host, 502, "smeter")
        try:
            await client.read()
        except (ModbusError, TimeoutError):
            return self.async_abort(reason="cannot_connect")
        finally:
            await client.aclose()

        self._discovered_host = host
        self._discovered_serial = serial
        self._discovered_firmware_version = ws_info.firmware_version
        self.context["title_placeholders"] = {"name": f"S Meter {serial}"}

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm adding a zeroconf-discovered S Meter."""
        if user_input is not None:
            data = InitialDeviceConfig(
                self._discovered_host,
                502,
                "S Meter",
                "smeter",
                serial=self._discovered_serial,
                firmware_version=self._discovered_firmware_version,
            )
            return self.async_create_entry(
                title="S Meter",
                data={**data.as_dict},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"address": self._discovered_host},
        )
