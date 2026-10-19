import unittest
from contextlib import asynccontextmanager
from ipaddress import ip_address
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from modbus_connection import ModbusTcpParams
from modbus_connection.exceptions import ModbusConnectionError
from modbus_connection.mock import MockModbusConnection

from custom_components.bluetti_modbus.config_flow import BluettiConfigFlow, _async_probe
from custom_components.bluetti_modbus.smeter_ws import SmeterWsInfo
from custom_components.bluetti_modbus.web_page import ModbusTcpSetting


def _patched_ws_query(firmware_version=None, modbus_tcp_enabled=None, modbus_tcp_encrypted=None):
    return patch(
        "custom_components.bluetti_modbus.config_flow.async_query_smeter",
        AsyncMock(
            return_value=SmeterWsInfo(firmware_version, modbus_tcp_enabled, modbus_tcp_encrypted)
        ),
    )


def _patched_web_page(enabled=None, encrypted=None):
    return patch(
        "custom_components.bluetti_modbus.config_flow.async_query_modbus_setting",
        AsyncMock(return_value=ModbusTcpSetting(enabled, encrypted)),
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
    name: str = "Bluetti HEMS-2._http._tcp.local.",
) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname="blhems-aabbccddeeff.local.",
        type="_http._tcp.local.",
        name=name,
        properties={},
    )


