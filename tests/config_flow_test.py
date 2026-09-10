import unittest
from ipaddress import ip_address
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from modbus_connection.exceptions import ModbusConnectionError

from custom_components.bluetti_modbus.config_flow import BluettiConfigFlow
from custom_components.bluetti_modbus.smeter_ws import SmeterWsInfo


def _patched_ws_query(firmware_version=None, modbus_tcp_enabled=None):
    return patch(
        "custom_components.bluetti_modbus.config_flow.async_query_smeter",
        AsyncMock(return_value=SmeterWsInfo(firmware_version, modbus_tcp_enabled)),
    )


def _flow() -> BluettiConfigFlow:
    return BluettiConfigFlow()


def _discovery_info(
    host: str = "10.2.1.80",
    name: str = "SMeter1234567890123._bluetti._tcp.local.",
) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname="smeter1234567890123.local.",
        type="_bluetti._tcp.local.",
        name=name,
        properties={},
    )


def _balco260_discovery_info(
    host: str = "10.2.1.128",
    name: str = "blhems-aabbccddeeff._bluetti._tcp.local.",
) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname="blhems-aabbccddeeff.local.",
        type="_bluetti._tcp.local.",
        name=name,
        properties={},
    )


def _patched_client(read_side_effect=None, device_values=None):
    client = MagicMock()
    client.read = AsyncMock(side_effect=read_side_effect)
    client.aclose = AsyncMock()
    client.device.values = device_values or {}
    return patch(
        "custom_components.bluetti_modbus.config_flow.BluettiModbusClient",
        return_value=client,
    )


def _type_options(data_schema):
    for key, validator in data_schema.schema.items():
        if str(key) == "type":
            return validator.config["options"]
    raise AssertionError("type field not found in the form's data_schema")


