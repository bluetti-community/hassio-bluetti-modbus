"""BLUETTI Modbus Config Flow"""

from __future__ import annotations

import logging
from typing import Any

import probatio
from homeassistant import config_entries
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
from modbus_connection import ModbusTcpParams
from modbus_connection.exceptions import ModbusError

from .const import (
    AC200L_CONFIRMED,
    AC500_CONFIRMED,
    BALCO500_CONFIRMED,
    BALCOTRANS_CONFIRMED,
    DEVICE_TYPE_DISPLAY_NAMES,
    DOMAIN,
    EP500P_CONFIRMED,
    EP2000_CONFIRMED,
    FP_CONFIRMED,
    PA030_CONFIRMED,
)
from .smeter_ws import async_query_smeter
from .types import InitialDeviceConfig
from .vendor.bluetti_modbus_lib import get_device, read_values

_LOGGER = logging.getLogger(__name__)

# What a probe below can fail with: the device not answering (ModbusError,
# or a bare TimeoutError), or Home Assistant already holding a connection to
# this host and port with other link settings (HomeAssistantError).
PROBE_ERRORS = (ModbusError, TimeoutError, HomeAssistantError)


async def _async_probe(hass: HomeAssistant, host: str, port: int, dev_type: str) -> dict[str, Any]:
    """Read a device once and return its values.

    On Home Assistant's shared Modbus connection: an entry already set up for
    this device keeps its link and the probe goes through it, instead of
    opening a second one to a device that accepts very few. A link opened
    here closes again when the probe is done.
    """
    params = ModbusTcpParams(host=host, port=port)
    async with async_get_temporary_unit(hass, params, 1) as unit:
        device = get_device(dev_type, unit)
        if device is None:
            raise ValueError(f"Unsupported device type: {dev_type!r}")
        return await read_values(device)


class BluettiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for BLUETTI Modbus devices."""

    # Bumped for the one-time d_timestamp-disable, d_serial/d_ver_arm/
    # d_ver_dsp-removal, legible-default-title, title-spacing,
    # drop-serial-from-title, switch-entities, b_ver_1-removal,
    # d_iot_ver-removal, battery-sub-device, unique_id-entry_id-prefix,
    # d_serial-replaces-d_iot_serial-as-identity, fault/warning-entity-
    # removal, ac500-pv-type-disable, ac500-pv-local-disable,
    # ac500-grid/ac-local-disable, balco260-never-populated-fields and
    # slots-beyond-count and battery-firmware-slots migrations -
    # see __init__.py's async_migrate_entry(). Must stay in sync with
    # _CURRENT_VERSION there - this is what HA stamps a newly created entry's
    # version with (a fresh entry created at a stale VERSION here would
    # otherwise immediately trigger a real migration step on its very next
    # setup, for no reason).
    VERSION = 23

    def __init__(self) -> None:
        _LOGGER.info("Initialize config flow")
        # Only ever set by async_step_zeroconf, read back by
        # async_step_zeroconf_confirm - the two always run as one flow
        # instance, in that order.
        self._discovered_host: str = ""
        self._discovered_serial: str = ""
        self._discovered_dev_type: str = ""
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

            serial: object = None
            try:
                values = await _async_probe(self.hass, address, port, dev_type)
                # S Meter declares no serial-equivalent field over Modbus at
                # all (see _modbus_identity()'s own docstring) - .get()
                # simply finds nothing there, no dev_type check needed here.
                serial = values.get("d_serial")
            except PROBE_ERRORS as err:
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)

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

        data_schema = probatio.Schema(
            {
                probatio.Required(CONF_ADDRESS): TextSelector(),
                probatio.Required(CONF_PORT, default=502): probatio.All(
                    NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
                    ),
                    probatio.Coerce(int),
                ),
                probatio.Required(
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
                        # own comment. AC200L (AC200L_CONFIRMED) and EP500P
                        # (EP500P_CONFIRMED) went through the same gate and
                        # are confirmed; FP (FP_CONFIRMED) is in it, and
                        # Balcotrans (BALCOTRANS_CONFIRMED) went through it
                        # too, and PA030 (PA030_CONFIRMED) is the one in it
                        # now - read on real hardware, not yet in Home
                        # Assistant.
                        options=[
                            *(
                                [SelectOptionDict(value="ac200l", label="AC200L")]
                                if AC200L_CONFIRMED
                                else []
                            ),
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
                            *(
                                [
                                    SelectOptionDict(
                                        value="balcotrans", label="Balco Transfer Hub"
                                    )
                                ]
                                if BALCOTRANS_CONFIRMED
                                else []
                            ),
                            *(
                                [SelectOptionDict(value="ep2000", label="EP2000")]
                                if EP2000_CONFIRMED
                                else []
                            ),
                            *(
                                [SelectOptionDict(value="ep500p", label="EP500Pro")]
                                if EP500P_CONFIRMED
                                else []
                            ),
                            *(
                                [SelectOptionDict(value="fp", label="FridgePower")]
                                if FP_CONFIRMED
                                else []
                            ),
                            *(
                                [SelectOptionDict(value="pa030", label="Apex 300")]
                                if PA030_CONFIRMED
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
        """Route a zeroconf discovery to the matching device type's own flow.

        manifest.json declares three zeroconf matchers, each routing here
        for a different instance-name prefix (case-insensitive - HA
        lowercases the name before matching, see
        homeassistant/components/zeroconf/discovery.py):

        - "_bluetti._tcp" + "smeter*": an S Meter. Confirmed against real
          hardware.
        - "_http._tcp" + "bluetti hems*": a Balco260 on current firmware.
          Confirmed against real hardware via an actual mDNS browser (not
          just avahi-browse's own summary, which doesn't distinguish
          service types as clearly): it advertises under the generic
          "_http._tcp" service (shared with unrelated devices on the
          network, the same reason Shelly's own manifest.json narrows some
          of its own zeroconf matchers by name), as "Bluetti HEMS[-N]" (an
          mDNS conflict-resolution suffix may or may not be appended,
          depending on what else is on the network) - not the
          "blhems-<MAC address>" an earlier revision assumed, which was
          actually this device's own DNS *hostname* (its own
          getNetworkStatusRsp's "mdns_hostname" field, over its
          WebSocket), a different thing from the mDNS *service instance
          name* zeroconf discovery actually matches on.
        - "_bluetti._tcp" + "balco260*": a Balco260 on a future firmware.
          BLUETTI support wrote (2026-09-14) that they will "standardize
          the management of the Balco260's mDNS and try to keep it
          consistent with the S Meter": instance name "Balco260 + SN",
          service "_bluetti._tcp" instead of "_http._tcp". Declared ahead
          of that firmware so discovery keeps working the day it ships,
          without an integration update - NOT yet confirmed against real
          hardware, and the exact separator between "Balco260" and the SN
          (if any) is unknown, which is why only the prefix is relied on:
          the balco260 flow learns the serial from the device's own
          d_serial register over Modbus anyway, never from this name. The
          "_http._tcp" matcher stays for every device still on today's
          firmware.
        """
        instance_name = discovery_info.name.split(".")[0].lower()
        if instance_name.startswith(("bluetti hems", "balco260")):
            return await self._async_step_zeroconf_balco260(discovery_info)
        return await self._async_step_zeroconf_smeter(discovery_info)

    async def _async_step_zeroconf_smeter(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle an S Meter discovered via mDNS.

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
        Balco260's own equivalent (see _async_step_zeroconf_balco260). A
        confirmed-disabled Modbus TCP setting aborts early with a specific
        reason instead of the connectivity check's own generic one; any
        other outcome (including the query itself failing or timing out)
        never blocks this flow - see async_query_smeter's own docstring for
        why.
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

        try:
            await _async_probe(self.hass, host, 502, "smeter")
        except PROBE_ERRORS:
            return self.async_abort(reason="cannot_connect")

        return await self._async_zeroconf_discovered(
            host, "smeter", serial, firmware_version=ws_info.firmware_version
        )

    async def _async_step_zeroconf_balco260(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Balco260 discovered via mDNS.

        Unlike S Meter, the mDNS instance name here carries no usable
        identity of its own - "Bluetti HEMS[-N]" (confirmed against real
        hardware via Home Assistant's own network-discovery view; an
        optional "-N" suffix is ordinary mDNS conflict-resolution numbering
        when more than one such device is on the network, not part of the
        name itself) is a fixed, generic product label, not the device's
        own serial number the way S Meter's mDNS name is - and not the
        "blhems-<MAC address>" DNS *hostname* a still-unconfirmed earlier
        revision of this comment assumed either (see that device's own
        getNetworkStatusRsp, received over its WebSocket after logging in
        with its default "admin"/empty-password credentials, for where
        that string actually comes from - a real value, just answering a
        different question than "what does zeroconf discovery match on").

        That WebSocket capture's own device_info/getVersionRsp (serial
        "1234567890123", firmware "arm:V500110112,dsp:V500140110,
        bms:V500080110" for the Balco260 itself) turned out to be
        redundant, though, not a gap to fill the way it was for S Meter:
        Balco260 already declares a real d_serial Modbus register (see
        _modbus_identity()'s own docstring in __init__.py) plus
        d_ver_arm/d_ver_dsp/d_iot_ver, all already read live on every poll
        via the manual flow's own identical Modbus-based path below - a
        one-time WebSocket snapshot at add time would only ever be able to
        go stale by comparison. So this reuses that same Modbus read
        (already required here as the connectivity check itself) to learn
        the serial too, rather than adding a second, authenticated
        WebSocket round trip for information already covered better.
        """
        host = discovery_info.host

        self._async_abort_entries_match({CONF_ADDRESS: host})

        serial: object = None
        try:
            values = await _async_probe(self.hass, host, 502, "balco260")
            serial = values.get("d_serial")
        except PROBE_ERRORS:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(
            str(serial) if serial is not None else host, raise_on_progress=False
        )
        self._abort_if_unique_id_configured()

        return await self._async_zeroconf_discovered(
            host, "balco260", str(serial) if serial is not None else host
        )

    async def _async_zeroconf_discovered(
        self,
        host: str,
        dev_type: str,
        serial: str,
        *,
        firmware_version: str | None = None,
    ) -> ConfigFlowResult:
        """Stash a successful zeroconf discovery and move to confirmation."""
        name = DEVICE_TYPE_DISPLAY_NAMES.get(dev_type, dev_type)
        self._discovered_host = host
        self._discovered_serial = serial
        self._discovered_dev_type = dev_type
        self._discovered_firmware_version = firmware_version
        self.context["title_placeholders"] = {"name": f"{name} {serial}"}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm adding a zeroconf-discovered device."""
        name = DEVICE_TYPE_DISPLAY_NAMES.get(
            self._discovered_dev_type, self._discovered_dev_type
        )

        if user_input is not None:
            data = InitialDeviceConfig(
                self._discovered_host,
                502,
                name,
                self._discovered_dev_type,
                serial=self._discovered_serial,
                firmware_version=self._discovered_firmware_version,
            )
            return self.async_create_entry(
                title=name,
                data={**data.as_dict},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": name, "address": self._discovered_host},
        )
