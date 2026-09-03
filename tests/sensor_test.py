import unittest
from enum import Enum
from unittest.mock import MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

from custom_components.bluetti_modbus.sensor import BluettiSensor, async_setup_entry


def _device_info():
    return {"name": "Test Device"}


def _sensor(**overrides) -> BluettiSensor:
    kwargs = {
        "coordinator": MagicMock(),
        "device_info": _device_info(),
        "address": 50001,
        "response_key": "d_num_inverters",
    }
    kwargs.update(overrides)
    sensor = BluettiSensor(**kwargs)
    sensor.async_write_ha_state = MagicMock()
    return sensor


class TestBluettiSensorInit(unittest.TestCase):
    def test_unique_id_and_translation_key_from_response_key(self):
        sensor = _sensor(response_key="d_num_inverters")
        self.assertEqual(sensor._attr_translation_key, "d_num_inverters")
        self.assertEqual(sensor.unique_id, "test_device_d_num_inverters")

    def test_pack_num_prefixes_response_key_and_translation_key(self):
        sensor = _sensor(response_key="b_soc", pack_num=2)
        self.assertEqual(sensor._response_key, "pack_2_b_soc")
        self.assertEqual(sensor._attr_translation_key, "pack_b_soc")

    def test_cell_num_sets_translation_placeholders(self):
        sensor = _sensor(response_key="b_v", cell_num=3)
        self.assertEqual(sensor._attr_translation_key, "pack_b_v")
        self.assertEqual(sensor._attr_translation_placeholders, {"cell_num": "3"})

    def test_device_class_state_class_category_are_set_from_ha_enums(self):
        sensor = _sensor(
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            category=EntityCategory.DIAGNOSTIC,
        )
        self.assertEqual(sensor._attr_device_class, SensorDeviceClass.POWER)
        self.assertEqual(sensor._attr_state_class, SensorStateClass.MEASUREMENT)
        self.assertEqual(sensor._attr_entity_category, EntityCategory.DIAGNOSTIC)

    def test_config_category_becomes_diagnostic(self):
        # SensorEntity refuses entity_category=CONFIG outright - this
        # integration only exposes read-only sensors, so config-tagged
        # fields (e.g. b_soc_low/b_soc_high) must surface as diagnostic
        # instead, or adding the entity raises HomeAssistantError.
        sensor = _sensor(category=EntityCategory.CONFIG)
        self.assertEqual(sensor._attr_entity_category, EntityCategory.DIAGNOSTIC)

    def test_starts_unavailable(self):
        sensor = _sensor()
        self.assertFalse(sensor.available)

    def test_enabled_by_default_defaults_to_true(self):
        sensor = _sensor()
        self.assertTrue(sensor._attr_entity_registry_enabled_default)

    def test_enabled_by_default_can_be_set_to_false(self):
        sensor = _sensor(enabled_by_default=False)
        self.assertFalse(sensor._attr_entity_registry_enabled_default)


class TestSetAvailableUnavailable(unittest.TestCase):
    def test_set_available_resets_counter_and_writes_state(self):
        sensor = _sensor()
        sensor._unavailable_counter = 3
        sensor._set_available()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor._unavailable_counter, 0)
        sensor.async_write_ha_state.assert_called_once()

    def test_set_unavailable_only_flips_after_five_strikes(self):
        sensor = _sensor()
        sensor._set_available()

        for _ in range(4):
            sensor._set_unavailable("test cause")
            self.assertTrue(sensor.available)

        sensor._set_unavailable("test cause")
        self.assertFalse(sensor.available)
        self.assertEqual(sensor._unavailable_counter, 5)