class TestConfigFlowUserStep(unittest.IsolatedAsyncioTestCase):
    async def test_no_input_shows_form(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            result = await flow.async_step_user()

        show_form.assert_called_once()
        self.assertEqual(show_form.call_args.kwargs["step_id"], "user")
        self.assertEqual(result, "form")

    async def test_ac500_offered_by_default(self):
        # AC500_CONFIRMED is True by default now - ItsMe00007 confirmed the
        # beta-line fixes working on a real AC500 inside a real HA install
        # (see that constant's own comment in const.py) and asked for AC500
        # to join the normal release line.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertIn("ac500", values)
        self.assertIn("balco260", values)
        self.assertIn("smeter", values)

    @patch("custom_components.bluetti_modbus.config_flow.AC500_CONFIRMED", False)
    async def test_ac500_not_offered_if_unconfirmed(self):
        # The flag mechanism itself still works, even though AC500_CONFIRMED
        # is True by default now - proven by patching it back to False,
        # matching BALCO500_CONFIRMED's own equivalent test below.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("ac500", values)

    async def test_balco500_not_offered_by_default(self):
        # BALCO500_CONFIRMED is False by default - see its own comment in
        # const.py. Unlike AC500, no community member has real Balco 500
        # hardware at all yet.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("balco500", values)
        self.assertIn("balco260", values)
        self.assertIn("smeter", values)

    @patch("custom_components.bluetti_modbus.config_flow.BALCO500_CONFIRMED", True)
    async def test_balco500_offered_once_confirmed(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertIn("balco500", values)

    async def test_creates_entry_titled_with_the_plain_product_name(self):
        # Regression test: the title used to have the serial number (or,
        # lacking one, the address) crammed into it. Now it's just the
        # product name, matching how other integrations name a single
        # device (e.g. "SLZB-06M") - the serial number belongs in
        # DeviceInfo.serial_number, not the display name. The device's own
        # reported data (a serial number here) must not affect the title at
        # all - device_values is set but irrelevant to what's asserted.
        flow = _flow()
        with (
            _patched_client(device_values={"d_serial": 1234567890123}),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured") as abort_check,
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            result = await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        # The device's own real serial number is preferred over the address
        # (see the flow's own comment on why) - a real d_serial reported
        # here means the address is never even reached as a fallback.
        set_uid.assert_awaited_once_with("1234567890123", raise_on_progress=False)
        abort_check.assert_called_once()
        self.assertEqual(create_entry.call_args.kwargs["title"], "Balco 260")
        self.assertEqual(
            create_entry.call_args.kwargs["data"],
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "Balco 260",
                "type": "balco260",
            },
        )
        self.assertEqual(result, "entry")

    async def test_falls_back_to_the_address_for_unique_id_when_no_serial_is_reported(
        self,
    ):
        # S Meter (no serial register at all) and any device that simply
        # hasn't reported one yet both land here - same fallback either way.
        flow = _flow()
        with (
            _patched_client(device_values={}),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry"),
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "smeter"}
            )

        set_uid.assert_awaited_once_with("10.2.1.60", raise_on_progress=False)

    async def test_aborts_for_an_address_already_configured_under_an_older_unique_id(
        self,
    ):
        # _async_abort_entries_match catches a duplicate-by-address even
        # when an *existing* entry hasn't been reconciled from its own
        # older, address-only unique_id to a serial-based one yet (see
        # _reconcile_config_entry_unique_id() in __init__.py) - plain
        # _abort_if_unique_id_configured alone wouldn't, since the two
        # would no longer match once this flow prefers the serial instead.
        flow = _flow()
        with (
            _patched_client(device_values={"d_serial": 1234567890123}),
            patch.object(flow, "_async_abort_entries_match") as abort_match,
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry"),
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        abort_match.assert_called_once_with({"address": "10.2.1.60"})

    async def test_creates_entry_titled_with_the_plain_product_name_no_serial(self):
        # S Meter has no serial number register at all (confirmed by
        # BLUETTI) - and any device could, in principle, fail to report one.
        # The title doesn't depend on that either way any more.
        flow = _flow()
        with (
            _patched_client(device_values={}),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "smeter"}
            )

        self.assertEqual(create_entry.call_args.kwargs["title"], "S Meter")

    async def test_creates_entry_titled_with_the_plain_product_name_ac500(self):
        # AC500 (bluetti_modbus_lib 0.15.0+): community-confirmed against
        # real hardware, not yet BLUETTI-support-confirmed like the other
        # two device types - selectable in the dropdown regardless.
        flow = _flow()
        with (
            _patched_client(device_values={}),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "ac500"}
            )

        self.assertEqual(create_entry.call_args.kwargs["title"], "AC500")

    async def test_defaults_port_and_type_when_missing(self):
        flow = _flow()
        with (
            _patched_client(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            await flow.async_step_user({"address": "10.2.1.60"})

        data = create_entry.call_args.kwargs["data"]
        self.assertEqual(data["port"], 502)
        self.assertEqual(data["type"], "balco260")

    async def test_connection_failure_reshows_form_with_error(self):
        flow = _flow()
        with (
            _patched_client(read_side_effect=ModbusConnectionError("no route to host")),
            patch.object(flow, "async_show_form", return_value="form") as show_form,
            patch.object(flow, "async_create_entry") as create_entry,
        ):
            result = await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        create_entry.assert_not_called()
        self.assertEqual(result, "form")
        self.assertEqual(show_form.call_args.kwargs["errors"]["base"], "cannot_connect")
        self.assertIn(
            "no route to host",
            show_form.call_args.kwargs["description_placeholders"]["error"],
        )

    async def test_connection_timeout_reshows_form_with_error(self):
        flow = _flow()
        with (
            _patched_client(read_side_effect=TimeoutError("timed out")),
            patch.object(flow, "async_show_form", return_value="form") as show_form,
            patch.object(flow, "async_create_entry") as create_entry,
        ):
            result = await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        create_entry.assert_not_called()
        self.assertEqual(result, "form")
        self.assertEqual(show_form.call_args.kwargs["errors"]["base"], "cannot_connect")

    async def test_client_is_always_closed_after_the_connectivity_check(self):
        flow = _flow()
        client = MagicMock()
        client.read = AsyncMock(side_effect=ModbusConnectionError("down"))
        client.aclose = AsyncMock()
        with (
            patch(
                "custom_components.bluetti_modbus.config_flow.BluettiModbusClient",
                return_value=client,
            ),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        client.aclose.assert_awaited_once()


class TestConfigFlowZeroconfStep(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_the_serial_from_the_mdns_name_and_shows_confirm_form(
        self,
    ):
        # "SMeter1234567890123" -> "1234567890123" - confirmed against a
        # real S Meter's own local web UI reporting that exact serial for
        # that exact mDNS instance name.
        flow = _flow()
        # The real flow manager always replaces the base class's frozen
        # default (a MappingProxyType) with a real dict before calling any
        # step - constructing the flow directly here skips that.
        flow.context = {}
        with (
            _patched_client(device_values={}),
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match") as abort_match,
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured") as abort_check,
            patch.object(flow, "async_show_form", return_value="form") as show_form,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        abort_match.assert_called_once_with({"address": "10.2.1.80"})
        set_uid.assert_awaited_once_with(
            "1234567890123", raise_on_progress=False
        )
        abort_check.assert_called_once()
        self.assertEqual(
            flow.context["title_placeholders"], {"name": "S Meter 1234567890123"}
        )
        self.assertEqual(show_form.call_args.kwargs["step_id"], "zeroconf_confirm")
        self.assertEqual(
            show_form.call_args.kwargs["description_placeholders"],
            {"name": "S Meter", "address": "10.2.1.80"},
        )
        self.assertEqual(result, "form")

    async def test_uses_the_modbus_port_not_the_advertised_web_ui_port(self):
        # The mDNS record advertises port 80 (the device's own web UI) -
        # Modbus TCP is always 502 here, deliberately not read from the
        # discovery info.
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={}) as client_cls,
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_discovery_info())

        client_cls.assert_called_once_with("10.2.1.80", 502, "smeter")

    async def test_aborts_when_modbus_does_not_respond(self):
        flow = _flow()
        with (
            _patched_client(read_side_effect=ModbusConnectionError("no route")),
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted") as async_abort,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        async_abort.assert_called_once_with(reason="cannot_connect")
        self.assertEqual(result, "aborted")

    async def test_client_is_always_closed_after_the_connectivity_check(self):
        flow = _flow()
        with (
            _patched_client(
                read_side_effect=ModbusConnectionError("down")
            ) as client_cls,
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted"),
        ):
            await flow.async_step_zeroconf(_discovery_info())

        client_cls.return_value.aclose.assert_awaited_once()

    async def test_queries_the_websocket_on_the_advertised_web_ui_port(self):
        # Not the Modbus port (502) - the WebSocket lives on the same port
        # as the device's own web UI (80, per real mDNS captures), which
        # discovery_info.port already carries.
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={}),
            patch(
                "custom_components.bluetti_modbus.config_flow.async_query_smeter",
                new=AsyncMock(return_value=SmeterWsInfo(None, None)),
            ) as query_ws,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_discovery_info())

        query_ws.assert_awaited_once_with(flow.hass, "10.2.1.80", 80)

    async def test_aborts_early_when_modbus_tcp_is_confirmed_disabled(self):
        # A best-effort WebSocket query (see smeter_ws.py) confirmed the
        # device itself reports Modbus TCP is turned off - a more specific
        # reason than the generic "cannot_connect" the Modbus attempt below
        # would otherwise produce, and no reason to even attempt it.
        flow = _flow()
        with (
            _patched_client() as client_cls,
            _patched_ws_query(modbus_tcp_enabled=False),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted") as async_abort,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        async_abort.assert_called_once_with(reason="modbus_tcp_disabled")
        client_cls.assert_not_called()
        self.assertEqual(result, "aborted")

    async def test_stores_the_firmware_version_learned_from_the_websocket_query(self):
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={}),
            _patched_ws_query(firmware_version="V300510106", modbus_tcp_enabled=True),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_discovery_info())

        self.assertEqual(flow._discovered_firmware_version, "V300510106")

    async def test_a_failed_websocket_query_does_not_block_discovery(self):
        # "Best effort": learning nothing from the WebSocket (see
        # smeter_ws.py's own docstring for why it never raises) must never
        # stop a real, working Modbus-based discovery.
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={}),
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form") as show_form,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        self.assertIsNone(flow._discovered_firmware_version)
        self.assertEqual(result, "form")
        show_form.assert_called_once()


