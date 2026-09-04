import unittest
from unittest.mock import MagicMock

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
        # A BC200 pack's own serial (pack_N_b_serial) - a different literal
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
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry1": {DATA_COORDINATOR: coordinator}}}

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

        self.assertEqual(diagnostics["coordinator"]["data"], {})
