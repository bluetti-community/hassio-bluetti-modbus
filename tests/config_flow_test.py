import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from modbus_connection.exceptions import ModbusConnectionError

from custom_components.bluetti_modbus.config_flow import BluettiConfigFlow


def _flow() -> BluettiConfigFlow:
    return BluettiConfigFlow()


def _patched_client(read_side_effect=None, device_values=None):
    client = MagicMock()
    client.read = AsyncMock(side_effect=read_side_effect)
    client.aclose = AsyncMock()
    client.device.values = device_values or {}
    return patch(
        "custom_components.bluetti_modbus.config_flow.BluettiModbusClient",
        return_value=client,
    )


class TestConfigFlowUserStep(unittest.IsolatedAsyncioTestCase):
    async def test_no_input_shows_form(self):
        flow = _flow()
        with patch.object(flow, "async_show_form", return_value="form") as show_form:
            result = await flow.async_step_user()

        show_form.assert_called_once()
        self.assertEqual(show_form.call_args.kwargs["step_id"], "user")
        self.assertEqual(result, "form")

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
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured") as abort_check,
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            result = await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        set_uid.assert_awaited_once_with("10.2.1.60", raise_on_progress=False)
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

    async def test_creates_entry_titled_with_the_plain_product_name_no_serial(self):
        # S Meter has no serial number register at all (confirmed by
        # BLUETTI) - and any device could, in principle, fail to report one.
        # The title doesn't depend on that either way any more.
        flow = _flow()
        with (
            _patched_client(device_values={}),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "smeter"}
            )

        self.assertEqual(create_entry.call_args.kwargs["title"], "S Meter")

    async def test_defaults_port_and_type_when_missing(self):
        flow = _flow()
        with (
            _patched_client(),
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