def _patched_probe(read_side_effect=None, device_values=None):
    return patch(
        "custom_components.bluetti_modbus.config_flow._async_probe",
        new=AsyncMock(side_effect=read_side_effect, return_value=device_values or {}),
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

    @patch("custom_components.bluetti_modbus.config_flow.BALCO500_CONFIRMED", False)
    async def test_balco500_not_offered_if_unconfirmed(self):
        # The flag mechanism itself still works, even though
        # BALCO500_CONFIRMED is True by default now.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("balco500", values)
        self.assertIn("balco260", values)
        self.assertIn("smeter", values)

    @patch("custom_components.bluetti_modbus.config_flow.AC200L_CONFIRMED", False)
    async def test_ac200l_not_offered_if_unconfirmed(self):
        # The flag mechanism still works even though AC200L_CONFIRMED is
        # True by default now (#118) - proven by patching it back to False,
        # as for AC500.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("ac200l", values)

    async def test_ac200l_offered_by_default(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertIn("ac200l", values)

    @patch("custom_components.bluetti_modbus.config_flow.FP_CONFIRMED", False)
    async def test_fp_not_offered_if_unconfirmed(self):
        # The flag mechanism still works even though FP_CONFIRMED is True
        # by default now (hassio#127) - proven by patching it back to False.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("fp", values)

    async def test_fp_offered_by_default(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertIn("fp", values)

    @patch("custom_components.bluetti_modbus.config_flow.EP500P_CONFIRMED", False)
    async def test_ep500p_not_offered_if_unconfirmed(self):
        # The flag mechanism still works even though EP500P_CONFIRMED is
        # True by default now (bluetti-registers#35) - proven by patching
        # it back to False, as for AC500 and AC200L.
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("ep500p", values)

    async def test_ep500p_offered_by_default(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertIn("ep500p", values)

    @patch("custom_components.bluetti_modbus.config_flow.EP2000_CONFIRMED", False)
    async def test_ep2000_not_offered_if_unconfirmed(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("ep2000", values)

    async def test_ep2000_offered(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        labels = {o["value"]: o["label"] for o in options}
        self.assertEqual(labels.get("ep2000"), "EP2000")

    @patch("custom_components.bluetti_modbus.config_flow.AC240_CONFIRMED", False)
    async def test_ac240_not_offered_unless_confirmed(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("ac240", values)

    @patch("custom_components.bluetti_modbus.config_flow.AC240_CONFIRMED", True)
    async def test_ac240_offered_once_confirmed(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        labels = {o["value"]: o["label"] for o in options}
        self.assertEqual(labels.get("ac240"), "AC240")

    @patch("custom_components.bluetti_modbus.config_flow.PA030_CONFIRMED", False)
    async def test_pa030_not_offered_unless_confirmed(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        values = {o["value"] for o in options}
        self.assertNotIn("pa030", values)
        self.assertIn("balco260", values)
        self.assertIn("smeter", values)

    async def test_pa030_offered_on_the_beta_line(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_user()

        options = _type_options(show_form.call_args.kwargs["data_schema"])
        labels = {o["value"]: o["label"] for o in options}
        self.assertEqual(labels.get("pa030"), "Apex 300")

    async def test_balco500_offered_by_default(self):
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
            _patched_probe(device_values={"d_serial": 1234567890123}),
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
            _patched_probe(device_values={}),
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
            _patched_probe(device_values={"d_serial": 1234567890123}),
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
            _patched_probe(device_values={}),
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
            _patched_probe(device_values={}),
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
            _patched_probe(),
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
            _patched_probe(read_side_effect=ModbusConnectionError("no route to host")),
            _patched_web_page(),
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
            _patched_probe(read_side_effect=TimeoutError("timed out")),
            _patched_web_page(),
            patch.object(flow, "async_show_form", return_value="form") as show_form,
            patch.object(flow, "async_create_entry") as create_entry,
        ):
            result = await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        create_entry.assert_not_called()
        self.assertEqual(result, "form")
        self.assertEqual(show_form.call_args.kwargs["errors"]["base"], "cannot_connect")

    async def _failed_user_step(self, dev_type, web_page=None, smeter_query=None):
        flow = _flow()
        with (
            _patched_probe(read_side_effect=ModbusConnectionError("no route to host")),
            web_page or _patched_web_page(),
            smeter_query or _patched_ws_query(),
            patch.object(flow, "async_show_form", return_value="form") as show_form,
        ):
            await flow.async_step_user({"address": "10.2.1.60", "port": 502, "type": dev_type})
        return show_form.call_args.kwargs["errors"]["base"]

    async def test_a_balco_family_device_says_when_its_page_reports_modbus_disabled(self):
        for dev_type in ("balco260", "balco500", "balcotrans", "fp"):
            with self.subTest(dev_type=dev_type):
                error = await self._failed_user_step(
                    dev_type, web_page=_patched_web_page(enabled=False, encrypted=False)
                )
                self.assertEqual(error, "modbus_tcp_disabled")

    async def test_a_balco_family_device_says_when_its_page_reports_modbus_encrypted(self):
        error = await self._failed_user_step(
            "fp", web_page=_patched_web_page(enabled=True, encrypted=True)
        )
        self.assertEqual(error, "modbus_tcp_encrypted")

    async def test_an_ac_family_device_says_when_its_page_reports_modbus_disabled(self):
        # The AC family's page has no crypt_enable: only "disabled" can show.
        for dev_type in ("ac200l", "ac240", "ac500", "ep500p"):
            with self.subTest(dev_type=dev_type):
                error = await self._failed_user_step(
                    dev_type, web_page=_patched_web_page(enabled=False, encrypted=None)
                )
                self.assertEqual(error, "modbus_tcp_disabled")

    async def test_an_enabled_unencrypted_setting_keeps_the_generic_error(self):
        error = await self._failed_user_step(
            "balco260", web_page=_patched_web_page(enabled=True, encrypted=False)
        )
        self.assertEqual(error, "cannot_connect")

    async def test_the_page_is_asked_on_its_own_port_not_the_modbus_one(self):
        with _patched_web_page() as web_page:
            await self._failed_user_step("balco260", web_page=web_page)
        web_page.assert_awaited_once()
        self.assertEqual(web_page.await_args.args[1:], ("10.2.1.60", 80))

    async def test_an_s_meter_says_when_its_page_reports_modbus_disabled_or_encrypted(self):
        for setting, reason in (
            ((False, False), "modbus_tcp_disabled"),
            ((True, True), "modbus_tcp_encrypted"),
        ):
            with self.subTest(reason=reason):
                error = await self._failed_user_step(
                    "smeter", web_page=_patched_web_page(*setting)
                )
                self.assertEqual(error, reason)

    async def test_other_device_types_never_query_a_web_page(self):
        with _patched_web_page() as web_page, _patched_ws_query() as smeter_query:
            error = await self._failed_user_step(
                "ep2000", web_page=web_page, smeter_query=smeter_query
            )
        self.assertEqual(error, "cannot_connect")
        web_page.assert_not_awaited()
        smeter_query.assert_not_awaited()

    async def test_a_working_probe_never_queries_a_web_page(self):
        flow = _flow()
        with (
            _patched_probe(device_values={"d_serial": 1234567890123}),
            _patched_web_page() as web_page,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry"),
        ):
            await flow.async_step_user({"address": "10.2.1.60", "port": 502, "type": "fp"})
        web_page.assert_not_awaited()


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
            _patched_probe(device_values={}),
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
            _patched_probe(device_values={}) as probe,
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_discovery_info())

        probe.assert_awaited_once_with(flow.hass, "10.2.1.80", 502, "smeter")

    async def test_aborts_when_modbus_does_not_respond(self):
        flow = _flow()
        with (
            _patched_probe(read_side_effect=ModbusConnectionError("no route")),
            _patched_ws_query(),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted") as async_abort,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        async_abort.assert_called_once_with(reason="cannot_connect")
        self.assertEqual(result, "aborted")

    async def test_queries_the_websocket_on_the_advertised_web_ui_port(self):
        # Not the Modbus port (502) - the WebSocket lives on the same port
        # as the device's own web UI (80, per real mDNS captures), which
        # discovery_info.port already carries.
        flow = _flow()
        flow.context = {}
        with (
            _patched_probe(device_values={}),
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
            _patched_probe() as probe,
            _patched_ws_query(modbus_tcp_enabled=False),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted") as async_abort,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        async_abort.assert_called_once_with(reason="modbus_tcp_disabled")
        probe.assert_not_awaited()
        self.assertEqual(result, "aborted")

    async def test_aborts_early_when_modbus_tcp_is_confirmed_encrypted(self):
        flow = _flow()
        with (
            _patched_probe() as probe,
            _patched_ws_query(modbus_tcp_enabled=True, modbus_tcp_encrypted=True),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_abort", return_value="aborted") as async_abort,
        ):
            result = await flow.async_step_zeroconf(_discovery_info())

        async_abort.assert_called_once_with(reason="modbus_tcp_encrypted")
        probe.assert_not_awaited()
        self.assertEqual(result, "aborted")

    async def test_stores_the_firmware_version_learned_from_the_websocket_query(self):
        flow = _flow()
        flow.context = {}
        with (
            _patched_probe(device_values={}),
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
            _patched_probe(device_values={}),
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
    async def test_routes_a_bluetti_hems_name_to_the_balco260_flow(self):
        flow = _flow()
        with patch.object(
            flow, "_async_step_zeroconf_balco260", new=AsyncMock(return_value="balco260")
        ) as balco260_step:
            result = await flow.async_step_zeroconf(_balco260_discovery_info())

        balco260_step.assert_awaited_once()
        self.assertEqual(result, "balco260")

    async def test_routes_a_bluetti_hems_name_without_the_conflict_suffix(self):
        # The "-N" is ordinary mDNS conflict-resolution numbering, not part
        # of the name itself - a lone device on the network reports no
        # suffix at all (confirmed against real hardware).
        flow = _flow()
        with patch.object(
            flow, "_async_step_zeroconf_balco260", new=AsyncMock(return_value="balco260")
        ) as balco260_step:
            await flow.async_step_zeroconf(
                _balco260_discovery_info(name="Bluetti HEMS._http._tcp.local.")
            )

        balco260_step.assert_awaited_once()

    async def test_routes_a_bluetti_hems_name_case_insensitively(self):
        # HA lowercases the instance name before ever matching it against
        # manifest.json's "bluetti hems*" pattern - confirmed real capture
        # used mixed case ("Bluetti HEMS-2"), so this must not depend on it.
        flow = _flow()
        with patch.object(
            flow, "_async_step_zeroconf_balco260", new=AsyncMock(return_value="balco260")
        ) as balco260_step:
            await flow.async_step_zeroconf(
                _balco260_discovery_info(name="BLUETTI HEMS-2._http._tcp.local.")
            )

        balco260_step.assert_awaited_once()

    async def test_routes_a_future_balco260_bluetti_tcp_name_to_the_balco260_flow(self):
        # BLUETTI support's stated plan (2026-09-14): the Balco260 will move
        # to "_bluetti._tcp" with an S Meter-style "Balco260 + SN" instance
        # name. Unconfirmed on hardware, so the exact separator is unknown -
        # only the prefix is relied on, and a name that reaches this flow
        # under "_bluetti._tcp" must not fall through to the S Meter flow.
        for name in (
            "Balco2601234567890123._bluetti._tcp.local.",
            "Balco260-1234567890123._bluetti._tcp.local.",
            "BALCO260_1234567890123._bluetti._tcp.local.",
        ):
            with self.subTest(name=name):
                flow = _flow()
                with (
                    patch.object(
                        flow,
                        "_async_step_zeroconf_balco260",
                        new=AsyncMock(return_value="balco260"),
                    ) as balco260_step,
                    patch.object(
                        flow, "_async_step_zeroconf_smeter", new=AsyncMock()
                    ) as smeter_step,
                ):
                    await flow.async_step_zeroconf(
                        _discovery_info(host="10.2.1.128", name=name)
                    )

                balco260_step.assert_awaited_once()
                smeter_step.assert_not_awaited()

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
        # own here ("Bluetti HEMS[-N]", a fixed generic label, not a
        # serial) - the real serial comes from the same Modbus read that
        # already serves as the connectivity check.
        flow = _flow()
        flow.context = {}
        with (
            _patched_probe(device_values={"d_serial": 1234567890123}),
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
            _patched_probe(device_values={"d_serial": 1234567890123}) as probe,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        probe.assert_awaited_once_with(flow.hass, "10.2.1.128", 502, "balco260")

    async def test_a_working_probe_queries_no_web_page(self):
        # Everything this flow needs comes from the Modbus read; the page is
        # only asked when that read fails.
        flow = _flow()
        flow.context = {}
        with (
            _patched_probe(device_values={"d_serial": 1234567890123}),
            patch(
                "custom_components.bluetti_modbus.config_flow.async_query_smeter",
                new=AsyncMock(),
            ) as query_ws,
            _patched_web_page() as web_page,
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        query_ws.assert_not_awaited()
        web_page.assert_not_awaited()

    async def test_aborts_with_the_reason_its_page_reports(self):
        for setting, reason in (
            (ModbusTcpSetting(False, False), "modbus_tcp_disabled"),
            (ModbusTcpSetting(True, True), "modbus_tcp_encrypted"),
        ):
            with self.subTest(reason=reason):
                flow = _flow()
                with (
                    _patched_probe(read_side_effect=ModbusConnectionError("no route")),
                    _patched_web_page(*setting) as web_page,
                    patch.object(flow, "_async_abort_entries_match"),
                    patch.object(flow, "async_abort", return_value="aborted") as async_abort,
                ):
                    await flow.async_step_zeroconf(_balco260_discovery_info())

                async_abort.assert_called_once_with(reason=reason)
                self.assertEqual(web_page.await_args.args[1:], ("10.2.1.128", 80))

    async def test_aborts_when_modbus_does_not_respond(self):
        flow = _flow()
        with (
            _patched_probe(read_side_effect=ModbusConnectionError("no route")),
            _patched_web_page(),
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
            _patched_probe(device_values={"d_serial": 1234567890123}) as probe,
            patch.object(flow, "_async_abort_entries_match") as abort_match,
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        abort_match.assert_called_once_with({"address": "10.2.1.128"})
        probe.assert_awaited_once()

    async def test_falls_back_to_the_host_when_no_serial_is_reported(self):
        flow = _flow()
        flow.context = {}
        with (
            _patched_probe(device_values={}),
            patch.object(flow, "_async_abort_entries_match"),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_show_form", return_value="form"),
        ):
            await flow.async_step_zeroconf(_balco260_discovery_info())

        set_uid.assert_awaited_once_with("10.2.1.128", raise_on_progress=False)


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


class TestProbe(unittest.IsolatedAsyncioTestCase):
    """_async_probe(): one read on Home Assistant's shared Modbus connection."""

    def _temporary_unit(self, conn: MockModbusConnection):
        self.held: list[tuple[object, ModbusTcpParams, int]] = []
        self.released = 0

        @asynccontextmanager
        async def temporary_unit(hass, params, unit_id):
            self.held.append((hass, params, unit_id))
            try:
                yield conn.for_unit(unit_id)
            finally:
                self.released += 1

        return patch(
            "custom_components.bluetti_modbus.config_flow.async_get_temporary_unit",
            new=temporary_unit,
        )

    async def test_reads_the_device_on_a_unit_held_for_the_probe_only(self):
        conn = MockModbusConnection()
        conn.for_unit(1).holding[50001] = 2  # d_num_inverters
        hass = MagicMock()

        with self._temporary_unit(conn):
            values = await _async_probe(hass, "10.2.1.60", 502, "balco260")

        self.assertEqual(values["d_num_inverters"], 2)
        self.assertEqual(self.held, [(hass, ModbusTcpParams(host="10.2.1.60", port=502), 1)])
        self.assertEqual(self.released, 1)

    async def test_the_hold_is_released_when_the_read_fails(self):
        with (
            self._temporary_unit(MockModbusConnection()),
            patch(
                "custom_components.bluetti_modbus.config_flow.read_values",
                new=AsyncMock(side_effect=ModbusConnectionError("down")),
            ),
            self.assertRaises(ModbusConnectionError),
        ):
            await _async_probe(MagicMock(), "10.2.1.60", 502, "balco260")

        self.assertEqual(self.released, 1)

    async def test_an_unknown_device_type_is_refused(self):
        with self._temporary_unit(MockModbusConnection()), self.assertRaises(ValueError):
            await _async_probe(MagicMock(), "10.2.1.60", 502, "nope")

        self.assertEqual(self.released, 1)

    async def test_a_link_held_with_other_settings_is_a_connection_error_for_the_user(self):
        # async_get_temporary_unit raises HomeAssistantError when another
        # integration holds this host and port with other link settings.
        flow = _flow()
        with (
            _patched_probe(read_side_effect=HomeAssistantError("in use")),
            _patched_web_page(),
            patch.object(flow, "async_show_form", return_value="form") as show_form,
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        self.assertEqual(show_form.call_args.kwargs["errors"]["base"], "cannot_connect")



class TestConfigFlowReconfigureStep(unittest.IsolatedAsyncioTestCase):
    def _flow(self, entry):
        flow = _flow()
        flow.hass = MagicMock()
        patcher = patch.object(flow, "_get_reconfigure_entry", return_value=entry)
        patcher.start()
        self.addCleanup(patcher.stop)
        return flow

    def _entry(self, unique_id="1234567890123", address="10.2.1.60", dev_type="balco260"):
        return MagicMock(
            unique_id=unique_id,
            data={"address": address, "port": 502, "name": "n", "type": dev_type},
        )

    async def _submit(self, flow, address="10.2.1.61", port=502, values=None, error=None):
        with (
            _patched_probe(read_side_effect=error, device_values=values) as probe,
            patch.object(flow, "_async_abort_entries_match") as abort_match,
            patch.object(
                flow, "async_update_reload_and_abort", return_value="updated"
            ) as update,
            patch.object(flow, "async_abort", return_value="aborted") as abort,
            patch.object(flow, "async_show_form", return_value="form") as show_form,
            patch(
                "custom_components.bluetti_modbus.config_flow._async_failure_reason",
                new=AsyncMock(return_value="cannot_connect"),
            ),
        ):
            result = await flow.async_step_reconfigure({"address": address, "port": port})
        return result, probe, abort_match, update, abort, show_form

    async def test_no_input_shows_the_current_address_and_port(self):
        entry = self._entry()
        flow = self._flow(entry)
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            await flow.async_step_reconfigure()

        kwargs = show_form.call_args.kwargs
        self.assertEqual(kwargs["step_id"], "reconfigure")
        suggested = {
            str(k): k.description["suggested_value"] for k in kwargs["data_schema"].schema
        }
        self.assertEqual(suggested, {"address": "10.2.1.60", "port": 502})

    async def test_the_same_unit_at_a_new_address_moves_the_entry(self):
        entry = self._entry()
        flow = self._flow(entry)

        result, probe, abort_match, update, _, _ = await self._submit(
            flow, values={"d_serial": 1234567890123}
        )

        self.assertEqual(result, "updated")
        probe.assert_awaited_once_with(flow.hass, "10.2.1.61", 502, "balco260")
        abort_match.assert_called_once_with({"address": "10.2.1.61"})
        update.assert_called_once_with(
            entry,
            unique_id="1234567890123",
            data_updates={"address": "10.2.1.61", "port": 502},
        )

    async def test_another_unit_at_the_new_address_aborts(self):
        flow = self._flow(self._entry())

        result, _, _, update, abort, _ = await self._submit(
            flow, values={"d_serial": 9999999999999}
        )

        self.assertEqual(result, "aborted")
        abort.assert_called_once_with(reason="wrong_device")
        update.assert_not_called()

    async def test_an_entry_keyed_on_its_address_takes_the_serial(self):
        entry = self._entry(unique_id="10.2.1.60")
        flow = self._flow(entry)

        _, _, _, update, _, _ = await self._submit(flow, values={"d_serial": 1234567890123})

        self.assertEqual(update.call_args.kwargs["unique_id"], "1234567890123")

    async def test_a_unit_without_a_serial_follows_its_new_address(self):
        entry = self._entry(unique_id="10.2.1.60", dev_type="smeter")
        flow = self._flow(entry)

        _, _, _, update, _, _ = await self._submit(flow, values={})

        self.assertEqual(update.call_args.kwargs["unique_id"], "10.2.1.61")

    async def test_a_port_change_alone_skips_the_duplicate_check(self):
        flow = self._flow(self._entry())

        _, _, abort_match, update, _, _ = await self._submit(
            flow, address="10.2.1.60", port=1502, values={"d_serial": 1234567890123}
        )

        abort_match.assert_not_called()
        self.assertEqual(
            update.call_args.kwargs["data_updates"], {"address": "10.2.1.60", "port": 1502}
        )

    async def test_an_unreachable_address_shows_the_form_with_the_reason(self):
        flow = self._flow(self._entry())

        result, _, _, update, _, show_form = await self._submit(
            flow, error=ModbusConnectionError("no route to host")
        )

        self.assertEqual(result, "form")
        update.assert_not_called()
        self.assertEqual(show_form.call_args.kwargs["errors"], {"base": "cannot_connect"})
        self.assertEqual(
            show_form.call_args.kwargs["description_placeholders"], {"error": "no route to host"}
        )
