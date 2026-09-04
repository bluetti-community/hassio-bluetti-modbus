import unittest
from enum import Enum
from unittest.mock import MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

from custom_components.bluetti_modbus.sensor import (
    BluettiSensor,
    _enum_options,
    _snake_case,
    async_setup_entry,
)


class _FakeEnum(Enum):
    Reserve = 0
    DcPv = 100


def _device_info():
    return {"name": "Test Device"}


def _pack_field(name):
    # A stand-in for any PACK_INFO_FIELDS lookup - what the unconditional
    # battery sub-device loop (and, when packs 2+ exist, the pack loop) both
    # call get_field() with. Shared so every test exercising either path
    # doesn't need its own copy.
    f = MagicMock(address=51221, unit="%", writable=False)
    f.name = name
    return f


def _sensor(**overrides) -> BluettiSensor:
    kwargs = {
        "coordinator": MagicMock(
            config_entry=MagicMock(entry_id="test_entry_id"), data={}
        ),
        "device_info": _device_info(),
        "address": 50001,
        "response_key": "d_num_inverters",
    }
    kwargs.update(overrides)
    sensor = BluettiSensor(**kwargs)
    sensor.async_write_ha_state = MagicMock()
    return sensor


class TestSnakeCase(unittest.TestCase):
    def test_converts_real_enum_member_names(self):
        # Every value these enums actually use, confirmed against real
        # hardware and the official register spec's own wording.
        cases = {
            "Idle": "idle",
            "NoFault": "no_fault",
            "NoWarning": "no_warning",
            "Reserve": "reserve",
            "DcPv": "dc_pv",
            "AcPv": "ac_pv",
            "OffGrid": "off_grid",
            "GridConnectedOperation": "grid_connected_operation",
            "AbnormalOffGrid": "abnormal_off_grid",
        }
        for pascal, snake in cases.items():
            self.assertEqual(_snake_case(pascal), snake)


class TestEnumOptions(unittest.TestCase):
    def test_returns_snake_cased_member_names_for_an_enum_backed_field(self):
        field = MagicMock(convert=_FakeEnum)
        self.assertEqual(_enum_options(field), ["reserve", "dc_pv"])

    def test_returns_none_for_a_plain_numeric_field(self):
        field = MagicMock(convert=None)
        self.assertIsNone(_enum_options(field))

    def test_returns_none_for_a_lambda_convert(self):
        # e.g. reference_offset_current()/bit_flag()/dotted_version() in
        # bluetti_modbus_lib - a real function, not an Enum subclass.
        field = MagicMock(convert=lambda raw: raw)
        self.assertIsNone(_enum_options(field))

    def test_returns_none_when_field_has_no_convert_attribute(self):
        field = object()
        self.assertIsNone(_enum_options(field))


