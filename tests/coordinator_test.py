import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed
from modbus_connection.exceptions import ModbusConnectionError

from custom_components.bluetti_modbus.coordinator import PollingCoordinator
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import Balco260, SMeter


def _result(name: str, value: object) -> MagicMock:
    r = MagicMock()
    r.name = name
    r.value = value
    return r


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


class TestAggregatePackSummary(unittest.IsolatedAsyncioTestCase):
    """The "Pack Summary" block (51001-51008) - only reports correctly at a
    different Modbus slave address (250) than the main device's own, see
    coordinator.py and bluetti_modbus_lib.aggregate_pack_summary()."""

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_aggregate_summary_is_read_and_merged_into_result(
        self, client_cls, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        # The main read's own (wrong, slave-1) value - overwritten below by
        # the aggregate summary's (correct, slave-250) value.
        client_cls.return_value.read = AsyncMock(
            return_value=[_result("d_num_battery_packs", 0)]
        )
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {"d_num_battery_packs": 4, "b_soc_total": 100}
        aggregate_fn.return_value = summary
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        aggregate_fn.assert_called_once_with(client_cls.return_value.conn)
        summary.async_update_with_retry.assert_awaited_once()
        self.assertEqual(result["d_num_battery_packs"], 4)
        self.assertEqual(result["b_soc_total"], 100)

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_reuses_the_same_aggregate_component_across_polls(
        self, client_cls, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {}
        aggregate_fn.return_value = summary
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        aggregate_fn.assert_called_once_with(client_cls.return_value.conn)
        self.assertEqual(summary.async_update_with_retry.await_count, 2)

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_skips_aggregate_summary_for_non_balco260_devices(
        self, client_cls, aggregate_fn
    ):
        # EP2000/S Meter's battery-pack behavior is unconfirmed on real
        # hardware - this integration's scope is Balco260 only.
        client_cls.return_value.device = MagicMock(spec=SMeter)
        client_cls.return_value.read = AsyncMock(return_value=[])
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        aggregate_fn.assert_not_called()


class TestBatteryPacks(unittest.IsolatedAsyncioTestCase):
    """Individual BC200 packs beyond the first - see coordinator.py and
    const.INDIVIDUAL_BC200_PACKS_CONFIRMED's own comment for why this stays
    disabled by default pending confirmation against real hardware."""

    def _mock_aggregate(self, aggregate_fn, num_packs: int) -> None:
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {"d_num_battery_packs": num_packs}
        aggregate_fn.return_value = summary

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_stays_disabled_by_default_even_with_packs_reported(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        # INDIVIDUAL_BC200_PACKS_CONFIRMED is False - real-hardware testing
        # found individual pack data unreliable even though the aggregate
        # count (d_num_battery_packs) is now correct.
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 4)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result["d_num_battery_packs"], 4)

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_reads_battery_packs_when_multiple_are_present(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 2)
        pack2 = MagicMock()
        pack2.async_update_with_retry = AsyncMock()
        pack2.values = {"b_soc": 77}
        battery_pack_fn.return_value = pack2
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_called_once_with(client_cls.return_value.conn, 2)
        pack2.async_update_with_retry.assert_awaited_once()
        self.assertEqual(result["pack_2_b_soc"], 77)
        self.assertNotIn("pack_1_b_soc", result)  # same slave as the main unit

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_reads_every_pack_from_2_to_num_packs(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 3)
        pack = MagicMock()
        pack.async_update_with_retry = AsyncMock()
        pack.values = {"b_soc": 50}
        battery_pack_fn.return_value = pack
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        self.assertEqual(
            [c.args[1] for c in battery_pack_fn.call_args_list],
            [2, 3],
        )

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_caps_at_max_battery_packs(self, client_cls, battery_pack_fn, aggregate_fn):
        # d_num_battery_packs reporting more than BLUETTI's own confirmed
        # maximum (5) must not be trusted past that cap.
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 16)
        pack = MagicMock()
        pack.async_update_with_retry = AsyncMock()
        pack.values = {}
        battery_pack_fn.return_value = pack
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        self.assertEqual(
            [c.args[1] for c in battery_pack_fn.call_args_list],
            [2, 3, 4, 5],
        )

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_reuses_the_same_pack_component_across_polls(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 2)
        pack = MagicMock()
        pack.async_update_with_retry = AsyncMock()
        pack.values = {"b_soc": 50}
        battery_pack_fn.return_value = pack
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        battery_pack_fn.assert_called_once_with(client_cls.return_value.conn, 2)
        self.assertEqual(pack.async_update_with_retry.await_count, 2)

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_skips_packs_for_a_single_installed_pack(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 1)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result, {"d_num_battery_packs": 1})

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_skips_packs_for_zero_installed_packs(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        self._mock_aggregate(aggregate_fn, 0)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result, {"d_num_battery_packs": 0})

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_skips_packs_when_d_num_battery_packs_is_missing(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        client_cls.return_value.device = MagicMock(spec=Balco260)
        client_cls.return_value.read = AsyncMock(return_value=[])
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {}
        aggregate_fn.return_value = summary
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result, {})

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC200_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack")
    @patch("custom_components.bluetti_modbus.coordinator.BluettiModbusClient")
    async def test_skips_packs_for_non_balco260_devices(
        self, client_cls, battery_pack_fn, aggregate_fn
    ):
        # EP2000's battery-pack behavior is unconfirmed on real hardware -
        # this integration's scope is Balco260 only for this feature.
        client_cls.return_value.device = MagicMock(spec=SMeter)
        client_cls.return_value.read = AsyncMock(
            return_value=[_result("d_num_battery_packs", 3)]
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        aggregate_fn.assert_not_called()
        self.assertEqual(result, {"d_num_battery_packs": 3})