class TestHandleCoordinatorUpdate(unittest.TestCase):
    def test_data_none_marks_unavailable(self):
        sensor = _sensor()
        sensor.coordinator.data = None
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.available)

    def test_data_not_a_dict_marks_unavailable(self):
        sensor = _sensor()
        sensor.coordinator.data = "not a dict"
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.available)

    def test_missing_key_marks_unavailable(self):
        sensor = _sensor(response_key="d_num_inverters")
        sensor.coordinator.data = {"some_other_field": 1}
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.available)

    def test_invalid_type_marks_unavailable(self):
        sensor = _sensor(response_key="d_num_inverters")
        sensor.coordinator.data = {"d_num_inverters": object()}
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.available)

    def test_numeric_value_becomes_available_with_native_value(self):
        sensor = _sensor(response_key="ac_o_p_total")
        sensor.coordinator.data = {"ac_o_p_total": 84}
        sensor._handle_coordinator_update()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 84)

    def test_enum_value_uses_its_name(self):
        class InverterStatus(Enum):
            GridConnectedOperation = "GridConnectedOperation"

        sensor = _sensor(response_key="d_inverter_status")
        sensor.coordinator.data = {
            "d_inverter_status": InverterStatus.GridConnectedOperation
        }
        sensor._handle_coordinator_update()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, "GridConnectedOperation")

    def test_list_value_without_cell_num_marks_unavailable_not_crash(self):
        # Regression test: len(response_data) < self._cell_num used to run
        # even when cell_num was None (the default - async_setup_entry never
        # passes it today), raising TypeError instead of handling it. No
        # field currently decodes to a list, but this is the guard that
        # protects the day one does.
        sensor = _sensor(response_key="some_list_field", cell_num=None)
        sensor.coordinator.data = {"some_list_field": [1, 2, 3]}
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.available)

    def test_list_value_shorter_than_cell_num_marks_unavailable(self):
        sensor = _sensor(response_key="some_list_field", cell_num=5)
        sensor.coordinator.data = {"some_list_field": [1, 2, 3]}
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.available)

    def test_list_value_with_valid_cell_num_picks_indexed_entry(self):
        sensor = _sensor(response_key="some_list_field", cell_num=2)
        sensor.coordinator.data = {"some_list_field": [10, 20, 30]}
        sensor._handle_coordinator_update()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 20)