class TestConfigFlowZeroconfRouting(unittest.IsolatedAsyncioTestCase):
    async def test_routes_a_blhems_name_to_the_balco260_flow(self):
        flow = _flow()
        with patch.object(
            flow, "_async_step_zeroconf_balco260", new=AsyncMock(return_value="balco260")
        ) as balco260_step:
            result = await flow.async_step_zeroconf(_balco260_discovery_info())

        balco260_step.assert_awaited_once()
        self.assertEqual(result, "balco260")

    async def test_routes_a_blhems_name_case_insensitively(self):
        # HA lowercases the instance name before ever matching it against
        # manifest.json's "blhems-*" pattern - confirmed real capture used
        # lowercase throughout, but this must not depend on that.
        flow = _flow()
        with patch.object(
            flow, "_async_step_zeroconf_balco260", new=AsyncMock(return_value="balco260")
        ) as balco260_step:
            await flow.async_step_zeroconf(
                _balco260_discovery_info(name="BLHEMS-AABBCCDDEEFF._bluetti._tcp.local.")
            )

        balco260_step.assert_awaited_once()

    async def test_routes_a_smeter_name_to_the_smeter_flow(self):
        flow = _flow()
        with patch.object(
            flow, "_async_step_zeroconf_smeter", new=AsyncMock(return_value="smeter")
        ) as smeter_step:
            result = await flow.async_step_zeroconf(_discovery_info())

        smeter_step.assert_awaited_once()
        self.assertEqual(result, "smeter")


