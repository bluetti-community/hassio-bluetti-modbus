import asyncio
import functools
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed
from modbus_connection import ModbusTcpParams
from modbus_connection.exceptions import ModbusConnectionError

from custom_components.bluetti_modbus.coordinator import (
    POLL_FAILURES_TOLERATED,
    READINGS_SCAN_INTERVAL,
    SETTINGS_FIRST_ADDRESS,
    SETTINGS_SCAN_INTERVAL,
    PollingCoordinator,
)
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import (
    AC500,
    Balco260,
    SMeter,
)

_COORDINATOR = "custom_components.bluetti_modbus.coordinator"


class _SharedConnection:
    """Home Assistant's shared Modbus connection, as the coordinator sees it.

    async_get_unit hands out one unit double per unit id; get_device builds
    `device` the first time (the readings device), then each of
    `extra_devices` in turn (the schema and settings of a split read plan);
    read_values polls through `read`.
    """

    def __init__(self) -> None:
        self.device: object = MagicMock()
        self.extra_devices: list[object] = []
        self.read = AsyncMock(return_value={})
        self.units: dict[int, MagicMock] = {}
        self.held: list[tuple[object, object, ModbusTcpParams, int]] = []
        self._built = False

    def get_unit(self, hass, entry, params, unit_id):
        self.held.append((hass, entry, params, unit_id))
        return self.units.setdefault(unit_id, MagicMock(unit_id=unit_id))

    def get_device(self, dev_type, unit):
        if not self._built:
            self._built = True
            return self.device
        return self.extra_devices.pop(0)

    async def read_values(self, device):
        return await self.read()


def _shared(test):
    @functools.wraps(test)
    async def wrapper(self, *mocks):
        link = _SharedConnection()
        with (
            patch(f"{_COORDINATOR}.async_get_unit", side_effect=link.get_unit),
            patch(f"{_COORDINATOR}.get_device", side_effect=link.get_device),
            patch(f"{_COORDINATOR}.read_values", side_effect=link.read_values),
        ):
            await test(self, link, *mocks)

    return wrapper


def _config():
    config = MagicMock()
    config.address = "10.2.1.60"
    config.port = 502
    config.dev_type = "balco260"
    config.name = "Test Device"
    return config


