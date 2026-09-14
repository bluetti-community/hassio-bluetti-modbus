import unittest
from unittest.mock import AsyncMock, MagicMock

from modbus_connection.exceptions import ModbusTimeoutError

from custom_components.bluetti_modbus.const import DATA_COORDINATOR, DOMAIN
from custom_components.bluetti_modbus.diagnostics import (
    async_get_config_entry_diagnostics,
)


class TestAsyncGetConfigEntryDiagnostics(unittest.IsolatedAsyncioTestCase):
    async def test_redacts_the_address_and_every_serial_field(self):
        entry = MagicMock(
            entry_id="entry1",
            data={
                "address": "10.2.1.60",
                "port": 502,
                "name": "Balco 260",
                "type": "balco260",
            },
            version=11,
        )
        coordinator = MagicMock(
            last_update_success=True,
            update_interval="0:00:30",
            data={
                "d_num_inverters": 2,
                "d_iot_serial": 1234567890123,
                "d_serial": 9876543210,
                "b_serial": 555,
                "pack_2_b_serial": 777,
            },
        )
        coordinator.async_read_raw_registers = AsyncMock(return_value={})
        coordinator.device.field_names.return_value = []
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry1": {DATA_COORDINATOR: coordinator}}}

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

        self.assertEqual(diagnostics["entry_data"]["address"], "**REDACTED**")
        # Not sensitive - passed through unredacted, unlike address.
        self.assertEqual(diagnostics["entry_data"]["port"], 502)
        self.assertEqual(diagnostics["entry_data"]["type"], "balco260")
        self.assertEqual(diagnostics["entry_version"], 11)
        self.assertTrue(diagnostics["coordinator"]["last_update_success"])
        self.assertEqual(diagnostics["coordinator"]["update_interval"], "0:00:30")

        data = diagnostics["coordinator"]["data"]
        # A normal reading - not a serial - must survive unredacted, or the
        # dump stops being useful for the "why is field X missing" case
        # this exists for (see CONTRIBUTING.md).
        self.assertEqual(data["d_num_inverters"], 2)
        self.assertEqual(data["d_iot_serial"], "**REDACTED**")
        self.assertEqual(data["d_serial"], "**REDACTED**")
        self.assertEqual(data["b_serial"], "**REDACTED**")
        # A BC260 pack's own serial (pack_N_b_serial) - a different literal
        # key per pack, only ever matched by its "_b_serial" suffix.
        self.assertEqual(data["pack_2_b_serial"], "**REDACTED**")

    async def test_non_dict_coordinator_data_becomes_an_empty_dict(self):
        # Defensive, matching sensor.py's own isinstance guard on the same
        # attribute - not expected to actually happen (diagnostics is only
        # offered for a loaded entry, which implies a successful first
        # refresh already populated a real dict), but cheap to not crash on.
        entry = MagicMock(
            entry_id="entry1",
            data={
                "address": "10.2.1.60",
                "port": 502,
                "name": "Balco 260",
                "type": "balco260",
            },
            version=11,
        )
        coordinator = MagicMock(
            last_update_success=False, update_interval="0:00:30", data=None
        )
        coordinator.async_read_raw_registers = AsyncMock(return_value={})
        coordinator.device.field_names.return_value = []
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry1": {DATA_COORDINATOR: coordinator}}}

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

        self.assertEqual(diagnostics["coordinator"]["data"], {})


def _entry() -> MagicMock:
    return MagicMock(
        entry_id="entry1",
        data={"address": "10.2.1.60", "port": 502, "name": "Balco 260", "type": "balco260"},
        version=11,
    )


def _field(address: int, count: int) -> MagicMock:
    return MagicMock(address=address, count=count)


class TestRawRegisters(unittest.IsolatedAsyncioTestCase):
    """The undecoded register words in a dump - see diagnostics.py's
    _raw_registers()."""

    def _hass(self, coordinator: MagicMock) -> MagicMock:
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry1": {DATA_COORDINATOR: coordinator}}}
        return hass

    async def test_redacts_every_word_a_serial_field_occupies(self):
        # d_serial is 4 registers wide on Balco260 (uint64 at 50206) - the
        # whole span has to go, not just its first word, and a neighbouring
        # non-serial register must survive untouched.
        coordinator = MagicMock(last_update_success=True, update_interval="0:00:30", data={})
        coordinator.device.field_names.return_value = ["d_num_inverters", "d_serial", "b_serial"]
        coordinator.device.get_field.side_effect = {
            "d_num_inverters": _field(50001, 1),
            "d_serial": _field(50206, 4),
            "b_serial": _field(51201, 4),
        }.__getitem__
        coordinator.async_read_raw_registers = AsyncMock(
            return_value={
                "device": {
                    "holding": {
                        50001: 1,
                        50205: 7,
                        50206: 0x1234,
                        50207: 0x5678,
                        50208: 0,
                        50209: 0,
                        50210: 500,
                        51201: 9,
                    }
                },
                "aggregate_pack_summary": {"holding": {51001: 4}},
            }
        )

        diagnostics = await async_get_config_entry_diagnostics(self._hass(coordinator), _entry())

        raw = diagnostics["raw_registers"]
        self.assertEqual(raw["device"]["holding"][50001], 1)
        self.assertEqual(raw["device"]["holding"][50205], 7)
        for address in (50206, 50207, 50208, 50209, 51201):
            self.assertEqual(raw["device"]["holding"][address], "**REDACTED**", address)
        self.assertEqual(raw["device"]["holding"][50210], 500)
        self.assertEqual(raw["aggregate_pack_summary"]["holding"][51001], 4)

    async def test_a_field_without_a_fixed_address_is_skipped(self):
        # Only the RegisterField family carries address/count; a serial
        # declared any other way can't be mapped to words, and must not
        # crash the dump.
        coordinator = MagicMock(last_update_success=True, update_interval="0:00:30", data={})
        coordinator.device.field_names.return_value = ["d_iot_serial"]
        coordinator.device.get_field.return_value = object()
        coordinator.async_read_raw_registers = AsyncMock(
            return_value={"device": {"holding": {53001: 42}}}
        )

        diagnostics = await async_get_config_entry_diagnostics(self._hass(coordinator), _entry())

        self.assertEqual(diagnostics["raw_registers"]["device"]["holding"][53001], 42)

    async def test_a_failed_raw_read_does_not_fail_the_download(self):
        # The decoded snapshot is still worth having, and the error itself
        # is part of what a dump is for.
        coordinator = MagicMock(
            last_update_success=True, update_interval="0:00:30", data={"b_soc": 71}
        )
        coordinator.device.field_names.return_value = []
        coordinator.async_read_raw_registers = AsyncMock(
            side_effect=ModbusTimeoutError("no reply")
        )

        diagnostics = await async_get_config_entry_diagnostics(self._hass(coordinator), _entry())

        self.assertEqual(diagnostics["coordinator"]["data"], {"b_soc": 71})
        self.assertEqual(
            diagnostics["raw_registers"], {"error": "ModbusTimeoutError: no reply"}
        )