class TestConfigFlowZeroconfBalco260Step(unittest.IsolatedAsyncioTestCase):
    async def test_reads_the_serial_via_modbus_and_shows_confirm_form(self):
        # Unlike S Meter, the mDNS name carries no usable identity of its
        # own here ("blhems-<MAC address>", not a serial) - the real serial
        # comes from the same Modbus read that already serves as the
        # connectivity check.
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={"d_serial": 1234567890123}),
            patch.object(flow, "_async_abort_entries_match") as abort_match,
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured") as abort_check,
            patch.object(flow, "async_show_form", return_value="form") as show_form,
        ):
            result = await flow.async_step_zeroconf(_balco260_discovery_info())

        abort_match.assert_called_once_with({"address": "10.2.1.128"})
        set_uid.assert_awaited_once_with("1234567890123", raise_on_progress=False)
        abort_check.assert_called_once()
        self.assertEqual(
            flow.context["title_placeholders"], {"name": "Balco 260 1234567890123"}
        )
        self.assertEqual(show_form.call_args.kwargs["step_id"], "zeroconf_confirm")
        self.assertEqual(
            show_form.call_args.kwargs["description_placeholders"],
            {"name": "Balco 260", "address": "10.2.1.128"},
        )
        self.assertIsNone(flow._discovered_firmware_version)
        self.assertEqual(result, "form")

    async def test_uses_the_modbus_port_not_the_advertised_web_ui_port(self):
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={"d_serial": 1234567890123}) as client_cls,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        client_cls.assert_called_once_with("10.2.1.128", 502, "balco260")

    async def test_does_not_query_the_websocket(self):
        # No independently confirmed value over what a live Modbus read
        # already provides (see _async_step_zeroconf_balco260's own
        # docstring) - and it would need authentication S Meter's own
        # equivalent doesn't, which this flow has no way to provide.
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={"d_serial": 1234567890123}),
            patch(
                "custom_components.bluetti_modbus.config_flow.async_query_smeter",
                new=AsyncMock(),
            ) as query_ws,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        query_ws.assert_not_awaited()

    async def test_aborts_when_modbus_does_not_respond(self):
        flow = _flow()
        with (
            _patched_client(read_side_effect=ModbusConnectionError("no route")),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted") as async_abort,
        ):
            result = await flow.async_step_zeroconf(_balco260_discovery_info())

        async_abort.assert_called_once_with(reason="cannot_connect")
        self.assertEqual(result, "aborted")

    async def test_aborts_for_an_address_already_configured_before_connecting(self):
        # Cheap, I/O-free dedupe happens before the Modbus attempt - same
        # ordering as the manual flow, and no reason to connect to a device
        # already configured under this address.
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={"d_serial": 1234567890123}) as client_cls,
            patch.object(flow, "_async_abort_entries_match") as abort_match,
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        abort_match.assert_called_once_with({"address": "10.2.1.128"})
        client_cls.assert_called_once()

    async def test_falls_back_to_the_host_when_no_serial_is_reported(self):
        flow = _flow()
        flow.context = {}
        with (
            _patched_client(device_values={}),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        set_uid.assert_awaited_once_with("10.2.1.128", raise_on_progress=False)

    async def test_client_is_always_closed_after_the_connectivity_check(self):
        flow = _flow()
        with (
            _patched_client(
                read_side_effect=ModbusConnectionError("down")
            ) as client_cls,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        client_cls.return_value.aclose.assert_awaited_once()


class TestConfigFlowZeroconfConfirmStep(unittest.IsolatedAsyncioTestCase):
    async def test_no_input_shows_the_confirm_form(self):
        flow = _flow()
        flow._discovered_host = "10.2.1.80"
        flow._discovered_dev_type = "smeter"
        with (
            patch.object(flow, "_set_confirm_only") as set_confirm_only,
            patch.object(flow, "async_show_form", return_value="form") as show_form,
        ):
            result = await flow.async_step_zeroconf_confirm()

        set_confirm_only.assert_called_once()
        self.assertEqual(show_form.call_args.kwargs["step_id"], "zeroconf_confirm")
        self.assertEqual(
            show_form.call_args.kwargs["description_placeholders"],
            {"name": "S Meter", "address": "10.2.1.80"},
        )
        self.assertEqual(result, "form")

    async def test_confirming_creates_the_entry(self):
        flow = _flow()
        flow._discovered_host = "10.2.1.80"
        flow._discovered_serial = "1234567890123"
        flow._discovered_dev_type = "smeter"
        with patch.object(
            flow, "async_create_entry", return_value="entry"
        ) as create_entry:
            result = await flow.async_step_zeroconf_confirm({})

        self.assertEqual(create_entry.call_args.kwargs["title"], "S Meter")
        self.assertEqual(
            create_entry.call_args.kwargs["data"],
            {
                "address": "10.2.1.80",
                "port": 502,
                "name": "S Meter",
                "type": "smeter",
                "serial": "1234567890123",
            },
        )
        self.assertEqual(result, "entry")

    async def test_confirming_includes_the_firmware_version_when_known(self):
        flow = _flow()
        flow._discovered_host = "10.2.1.80"
        flow._discovered_serial = "1234567890123"
        flow._discovered_dev_type = "smeter"
        flow._discovered_firmware_version = "V300510106"
        with patch.object(
            flow, "async_create_entry", return_value="entry"
        ) as create_entry:
            await flow.async_step_zeroconf_confirm({})

        self.assertEqual(
            create_entry.call_args.kwargs["data"]["firmware_version"], "V300510106"
        )

    async def test_confirming_a_balco260_creates_the_entry(self):
        flow = _flow()
        flow._discovered_host = "10.2.1.128"
        flow._discovered_serial = "1234567890123"
        flow._discovered_dev_type = "balco260"
        with patch.object(
            flow, "async_create_entry", return_value="entry"
        ) as create_entry:
            result = await flow.async_step_zeroconf_confirm({})

        self.assertEqual(create_entry.call_args.kwargs["title"], "Balco 260")
        self.assertEqual(
            create_entry.call_args.kwargs["data"],
            {
                "address": "10.2.1.128",
                "port": 502,
                "name": "Balco 260",
                "type": "balco260",
                "serial": "1234567890123",
            },
        )
        self.assertEqual(result, "entry")