class TestPollingCoordinator(unittest.IsolatedAsyncioTestCase):
    @_shared
    async def test_unit_1_is_held_for_the_entry_on_the_devices_address(self, link):
        hass, entry = MagicMock(), MagicMock()

        PollingCoordinator(hass, entry, _config())

        self.assertEqual(
            link.held, [(hass, entry, ModbusTcpParams(host="10.2.1.60", port=502), 1)]
        )

    async def test_an_unknown_device_type_is_refused(self):
        config = _config()
        config.dev_type = "nope"
        with patch(f"{_COORDINATOR}.async_get_unit"), self.assertRaises(ValueError):
            PollingCoordinator(MagicMock(), MagicMock(), config)

    @_shared
    async def test_repeated_updates_reuse_the_same_client(self, link):
        link.read = AsyncMock(return_value={})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        # A fresh connection on every poll is exactly the pattern that has
        # made the device's Modbus TCP stack unresponsive under load.
        self.assertEqual(len(link.held), 1)
        self.assertEqual(link.read.await_count, 2)

    @_shared
    async def test_async_update_data_maps_results_by_name(self, link):
        link.read = AsyncMock(return_value={"d_num_inverters": 1, "b_soc": 89})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        self.assertEqual(result, {"d_num_inverters": 1, "b_soc": 89})

    @_shared
    async def test_async_update_data_with_no_fields_returns_empty_dict(self, link):
        link.read = AsyncMock(return_value={})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        self.assertEqual(result, {})

    @_shared
    async def test_modbus_error_becomes_update_failed(self, link):
        # No values yet (the first refresh): nothing to ride out on, the
        # failure surfaces at once so setup fails properly.
        link.read = AsyncMock(
            side_effect=ModbusConnectionError("no route to host")
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    @_shared
    async def test_a_failed_poll_keeps_the_last_values(self, link):
        # A Balco 260 fails about one poll an hour even after the library's
        # retries, and the next poll recovers: the entities keep their last
        # values instead of going unavailable for a cycle.
        link.read = AsyncMock(
            side_effect=ModbusConnectionError("Connection lost before response was received.")
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())
        coordinator.data = {"b_soc": 89}

        result = await coordinator._async_update_data()

        self.assertEqual(result, {"b_soc": 89})

    @_shared
    async def test_more_failed_polls_than_tolerated_become_update_failed(self, link):
        link.read = AsyncMock(
            side_effect=ModbusConnectionError("Connection lost before response was received.")
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())
        coordinator.data = {"b_soc": 89}

        for _ in range(POLL_FAILURES_TOLERATED):
            self.assertEqual(await coordinator._async_update_data(), {"b_soc": 89})
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    @_shared
    async def test_a_successful_poll_resets_the_tolerance(self, link):
        lost = ModbusConnectionError("Connection lost before response was received.")
        n = POLL_FAILURES_TOLERATED
        link.read = AsyncMock(
            side_effect=[lost] * n + [{"b_soc": 90}] + [lost] * (n + 1)
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())
        coordinator.data = {"b_soc": 89}

        for _ in range(n):
            await coordinator._async_update_data()
        self.assertEqual(await coordinator._async_update_data(), {"b_soc": 90})
        coordinator.data = {"b_soc": 90}
        # The full tolerance is available again before the next one raises.
        for _ in range(n):
            await coordinator._async_update_data()
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    @_shared
    async def test_device_property_returns_the_clients_device(self, link):
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        self.assertIs(coordinator.device, link.device)

    @_shared
    async def test_async_write_calls_device_write(self, link):
        link.device.write = AsyncMock()
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator.async_write("b_soc_low", 42)

        link.device.write.assert_awaited_once_with("b_soc_low", 42)

    @_shared
    async def test_write_waits_for_an_in_flight_poll_to_finish(self, link):
        # Confirmed on real hardware: a write landing while the periodic
        # poll is mid-flight can come back as ModbusProtocolError("Expected
        # response to match request") - not because the device rejects the
        # write (the official BLUETTI app shows the new value took effect
        # regardless), but because this device's Modbus TCP stack is
        # fragile under overlapping requests on the same connection.
        # Serializing every read and write through the same lock means the
        # device only ever sees one request in flight at a time.
        read_started = asyncio.Event()
        release_read = asyncio.Event()

        async def slow_read():
            read_started.set()
            await release_read.wait()
            return {}

        link.read = slow_read
        link.device.write = AsyncMock()
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        update_task = asyncio.ensure_future(coordinator._async_update_data())
        await read_started.wait()

        write_task = asyncio.ensure_future(coordinator.async_write("ac_o_switch", 1))
        await asyncio.sleep(0)
        self.assertFalse(link.device.write.called)

        release_read.set()
        await update_task
        await write_task

        link.device.write.assert_awaited_once_with("ac_o_switch", 1)


class TestReadingsAndSettingsSplit(unittest.IsolatedAsyncioTestCase):
    """The data area every cycle, the settings block on its own slower one."""

    def _coordinator(self, link):
        # The real Balco 260 profile as the readings device, so the split runs
        # on genuine addresses; the two components it builds are doubles, so
        # nothing here can reach for a connection.
        device = Balco260(None)
        link.device = device
        link.read = AsyncMock(return_value={"b_soc_total": 80})
        schema = MagicMock()
        schema.write = AsyncMock()
        settings = MagicMock()
        settings.async_update_with_retry = AsyncMock()
        settings.values = {"ac_o_switch": 1}
        settings.get_field.side_effect = lambda name: (
            MagicMock() if name == "ac_o_switch" else None
        )
        link.extra_devices = [schema, settings]
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())
        return coordinator, device, schema, settings

    def test_the_intervals_are_fifteen_and_sixty_seconds(self):
        self.assertEqual(READINGS_SCAN_INTERVAL.total_seconds(), 15)
        self.assertEqual(SETTINGS_SCAN_INTERVAL.total_seconds(), 60)

    def test_reading_faster_keeps_the_ninety_second_grace_period(self):
        # The tolerance is a time budget, not a poll count: stale values are
        # kept for 90 s before entities go unavailable, as at 30 s with two
        # tolerated failures. Halving the interval must not halve that.
        grace = (POLL_FAILURES_TOLERATED + 1) * READINGS_SCAN_INTERVAL.total_seconds()
        self.assertEqual(grace, 90)

    @_shared
    async def test_the_settings_block_leaves_the_every_cycle_read(self, link):
        coordinator, device, schema, settings = self._coordinator(link)

        self.assertEqual(coordinator.update_interval, READINGS_SCAN_INTERVAL)
        # What every cycle reads: no field from 57001 up is left in it.
        polled = [device.get_field(n) for n in device.field_names()]
        self.assertTrue(polled)
        self.assertTrue(all(f.address < SETTINGS_FIRST_ADDRESS for f in polled))
        # The settings component gets exactly those fields, and the platforms
        # keep a whole profile to build their entities from.
        kept = settings.restrict_fields.call_args.args[0]
        self.assertIn("ac_o_switch", kept)
        self.assertIs(coordinator.device, schema)
        schema.restrict_fields.assert_not_called()

    @_shared
    async def test_the_first_poll_reads_both_and_merges_them(self, link):
        coordinator, _device, _schema, settings = self._coordinator(link)

        result = await coordinator._async_update_data()

        self.assertEqual(result, {"ac_o_switch": 1, "b_soc_total": 80})
        settings.async_update_with_retry.assert_awaited_once()

    @patch("custom_components.bluetti_modbus.coordinator.time.monotonic")
    @_shared
    async def test_settings_are_read_once_a_minute_and_kept_in_between(
        self, link, monotonic
    ):
        coordinator, _device, _schema, settings = self._coordinator(link)

        monotonic.return_value = 1000.0
        await coordinator._async_update_data()
        monotonic.return_value = 1015.0
        result = await coordinator._async_update_data()

        # Read once, and still in the snapshot fifteen seconds later.
        settings.async_update_with_retry.assert_awaited_once()
        self.assertEqual(result["ac_o_switch"], 1)

        monotonic.return_value = 1060.0
        await coordinator._async_update_data()
        self.assertEqual(settings.async_update_with_retry.await_count, 2)

    @_shared
    async def test_a_failed_settings_read_keeps_the_poll_and_the_last_values(
        self, link
    ):
        coordinator, _device, _schema, settings = self._coordinator(link)
        await coordinator._async_update_data()
        settings.async_update_with_retry.side_effect = ModbusConnectionError("dropped")
        coordinator._settings_due_at = 0.0

        result = await coordinator._async_update_data()

        self.assertEqual(result, {"ac_o_switch": 1, "b_soc_total": 80})
        # Still due, so the very next cycle tries again.
        self.assertEqual(coordinator._settings_due_at, 0.0)

    @patch("custom_components.bluetti_modbus.coordinator.time.monotonic")
    @_shared
    async def test_a_settings_write_brings_the_settings_read_forward(
        self, link, monotonic
    ):
        coordinator, _device, schema, settings = self._coordinator(link)
        monotonic.return_value = 1000.0
        await coordinator._async_update_data()

        await coordinator.async_write("ac_o_switch", 0)

        # Written through the whole profile, and confirmed on the first poll
        # once the device has settled rather than up to a minute later.
        schema.write.assert_awaited_once_with("ac_o_switch", 0)
        settings.values = {"ac_o_switch": 0}
        monotonic.return_value = 1015.0
        result = await coordinator._async_update_data()
        self.assertEqual(settings.async_update_with_retry.await_count, 2)
        self.assertEqual(result["ac_o_switch"], 0)

    @patch("custom_components.bluetti_modbus.coordinator.time.monotonic")
    @_shared
    async def test_a_poll_right_after_a_write_keeps_the_written_value(
        self, link, monotonic
    ):
        # The device serves the old value for a moment after a write. A poll
        # landing in that moment must neither read the settings - it would
        # read the old value and keep it for a minute - nor merge the old
        # snapshot back in: the switch would snap back under the owner's hand.
        coordinator, _device, _schema, settings = self._coordinator(link)
        monotonic.return_value = 1000.0
        await coordinator._async_update_data()

        await coordinator.async_write("ac_o_switch", 0)
        monotonic.return_value = 1001.0
        result = await coordinator._async_update_data()

        settings.async_update_with_retry.assert_awaited_once()
        self.assertEqual(result["ac_o_switch"], 0)

    @_shared
    async def test_a_data_area_write_leaves_the_settings_schedule_alone(
        self, link
    ):
        coordinator, _device, _schema, _settings = self._coordinator(link)
        await coordinator._async_update_data()
        due = coordinator._settings_due_at

        await coordinator.async_write("b_soc_total", 50)

        self.assertEqual(coordinator._settings_due_at, due)

    @_shared
    async def test_a_profile_without_settings_is_not_split(self, link):
        # An S Meter declares nothing from 57001 up: nothing to split, and the
        # readings device stays the schema exactly as before.
        link.device = SMeter(None)
        link.read = AsyncMock(return_value={})

        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        self.assertEqual(link.extra_devices, [])
        self.assertIs(coordinator.device, link.device)
        self.assertEqual(await coordinator._async_update_data(), {})