class TestAsyncAddedToHass(unittest.IsolatedAsyncioTestCase):
    async def test_primes_state_from_data_already_on_the_coordinator(self):
        # async_config_entry_first_refresh() already ran (see __init__.py)
        # before this entity was ever created - coordinator.data reflects
        # that read. Without priming here, this sensor would stay
        # unavailable (_attr_available starts False in __init__) until the
        # coordinator's next scheduled poll (update_interval, 30s).
        sensor = _sensor(response_key="d_num_inverters")
        sensor.coordinator.data = {"d_num_inverters": 2}

        await sensor.async_added_to_hass()

        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 2)


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_adds_a_sensor_per_field(self, config_cls, dev_info_fn, get_device_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        # MagicMock(name=...) sets the mock's own repr, not a `.name`
        # attribute - must be assigned after construction to actually be
        # readable as field.name (this is what async_setup_entry now uses
        # to look metadata up by field name).
        field = MagicMock(address=50001, unit="W")
        field.name = "ac_o_p_total"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["ac_o_p_total"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(len(added), 1)
        sensor = added[0]
        self.assertIsInstance(sensor, BluettiSensor)
        # ac_o_p_total is in field_metadata.FIELD_METADATA as a power
        # measurement - proves async_setup_entry actually looks metadata up
        # by field name, not from the (now removed) field object itself.
        self.assertEqual(sensor._attr_device_class, SensorDeviceClass.POWER)
        self.assertEqual(sensor._attr_state_class, SensorStateClass.MEASUREMENT)

    @patch("custom_components.bluetti_modbus.sensor.phase_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_d_status_is_skipped_it_is_a_binary_sensor_field(
        self, config_cls, dev_info_fn, get_device_fn, phase_device_info_fn
    ):
        # d_status/d_timestamp (55111/55112) are S Meter-only fields (see
        # const.py) - dev_type must actually be "smeter" here, not some
        # other device, for this fixture to mean what it claims.
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        phase_device_info_fn.side_effect = lambda hass, entry, phase: {
            "name": f"Test Device Phase {phase.upper()}"
        }

        field = MagicMock(address=55112, unit=None)
        field.name = "d_timestamp"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["d_status", "d_timestamp"]
        bluetti_device.get_field.side_effect = lambda name: {"d_timestamp": field}[name]
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        # get_field("d_status") would raise (not in the side_effect dict) if
        # d_status weren't skipped before it's ever looked up.
        self.assertEqual([s._response_key for s in added], ["d_timestamp"])

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_writable_b_soc_low_is_skipped_number_py_handles_it(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        field = MagicMock(address=57016, unit="%", writable=True)
        field.name = "b_soc_low"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["b_soc_low"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_writable_ac_o_switch_is_skipped_switch_py_handles_it(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        field = MagicMock(address=57001, unit=None, writable=True)
        field.name = "ac_o_switch"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["ac_o_switch"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_non_writable_ac_o_switch_stays_a_sensor(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        # e.g. EP2000 today: the schema knows about ac_o_switch, but
        # bluetti_modbus_lib doesn't mark it writable there yet - it must
        # stay readable as a plain sensor, not disappear.
        config_cls.from_dict.return_value = MagicMock(dev_type="ep2000", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        field = MagicMock(address=57001, unit=None, writable=False)
        field.name = "ac_o_switch"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["ac_o_switch"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual([s._response_key for s in added], ["ac_o_switch"])

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_d_serial_is_skipped_it_feeds_device_info_instead(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        field = MagicMock(address=50001, unit=None)
        field.name = "d_num_inverters"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = [
            "d_serial",
            "d_ver_arm",
            "d_ver_dsp",
            "b_ver_1",
            "d_num_inverters",
        ]
        bluetti_device.get_field.side_effect = lambda name: {"d_num_inverters": field}[name]
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        # get_field("d_serial") would raise (not in the side_effect dict) if
        # the identity fields weren't skipped before they're ever looked up
        # - same for b_ver_1 (BMS firmware version), which joins them in
        # DeviceInfo.sw_version instead of staying a plain sensor.
        self.assertEqual([s._response_key for s in added], ["d_num_inverters"])

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_non_writable_b_soc_low_stays_a_sensor(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        # e.g. EP2000 today: the schema knows about b_soc_low, but
        # bluetti_modbus_lib doesn't mark it writable there yet - it must
        # stay readable as a plain sensor, not disappear.
        config_cls.from_dict.return_value = MagicMock(dev_type="ep2000", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        field = MagicMock(address=57016, unit="%", writable=False)
        field.name = "b_soc_low"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["b_soc_low"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual([s._response_key for s in added], ["b_soc_low"])

    @patch("custom_components.bluetti_modbus.sensor.phase_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_smeter_routes_phase_fields_to_their_own_sub_device(
        self, config_cls, dev_info_fn, get_device_fn, phase_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        phase_device_info_fn.side_effect = lambda hass, entry, phase: {
            "name": f"Test Device Phase {phase.upper()}"
        }

        main_field = MagicMock(address=55112, unit=None)
        main_field.name = "d_timestamp"
        phase_a_field = MagicMock(address=55114, unit="V")
        phase_a_field.name = "ac_a_v"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["d_timestamp", "ac_a_v"]
        bluetti_device.get_field.side_effect = lambda name: {
            "d_timestamp": main_field,
            "ac_a_v": phase_a_field,
        }[name]
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        by_key = {s._response_key: s for s in added}
        self.assertEqual(by_key["d_timestamp"].device_info, _device_info())
        self.assertEqual(
            by_key["ac_a_v"].device_info, {"name": "Test Device Phase A"}
        )

    @patch("custom_components.bluetti_modbus.sensor.pack_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_creates_pack_sensors_when_multiple_packs_are_present(
        self, config_cls, dev_info_fn, get_device_fn, pack_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        pack_device_info_fn.side_effect = lambda hass, entry, pack_num: {
            "name": f"Test Device Pack {pack_num}"
        }

        def _field(name):
            f = MagicMock(address=51221, unit="%", writable=False)
            f.name = name
            return f

        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []  # main-loop sensors irrelevant here
        bluetti_device.get_field.side_effect = _field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator
        from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import (
            PACK_INFO_FIELDS,
        )

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {"d_num_battery_packs": 2}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        pack_response_keys = {s._response_key for s in added}
        self.assertEqual(len(added), len(PACK_INFO_FIELDS))
        self.assertTrue(all(k.startswith("pack_2_") for k in pack_response_keys))
        self.assertEqual(added[0].device_info, {"name": "Test Device Pack 2"})

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_pack_sensors_for_a_single_installed_pack(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {"d_num_battery_packs": 1}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_pack_sensors_for_zero_installed_packs(
        self, config_cls, dev_info_fn, get_device_fn
    ):
        # The most common real-world value for a bare Balco260 with no BC200
        # pack attached at all - distinct from "1" (see the test above) and
        # from "missing" (coordinator.data.get() returning None, also
        # excluded by the isinstance check in sensor.py). Confirmed against
        # real hardware this session.
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.data = {"d_num_battery_packs": 0}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_coordinator_does_not_add_entities(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")

        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": MagicMock()}}}
        entry = MagicMock(entry_id="entry1")
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)

        async_add_entities.assert_not_called()
