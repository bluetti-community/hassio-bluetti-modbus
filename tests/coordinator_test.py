import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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
    async def test_async_update_data_builds_client_with_config_values(self, client_cls):
        client_cls.return_value.read = AsyncMock(return_value=[])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config(), MagicMock())

        await coordinator._async_update_data()

        client_cls.assert_called_once_with("10.2.1.60", 502, "balco260")

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_async_update_data_maps_results_by_name(self, client_cls):
        r1 = MagicMock(name="d_num_inverters")
        r1.name = "d_num_inverters"
        r1.value = 1
        r2 = MagicMock(name="b_soc")
        r2.name = "b_soc"
        r2.value = 89
        client_cls.return_value.read = AsyncMock(return_value=[r1, r2])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config(), MagicMock())

        result = await coordinator._async_update_data()

        self.assertEqual(result, {"d_num_inverters": 1, "b_soc": 89})

    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_async_update_data_with_no_fields_returns_empty_dict(self, client_cls):
        client_cls.return_value.read = AsyncMock(return_value=[])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config(), MagicMock())

        result = await coordinator._async_update_data()

        self.assertEqual(result, {})