class TestBluettiSensorInit(unittest.TestCase):
    def test_unique_id_and_translation_key_from_response_key(self):
        sensor = _sensor(response_key="d_num_inverters")
        self.assertEqual(sensor._attr_translation_key, "d_num_inverters")
        self.assertEqual(sensor.unique_id, "test_entry_id_test_device_d_num_inverters")

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

    def test_options_sets_enum_device_class_and_options(self):
        # ENUM is mutually exclusive with a numeric device_class
        # (homeassistant/components/sensor/__init__.py rejects the
        # combination) - options= always wins over a device_class= passed
        # alongside it, since an enum-backed field never has a real one.
        sensor = _sensor(
            options=["reserve", "dc_pv"], device_class=SensorDeviceClass.POWER
        )
        self.assertEqual(sensor._attr_device_class, SensorDeviceClass.ENUM)
        self.assertEqual(sensor._attr_options, ["reserve", "dc_pv"])

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

    def test_enum_value_uses_its_snake_cased_name(self):
        # Not the raw PascalCase name - HA's hassfest requires translation
        # keys (and therefore the raw state values they translate) to match
        # [a-z0-9-_]+ (confirmed by a real CI failure on "DcPv" etc.).
        class InverterStatus(Enum):
            GridConnectedOperation = "GridConnectedOperation"

        sensor = _sensor(response_key="d_inverter_status")
        sensor.coordinator.data = {
            "d_inverter_status": InverterStatus.GridConnectedOperation
        }
        sensor._handle_coordinator_update()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, "grid_connected_operation")

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
    @patch("custom_components.bluetti_modbus.sensor.phase_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_adds_a_sensor_per_field(
        self, config_cls, dev_info_fn, get_device_fn, phase_device_info_fn
    ):
        # smeter, not balco260 - sidesteps the unconditional battery
        # sub-device construction (see TestCreatesBatterySensors for that),
        # irrelevant to what this test actually checks (field_metadata
        # lookup by name). Unlike the battery loop, S Meter's phase sensors
        # are still gated by get_sensors() below (kept to just
        # "ac_o_p_total"), so phase_device_info only needs a bare mock here,
        # not a real per-phase implementation.
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        phase_device_info_fn.side_effect = lambda hass, entry, phase: {
            "name": f"Test Device Phase {phase.upper()}"
        }

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

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
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

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        # get_field("d_status") would raise (not in the side_effect dict) if
        # d_status weren't skipped before it's ever looked up.
        self.assertEqual([s._response_key for s in added], ["d_timestamp"])

    @patch("custom_components.bluetti_modbus.sensor.phase_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_writable_b_soc_low_is_skipped_number_py_handles_it(
        self, config_cls, dev_info_fn, get_device_fn, phase_device_info_fn
    ):
        # smeter, not balco260 - the FIELDS_SHOWN_VIA_NUMBER check itself
        # doesn't care about dev_type, and this sidesteps the unconditional
        # battery sub-device construction (see TestCreatesBatterySensors).
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        phase_device_info_fn.side_effect = lambda hass, entry, phase: {
            "name": f"Test Device Phase {phase.upper()}"
        }

        field = MagicMock(address=57016, unit="%", writable=True)
        field.name = "b_soc_low"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["b_soc_low"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.sensor.phase_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_writable_ac_o_switch_is_skipped_switch_py_handles_it(
        self, config_cls, dev_info_fn, get_device_fn, phase_device_info_fn
    ):
        # smeter, not balco260 - the FIELDS_SHOWN_VIA_SWITCH check itself
        # doesn't care about dev_type, and this sidesteps the unconditional
        # battery sub-device construction (see TestCreatesBatterySensors).
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        phase_device_info_fn.side_effect = lambda hass, entry, phase: {
            "name": f"Test Device Phase {phase.upper()}"
        }

        field = MagicMock(address=57001, unit=None, writable=True)
        field.name = "ac_o_switch"
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["ac_o_switch"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
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

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual([s._response_key for s in added], ["ac_o_switch"])

    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_identity_fields_are_skipped_they_feed_device_info_instead(
        self, config_cls, dev_info_fn, get_device_fn, battery_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        battery_device_info_fn.return_value = {"name": "Test Device Battery"}

        # Permissive - unlike a narrow dict-of-one, this also answers the
        # unconditional battery sub-device loop's PACK_INFO_FIELDS lookups
        # (b_soc, b_v, ...), which aren't this test's concern.
        def _field(name):
            f = MagicMock(address=50001, unit=None)
            f.name = name
            return f

        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = [
            "d_serial",
            "d_ver_arm",
            "d_ver_dsp",
            "b_ver_1",
            "d_iot_ver",
            "d_iot_serial",
            "d_num_inverters",
        ]
        bluetti_device.get_field.side_effect = _field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        response_keys = {s._response_key for s in added}
        # d_serial is no longer excluded - it's real data, just not "the"
        # device serial anymore (see const.py's FIELDS_SHOWN_VIA_DEVICE_INFO
        # - d_iot_serial replaced it there). d_num_inverters is unrelated,
        # proving normal fields still get through.
        self.assertIn("d_serial", response_keys)
        self.assertIn("d_num_inverters", response_keys)
        # d_ver_arm/d_ver_dsp/d_iot_ver/d_iot_serial feed the main
        # DeviceInfo instead; b_ver_1 feeds the battery sub-device's -
        # never plain sensors.
        self.assertNotIn("d_ver_arm", response_keys)
        self.assertNotIn("d_ver_dsp", response_keys)
        self.assertNotIn("b_ver_1", response_keys)
        self.assertNotIn("d_iot_ver", response_keys)
        self.assertNotIn("d_iot_serial", response_keys)

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

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
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

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
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

    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.pack_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_creates_pack_sensors_when_multiple_packs_are_present(
        self, config_cls, dev_info_fn, get_device_fn, pack_device_info_fn, battery_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        pack_device_info_fn.side_effect = lambda hass, entry, pack_num: {
            "name": f"Test Device Pack {pack_num}"
        }
        battery_device_info_fn.return_value = {"name": "Test Device Battery"}

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

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {"d_num_battery_packs": 2}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        # The unconditional battery sub-device (see
        # TestCreatesBatterySensors) also creates sensors now - filter this
        # test's own assertions down to pack 2's, which are what it's
        # actually about.
        pack_sensors = [s for s in added if s._response_key.startswith("pack_2_")]
        self.assertEqual(len(pack_sensors), len(PACK_INFO_FIELDS))
        self.assertEqual(pack_sensors[0].device_info, {"name": "Test Device Pack 2"})

    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_pack_sensors_for_a_single_installed_pack(
        self, config_cls, dev_info_fn, get_device_fn, battery_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        battery_device_info_fn.return_value = {"name": "Test Device Battery"}
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []
        bluetti_device.get_field.side_effect = _pack_field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {"d_num_battery_packs": 1}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        # No BC200 pack sub-device (1 = only the built-in battery) - but the
        # battery's own sensors (unconditional, unprefixed) are still there.
        self.assertEqual([s for s in added if s._response_key.startswith("pack_")], [])
        self.assertTrue(len(added) > 0)

    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_pack_sensors_for_zero_installed_packs(
        self, config_cls, dev_info_fn, get_device_fn, battery_device_info_fn
    ):
        # The most common real-world value for a bare Balco260 with no BC200
        # pack attached at all - distinct from "1" (see the test above) and
        # from "missing" (coordinator.data.get() returning None, also
        # excluded by the isinstance check in sensor.py). Confirmed against
        # real hardware this session.
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        battery_device_info_fn.return_value = {"name": "Test Device Battery"}
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []
        bluetti_device.get_field.side_effect = _pack_field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {"d_num_battery_packs": 0}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        # The built-in battery's own sensors are still there even with 0
        # total packs reported - "0" doesn't mean "no battery at all", see
        # battery_device_info()'s own docstring.
        self.assertEqual([s for s in added if s._response_key.startswith("pack_")], [])
        self.assertTrue(len(added) > 0)

    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_coordinator_does_not_add_entities(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")

        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": MagicMock()}}}
        entry = MagicMock(entry_id="entry1")
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)

        async_add_entities.assert_not_called()


class TestCreatesBatterySensors(unittest.IsolatedAsyncioTestCase):
    """Balco260's built-in battery, on its own sub-device (const.py's
    FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO) - same PACK_INFO_FIELDS block as
    BC200 packs 2..5 (TestAsyncSetupEntry's pack tests), but unconditional
    (a Balco260 always has a built-in battery) and without a pack_num
    prefix (its data comes from the main device's own read, under plain
    field names - see coordinator.py)."""

    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_creates_a_sensor_per_field_except_the_battery_device_info_ones(
        self, config_cls, dev_info_fn, get_device_fn, battery_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        battery_device_info_fn.return_value = {"name": "Test Device Battery"}

        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []  # main-loop sensors irrelevant here
        bluetti_device.get_field.side_effect = _pack_field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator
        from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import (
            PACK_INFO_FIELDS,
        )

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {}  # no BC200 packs - the battery still gets sensors
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        response_keys = {s._response_key for s in added}
        # b_serial/b_ver_1 feed the battery's own DeviceInfo instead (see
        # FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO) - not sensors here.
        self.assertEqual(
            response_keys, PACK_INFO_FIELDS - {"b_serial", "b_ver_1"}
        )
        # No pack_N_ prefix - unlike packs 2+, unprefixed (see the class
        # docstring).
        self.assertTrue(all("pack_" not in k for k in response_keys))
        self.assertTrue(all(s.device_info == {"name": "Test Device Battery"} for s in added))

    @patch("custom_components.bluetti_modbus.sensor.battery_device_info")
    @patch("custom_components.bluetti_modbus.sensor.phase_device_info")
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_smeter_has_no_battery_sub_device(
        self, config_cls, dev_info_fn, get_device_fn, phase_device_info_fn, battery_device_info_fn
    ):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        phase_device_info_fn.side_effect = lambda hass, entry, phase: {
            "name": f"Test Device Phase {phase.upper()}"
        }

        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = []
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.data = {}
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        battery_device_info_fn.assert_not_called()
        self.assertEqual(added, [])
