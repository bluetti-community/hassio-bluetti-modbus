import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed
from modbus_connection.exceptions import ModbusConnectionError

from custom_components.bluetti_modbus.coordinator import PollingCoordinator


def _config():
    config = MagicMock()
    config.address = "10.2.1.60"
    config.port = 502
    config.dev_type = "balco260"
    config.name = "Test Device"
    return config


class TestPollingCoordinator(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_client_is_built_once_from_config_values(self, client_cls):
        client_cls.return_value.read = AsyncMock(return_value=[])

        PollingCoordinator(MagicMock(), MagicMock(), _config())

        client_cls.assert_called_once_with("10.2.1.60", 502, "balco260")

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_repeated_updates_reuse_the_same_client(self, client_cls):
        client_cls.return_value.read = AsyncMock(return_value=[])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        # A fresh connection on every poll is exactly the pattern that has
        # made the device's Modbus TCP stack unresponsive under load.
        client_cls.assert_called_once_with("10.2.1.60", 502, "balco260")
        self.assertEqual(client_cls.return_value.read.await_count, 2)

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_async_update_data_maps_results_by_name(self, client_cls):
        r1 = MagicMock(name="d_num_inverters")
        r1.name = "d_num_inverters"
        r1.value = 1
        r2 = MagicMock(name="b_soc")
        r2.name = "b_soc"
        r2.value = 89
        client_cls.return_value.read = AsyncMock(return_value=[r1, r2])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        self.assertEqual(result, {"d_num_inverters": 1, "b_soc": 89})

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_async_update_data_with_no_fields_returns_empty_dict(self, client_cls):
        client_cls.return_value.read = AsyncMock(return_value=[])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        self.assertEqual(result, {})

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_modbus_error_becomes_update_failed(self, client_cls):
        client_cls.return_value.read = AsyncMock(
            side_effect=ModbusConnectionError("no route to host")
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_device_property_returns_the_clients_device(self, client_cls):
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        self.assertIs(coordinator.device, client_cls.return_value.device)

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_aclose_closes_the_underlying_client(self, client_cls):
        client_cls.return_value.aclose = AsyncMock()
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator.aclose()

        client_cls.return_value.aclose.assert_awaited_once()