class TestReadRawRegisters(unittest.IsolatedAsyncioTestCase):
    """The undecoded register words behind a diagnostics dump - see
    PollingCoordinator.async_read_raw_registers()."""

    @_shared
    async def test_returns_the_devices_raw_map(self, link):
        raw = {"holding": {50001: 1, 50002: 432}}
        link.device.async_read_raw = AsyncMock(return_value=raw)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator.async_read_raw_registers()

        self.assertEqual(result, {"device": raw})
        # notify=False: a diagnostics read must not fire update listeners
        # as if it were a poll.
        link.device.async_read_raw.assert_awaited_once_with(notify=False)

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @_shared
    async def test_includes_the_aggregate_summary_once_a_poll_has_built_it(
        self, link, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.device.async_read_raw = AsyncMock(
            return_value={"holding": {50001: 1}}
        )
        link.read = AsyncMock(return_value={})
        aggregate = aggregate_fn.return_value
        aggregate.async_update_with_retry = AsyncMock()
        aggregate.values = {}
        aggregate.async_read_raw = AsyncMock(return_value={"holding": {51001: 4}})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        # Before any poll the aggregate component doesn't exist yet - the
        # raw dump only covers the main device.
        self.assertEqual(
            await coordinator.async_read_raw_registers(),
            {"device": {"holding": {50001: 1}}},
        )

        await coordinator._async_update_data()

        self.assertEqual(
            await coordinator.async_read_raw_registers(),
            {
                "device": {"holding": {50001: 1}},
                "aggregate_pack_summary": {"holding": {51001: 4}},
            },
        )
        aggregate.async_read_raw.assert_awaited_once_with(notify=False)

    @_shared
    async def test_waits_for_an_in_flight_poll_to_finish(self, link):
        # Same reason as async_write: this device's Modbus TCP stack is
        # fragile under overlapping requests on one connection, so a
        # diagnostics read must queue behind the poll, not race it.
        read_started = asyncio.Event()
        release_read = asyncio.Event()

        async def slow_read():
            read_started.set()
            await release_read.wait()
            return {}

        link.read = slow_read
        link.device.async_read_raw = AsyncMock(return_value={})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        update_task = asyncio.ensure_future(coordinator._async_update_data())
        await read_started.wait()

        raw_task = asyncio.ensure_future(coordinator.async_read_raw_registers())
        await asyncio.sleep(0)
        self.assertFalse(link.device.async_read_raw.called)

        release_read.set()
        await update_task
        await raw_task

        link.device.async_read_raw.assert_awaited_once()


class TestAggregatePackSummary(unittest.IsolatedAsyncioTestCase):
    """The "Pack Summary" block (51001-51008) - only reports correctly at a
    different Modbus slave address (250) than the main device's own, see
    coordinator.py and bluetti_modbus_lib.aggregate_pack_summary()."""

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", False)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @_shared
    async def test_aggregate_summary_is_read_and_merged_into_result(
        self, link, aggregate_fn
    ):
        # Gate patched off so this stays about the aggregate summary alone
        # (with 4 packs reported, the per-pack reads would otherwise run).
        link.device = MagicMock(spec=Balco260)
        # The main read's own (wrong, slave-1) value - overwritten below by
        # the aggregate summary's (correct, slave-250) value.
        link.read = AsyncMock(
            return_value={"d_num_battery_packs": 0}
        )
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {"d_num_battery_packs": 4, "b_soc_total": 100}
        aggregate_fn.return_value = summary
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        aggregate_fn.assert_called_once_with(link.units[250])
        summary.async_update_with_retry.assert_awaited_once()
        self.assertEqual(result["d_num_battery_packs"], 4)
        self.assertEqual(result["b_soc_total"], 100)

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @_shared
    async def test_reuses_the_same_aggregate_component_across_polls(
        self, link, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {}
        aggregate_fn.return_value = summary
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        aggregate_fn.assert_called_once_with(link.units[250])
        self.assertEqual(summary.async_update_with_retry.await_count, 2)

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @_shared
    async def test_skips_aggregate_summary_for_non_balco260_devices(
        self, link, aggregate_fn
    ):
        # EP2000/S Meter's battery-pack behavior is unconfirmed on real
        # hardware - this integration's scope is Balco260 only.
        link.device = MagicMock(spec=SMeter)
        link.read = AsyncMock(return_value={})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        aggregate_fn.assert_not_called()

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @_shared
    async def test_skips_aggregate_summary_for_ac500(self, link, aggregate_fn):
        # AC500's own d_num_battery_packs means "device maximum," not
        # Balco260's confirmed "actual installed count" (real-hardware
        # testing) - aggregate_pack_summary() stays Balco260-only for now.
        link.device = MagicMock(spec=AC500)
        link.read = AsyncMock(return_value={})
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        aggregate_fn.assert_not_called()


class TestBatteryPacks(unittest.IsolatedAsyncioTestCase):
    """Individual BC260 packs beyond the first - see coordinator.py and
    const.INDIVIDUAL_BC260_PACKS_CONFIRMED's own comment for the hardware
    this was confirmed on."""

    def _mock_aggregate(self, aggregate_fn, num_packs: int) -> None:
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {"d_num_battery_packs": num_packs}
        aggregate_fn.return_value = summary

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", False)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_the_gate_still_works_when_off(
        self, link, battery_pack_fn, aggregate_fn
    ):
        # INDIVIDUAL_BC260_PACKS_CONFIRMED is True by default now (#55) -
        # proven by patching it back to False.
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 4)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result["d_num_battery_packs"], 4)

    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_a_pack_that_is_not_reporting_publishes_nothing(
        self, link, battery_pack_fn, aggregate_fn
    ):
        # Real hardware (2026-09-18, three packs): slot 41 answered its
        # serial number and zeros for everything else - a pack asleep or
        # off. Its values are not published, so its entities go unavailable
        # instead of showing 0 %, 0 V (and 3000 A for b_c's raw 0).
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 3)
        silent = MagicMock()
        silent.async_update_with_retry = AsyncMock()
        silent.values = {"b_type": "", "b_serial": 2615112301352, "b_v": 0.0, "b_c": 3000.0, "b_soc": 0}
        live = MagicMock()
        live.async_update_with_retry = AsyncMock()
        live.values = {"b_type": "BC260", "b_serial": 2610110280905, "b_v": 27.2, "b_soc": 85}
        battery_pack_fn.side_effect = [silent, live]
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        self.assertNotIn("pack_2_b_soc", result)
        self.assertNotIn("pack_2_b_serial", result)
        self.assertEqual(result["pack_3_b_soc"], 85)
        self.assertEqual(result["pack_3_b_type"], "BC260")

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_reads_battery_packs_when_multiple_are_present(
        self, link, battery_pack_fn, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 2)
        pack2 = MagicMock()
        pack2.async_update_with_retry = AsyncMock()
        pack2.values = {"b_type": "BC260", "b_v": 27.2, "b_soc": 77}
        battery_pack_fn.return_value = pack2
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        # Pack 2 is the first expansion pack, at slave 41 (pack_slave_id()).
        battery_pack_fn.assert_called_once_with(link.units[41])
        pack2.async_update_with_retry.assert_awaited_once()
        self.assertEqual(result["pack_2_b_soc"], 77)
        self.assertNotIn("pack_1_b_soc", result)  # same slave as the main unit

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_reads_every_pack_from_2_to_num_packs(
        self, link, battery_pack_fn, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 3)
        pack = MagicMock()
        pack.async_update_with_retry = AsyncMock()
        pack.values = {"b_type": "BC260", "b_v": 27.0, "b_soc": 50}
        battery_pack_fn.return_value = pack
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        self.assertEqual(
            [c.args[0].unit_id for c in battery_pack_fn.call_args_list],
            [41, 42],
        )

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_caps_at_max_battery_packs(self, link, battery_pack_fn, aggregate_fn):
        # d_num_battery_packs reporting more than BLUETTI's own confirmed
        # maximum (5) must not be trusted past that cap.
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 16)
        pack = MagicMock()
        pack.async_update_with_retry = AsyncMock()
        pack.values = {}
        battery_pack_fn.return_value = pack
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()

        self.assertEqual(
            [c.args[0].unit_id for c in battery_pack_fn.call_args_list],
            [41, 42, 43, 44],
        )

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_reuses_the_same_pack_component_across_polls(
        self, link, battery_pack_fn, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 2)
        pack = MagicMock()
        pack.async_update_with_retry = AsyncMock()
        pack.values = {"b_type": "BC260", "b_v": 27.0, "b_soc": 50}
        battery_pack_fn.return_value = pack
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        # Pack 2 is the first expansion pack, at slave 41 (pack_slave_id()).
        battery_pack_fn.assert_called_once_with(link.units[41])
        self.assertEqual(pack.async_update_with_retry.await_count, 2)

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_skips_packs_for_a_single_installed_pack(
        self, link, battery_pack_fn, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 1)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result, {"d_num_battery_packs": 1})

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_skips_packs_for_zero_installed_packs(
        self, link, battery_pack_fn, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        self._mock_aggregate(aggregate_fn, 0)
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result, {"d_num_battery_packs": 0})

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_skips_packs_when_d_num_battery_packs_is_missing(
        self, link, battery_pack_fn, aggregate_fn
    ):
        link.device = MagicMock(spec=Balco260)
        link.read = AsyncMock(return_value={})
        summary = MagicMock()
        summary.async_update_with_retry = AsyncMock()
        summary.values = {}
        aggregate_fn.return_value = summary
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        self.assertEqual(result, {})

    @patch("custom_components.bluetti_modbus.coordinator.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.coordinator.aggregate_pack_summary_component")
    @patch("custom_components.bluetti_modbus.coordinator.battery_pack_component")
    @_shared
    async def test_skips_packs_for_non_balco260_devices(
        self, link, battery_pack_fn, aggregate_fn
    ):
        # EP2000's battery-pack behavior is unconfirmed on real hardware -
        # this integration's scope is Balco260 only for this feature.
        link.device = MagicMock(spec=SMeter)
        link.read = AsyncMock(
            return_value={"d_num_battery_packs": 3}
        )
        coordinator = PollingCoordinator(MagicMock(), MagicMock(), _config())

        result = await coordinator._async_update_data()

        battery_pack_fn.assert_not_called()
        aggregate_fn.assert_not_called()
        self.assertEqual(result, {"d_num_battery_packs": 3})


class TestHomeAssistantsSharedConnection(unittest.IsolatedAsyncioTestCase):
    """Against Home Assistant's own async_get_unit, not a double: the units
    this entry holds are what Settings -> Connectivity -> Modbus lists."""

    async def test_the_entry_is_listed_on_the_devices_connection_until_it_unloads(self):
        from homeassistant.components.modbus.connection import async_get_connection_info

        hass = MagicMock()
        hass.data = {}
        entry = MagicMock()
        entry.entry_id = "entry"
        on_unload = []
        entry.async_on_unload.side_effect = on_unload.append

        PollingCoordinator(hass, entry, _config())

        [info] = async_get_connection_info(hass)
        self.assertEqual(info.endpoint, ("tcp", "10.2.1.60", 502))
        self.assertEqual(info.units, {"entry": [1]})

        for release in on_unload:
            await release()
        self.assertEqual(async_get_connection_info(hass), [])

