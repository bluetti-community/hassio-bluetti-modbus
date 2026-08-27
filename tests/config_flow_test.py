import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from modbus_connection.exceptions import ModbusConnectionError

from custom_components.bluetti_modbus.config_flow import BluettiConfigFlow


def _flow() -> BluettiConfigFlow:
    return BluettiConfigFlow()


def _patched_client(read_side_effect=None):
    client = MagicMock()
    client.read = AsyncMock(side_effect=read_side_effect)
    client.aclose = AsyncMock()
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

    async def test_creates_entry_with_ip_address(self):
        flow = _flow()
        with (
            _patched_client(),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()) as set_uid,
            patch.object(flow, "_abort_if_unique_id_configured") as abort_check,
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            result = await flow.async_step_user(
                {"address": "10.2.1.60", "port": 502, "type": "balco260"}
            )

        set_uid.assert_awaited_once_with("10.2.1.60", raise_on_progress=False)
        abort_check.assert_called_once()
        self.assertEqual(create_entry.call_args.kwargs["title"], "102160502")
        self.assertEqual(
            create_entry.call_args.kwargs["data"],
            {"address": "10.2.1.60", "port": 502, "name": "102160502", "type": "balco260"},
        )
        self.assertEqual(result, "entry")

    async def test_creates_entry_with_hostname_preserves_letters(self):
        # Regression test: name used to be built with re.sub("[^A-Z0-9]+", ...),
        # which stripped every lowercase letter - a hostname like "balco.local"
        # collapsed to just the port number. Fixed to [^A-Za-z0-9]+.
        flow = _flow()
        with (
            _patched_client(),
            patch.object(flow, "async_set_unique_id", new=AsyncMock()),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_create_entry", return_value="entry") as create_entry,
        ):
            await flow.async_step_user(
                {"address": "balco.local", "port": 502, "type": "balco260"}
            )

        self.assertEqual(create_entry.call_args.kwargs["title"], "balcolocal502")

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
