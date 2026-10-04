"""Entities numbered beyond the count the unit reports (hassio-bluetti-modbus#134)."""

import unittest
from unittest.mock import MagicMock, patch

from custom_components.bluetti_modbus.const import CONF_SLOTS_BEYOND_COUNT_PENDING
from custom_components.bluetti_modbus.coordinator import PollingCoordinator
from custom_components.bluetti_modbus.sensor import (
    async_setup_entry,
    beyond_reported_count,
)

_ENTRY_DATA = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}


def _field(name):
    f = MagicMock(address=50001, unit=None, writable=False)
    f.name = name
    return f


class TestBeyondReportedCount(unittest.TestCase):
    def test_each_group_follows_its_own_count(self):
        # Counts from a Balco 260 diagnostics dump: three grid phases (an
        # S Meter is fitted), one AC output phase, one inverter, four PV
        # inputs, one firmware slot.
        data = {
            "d_phase_count": 3,
            "ac_phase_count": 1,
            "d_inverter_phase_count": 1,
            "pv_dc_count": 4,
            "pv_ac_count": 0,
            "b_ver_count": 1,
        }
        self.assertFalse(beyond_reported_count("g_3_i_p", data))
        self.assertFalse(beyond_reported_count("g_3_p_active", data))
        self.assertTrue(beyond_reported_count("ac_2_o_v", data))
        self.assertFalse(beyond_reported_count("ac_1_o_p", data))
        self.assertTrue(beyond_reported_count("d_inverter_2_status", data))
        self.assertTrue(beyond_reported_count("d_inverter_3_p_active_internal", data))
        self.assertFalse(beyond_reported_count("pv_4_i_type", data))
        self.assertTrue(beyond_reported_count("b_ver_2", data))
        self.assertFalse(beyond_reported_count("b_ver_1", data))

    def test_ep2000_inverters_follow_the_phase_count_not_the_inverter_count(self):
        # On the EP2000 d_inverter_1..3 are the three phases of one inverter:
        # d_num_inverters reads 1 while all three are live.
        data = {"d_num_inverters": 1, "d_inverter_phase_count": 3, "pv_dc_count": 2}
        self.assertFalse(beyond_reported_count("d_inverter_3_p", data))
        self.assertTrue(beyond_reported_count("pv_3_i_p", data))

    def test_ac_pv_inputs_add_to_the_dc_ones(self):
        data = {"pv_dc_count": 1, "pv_ac_count": 1}
        self.assertFalse(beyond_reported_count("pv_2_i_p", data))
        self.assertTrue(beyond_reported_count("pv_3_i_p", data))

    def test_a_missing_ac_pv_count_counts_as_none(self):
        self.assertTrue(beyond_reported_count("pv_2_i_p", {"pv_dc_count": 1}))

    def test_a_missing_or_zero_count_hides_nothing(self):
        # The FridgePower reads d_inverter_phase_count 0 with one inverter.
        self.assertFalse(beyond_reported_count("d_inverter_2_p", {}))
        self.assertFalse(beyond_reported_count("d_inverter_2_p", {"d_inverter_phase_count": 0}))
        self.assertFalse(beyond_reported_count("d_inverter_2_p", {"d_inverter_phase_count": None}))
        self.assertFalse(beyond_reported_count("d_inverter_2_p", {"d_inverter_phase_count": True}))

    def test_fields_without_a_number_are_never_hidden(self):
        data = {"d_phase_count": 1, "pv_dc_count": 1, "b_ver_count": 1}
        for name in ("g_i_p_total", "pv_i_p_total", "d_inverter_total", "b_ver_count"):
            self.assertFalse(beyond_reported_count(name, data), name)

    def test_an_expansion_pack_uses_its_own_count(self):
        data = {"b_ver_count": 3, "pack_2_b_ver_count": 1}
        self.assertTrue(beyond_reported_count("b_ver_2", data, "pack_2_"))
        self.assertFalse(beyond_reported_count("b_ver_2", data))


