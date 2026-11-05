import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import probatio
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from modbus_connection.exceptions import ModbusTimeoutError

from custom_components.bluetti_modbus import CONFIG_SCHEMA, async_setup
from custom_components.bluetti_modbus.const import DOMAIN
from custom_components.bluetti_modbus.services import (
    READ_REGISTER_SCHEMA,
    SERVICE_READ_REGISTER,
    _async_read_register,
    async_setup_services,
)

_SERVICES = "custom_components.bluetti_modbus.services"


def _entry(dev_type="balco260", values=None, error=None):
    entry = MagicMock()
    entry.title = "Balco 260"
    coordinator = entry.runtime_data
    coordinator.config.dev_type = dev_type
    coordinator.async_read_registers = AsyncMock(return_value=values, side_effect=error)
    return entry


def _call(**data):
    call = MagicMock()
    call.data = READ_REGISTER_SCHEMA({"config_entry_id": "entry_1", **data})
    return call


class TestSetup(unittest.IsolatedAsyncioTestCase):
    async def test_async_setup_registers_read_register_as_response_only(self):
        hass = MagicMock()

        self.assertTrue(await async_setup(hass, {}))

        hass.services.async_register.assert_called_once_with(
            DOMAIN,
            SERVICE_READ_REGISTER,
            _async_read_register,
            schema=READ_REGISTER_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    def test_setup_services_is_what_async_setup_calls(self):
        hass = MagicMock()

        async_setup_services(hass)

        self.assertEqual(hass.services.async_register.call_count, 1)

    def test_config_schema_accepts_no_yaml_of_its_own(self):
        self.assertEqual(CONFIG_SCHEMA({}), {})


class TestSchema(unittest.TestCase):
    def test_count_defaults_to_one(self):
        data = READ_REGISTER_SCHEMA({"config_entry_id": "entry_1", "address": "57016"})

        self.assertEqual(data["address"], 57016)
        self.assertEqual(data["count"], 1)

    def test_address_and_count_are_bounded(self):
        for data in (
            {"address": -1},
            {"address": 65536},
            {"address": 57016, "count": 0},
            {"address": 57016, "count": 126},
        ):
            with self.subTest(data=data), self.assertRaises(probatio.Invalid):
                READ_REGISTER_SCHEMA({"config_entry_id": "entry_1", **data})


class TestReadRegister(unittest.IsolatedAsyncioTestCase):
    async def _run(self, entry, **data):
        with patch(
            f"{_SERVICES}.service.async_get_config_entry", return_value=entry
        ) as get:
            call = _call(**data)
            result = await _async_read_register(call)
        get.assert_called_once_with(call.hass, DOMAIN, "entry_1")
        return result

    async def test_returns_the_raw_words(self):
        entry = _entry(values=[15, 95])

        result = await self._run(entry, address=57016, count=2)

        self.assertEqual(result, {"address": 57016, "values": [15, 95]})
        entry.runtime_data.async_read_registers.assert_awaited_once_with(57016, 2)

    async def test_refuses_an_s_meter_without_reading(self):
        entry = _entry(dev_type="smeter")

        with self.assertRaises(ServiceValidationError) as ctx:
            await self._run(entry, address=55111)

        self.assertEqual(ctx.exception.translation_key, "read_register_unsupported")
        self.assertEqual(
            ctx.exception.translation_placeholders, {"device": "Balco 260"}
        )
        entry.runtime_data.async_read_registers.assert_not_awaited()

    async def test_a_read_outside_the_profile_is_a_validation_error(self):
        entry = _entry(error=ValueError("registers 57503-57503 are outside the ranges"))

        with self.assertRaises(ServiceValidationError) as ctx:
            await self._run(entry, address=57503)

        self.assertEqual(ctx.exception.translation_key, "invalid_register_request")
        self.assertEqual(
            ctx.exception.translation_placeholders,
            {"error": "registers 57503-57503 are outside the ranges"},
        )

    async def test_a_failed_read_is_a_communication_error(self):
        entry = _entry(error=ModbusTimeoutError("no reply"))

        with self.assertRaises(HomeAssistantError) as ctx:
            await self._run(entry, address=50001)

        self.assertNotIsInstance(ctx.exception, ServiceValidationError)
        self.assertEqual(ctx.exception.translation_key, "communication_error")
        self.assertEqual(ctx.exception.translation_placeholders, {"error": "no reply"})


if __name__ == "__main__":
    unittest.main()