class TestSetupHidesSlotsBeyondCount(unittest.IsolatedAsyncioTestCase):
    def _setup(self, data, entry_data=None, sensors=("pv_2_i_p", "pv_3_i_p")):
        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock())
        coordinator.data = data
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        entry.data = dict(entry_data or _ENTRY_DATA)
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = list(sensors)
        bluetti_device.get_field.side_effect = _field
        return hass, entry, bluetti_device

    @patch("custom_components.bluetti_modbus.sensor.INDIVIDUAL_BC260_PACKS_CONFIRMED", True)
    @patch("custom_components.bluetti_modbus.sensor.pack_device_info")
    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    async def test_entities_beyond_the_counts_are_created_disabled(
        self, dev_info_fn, get_device_fn, battery_device_info_fn, pack_device_info_fn
    ):
        dev_info_fn.return_value = {"name": "Balco 260"}
        battery_device_info_fn.return_value = {"name": "Battery"}
        pack_device_info_fn.side_effect = lambda hass, entry, pack_num, coordinator: {
            "name": f"Pack {pack_num}"
        }
        hass, entry, bluetti_device = self._setup(
            {
                "pv_dc_count": 2,
                "b_ver_count": 1,
                "d_num_battery_packs": 2,
                "pack_2_b_ver_count": 2,
            }
        )
        get_device_fn.return_value = bluetti_device
        added = []

        await async_setup_entry(hass, entry, added.extend)

        enabled = {s._response_key: s._attr_entity_registry_enabled_default for s in added}
        self.assertTrue(enabled["pv_2_i_p"])
        self.assertFalse(enabled["pv_3_i_p"])
        self.assertFalse(enabled["b_ver_2"])
        self.assertTrue(enabled["pack_2_b_ver_2"])
        self.assertFalse(enabled["pack_2_b_ver_3"])
        # No migration pending: nothing touches the registry.
        hass.config_entries.async_update_entry.assert_not_called()

    @patch("custom_components.bluetti_modbus.sensor.er")
    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    async def test_a_migrated_entry_disables_its_registered_entities_once(
        self, dev_info_fn, get_device_fn, battery_device_info_fn, er_module
    ):
        dev_info_fn.return_value = {"name": "Balco 260"}
        battery_device_info_fn.return_value = {"name": "Battery"}
        hass, entry, bluetti_device = self._setup(
            {"pv_dc_count": 1, "b_ver_count": 1},
            entry_data={**_ENTRY_DATA, CONF_SLOTS_BEYOND_COUNT_PENDING: True},
            sensors=("pv_1_i_p", "pv_2_i_p", "pv_3_i_p"),
        )
        get_device_fn.return_value = bluetti_device
        registry = MagicMock()
        er_module.async_get.return_value = registry
        entries = {}

        def entity_id_for(domain, platform, unique_id):
            # pv_2 registered and enabled, pv_3 never registered, b_ver_3
            # disabled by the user, b_ver_4 registered and enabled.
            for key, entity_id in (
                ("pv_2_i_p", "sensor.pv_2"),
                ("b_ver_3", "sensor.b_ver_3"),
                ("b_ver_4", "sensor.b_ver_4"),
            ):
                if unique_id == unique_ids[key]:
                    return entity_id
            return None

        registry.async_get_entity_id.side_effect = entity_id_for
        entries["sensor.pv_2"] = MagicMock(disabled_by=None)
        entries["sensor.b_ver_3"] = MagicMock(disabled_by="user")
        entries["sensor.b_ver_4"] = MagicMock(disabled_by=None)
        registry.async_get.side_effect = entries.get
        unique_ids = {}
        added = []

        def add(sensors):
            added.extend(sensors)

        original_disable = __import__(
            "custom_components.bluetti_modbus.sensor", fromlist=["_"]
        )._disable_registered_beyond_count

        def capture(hass_, entry_, sensors):
            for s in sensors:
                unique_ids[s._response_key] = s.unique_id
            original_disable(hass_, entry_, sensors)

        with patch(
            "custom_components.bluetti_modbus.sensor._disable_registered_beyond_count",
            side_effect=capture,
        ):
            await async_setup_entry(hass, entry, add)

        # Every entity beyond a count is checked, the pv_1 and b_ver_1-free
        # ones never are.
        self.assertEqual(set(unique_ids), {"pv_2_i_p", "pv_3_i_p", "b_ver_2", "b_ver_3", "b_ver_4"})
        disabled = {call.args[0] for call in registry.async_update_entity.call_args_list}
        self.assertEqual(disabled, {"sensor.pv_2", "sensor.b_ver_4"})
        for call in registry.async_update_entity.call_args_list:
            self.assertEqual(
                call.kwargs, {"disabled_by": er_module.RegistryEntryDisabler.INTEGRATION}
            )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, data=_ENTRY_DATA)

    @patch("custom_components.bluetti_modbus.sensor.er")
    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    async def test_an_entity_whose_registry_entry_vanished_is_skipped(
        self, dev_info_fn, get_device_fn, battery_device_info_fn, er_module
    ):
        dev_info_fn.return_value = {"name": "Balco 260"}
        battery_device_info_fn.return_value = {"name": "Battery"}
        hass, entry, bluetti_device = self._setup(
            {"pv_dc_count": 1},
            entry_data={**_ENTRY_DATA, CONF_SLOTS_BEYOND_COUNT_PENDING: True},
        )
        get_device_fn.return_value = bluetti_device
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = "sensor.pv_2"
        registry.async_get.return_value = None

        await async_setup_entry(hass, entry, lambda sensors: None)

        registry.async_update_entity.assert_not_called()
        hass.config_entries.async_update_entry.assert_called_once_with(entry, data=_ENTRY_DATA)


if __name__ == "__main__":
    unittest.main()
