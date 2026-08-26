import unittest
from enum import Enum
from unittest.mock import MagicMock, patch

from homeassistant.const import EntityCategory

from custom_components.bluetti_modbus.sensor import BluettiSensor, async_setup_entry


class _FakeDeviceClass(Enum):
    POWER = "power"


class _FakeCategory(Enum):
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"


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

    def test_device_class_state_class_category_use_enum_value(self):
        sensor = _sensor(
            device_class=_FakeDeviceClass.POWER,
            state_class=_FakeDeviceClass.POWER,
            category=_FakeCategory.DIAGNOSTIC,
        )
        self.assertEqual(sensor._attr_device_class, "power")
        self.assertEqual(sensor._attr_state_class, "power")
        self.assertEqual(sensor._attr_entity_category, EntityCategory.DIAGNOSTIC)

    def test_config_category_becomes_diagnostic(self):
        # SensorEntity refuses entity_category=CONFIG outright - this
        # integration only exposes read-only sensors, so config-tagged
        # fields (e.g. b_soc_low/b_soc_high) must surface as diagnostic
        # instead, or adding the entity raises HomeAssistantError.
        sensor = _sensor(category=_FakeCategory.CONFIG)
        self.assertEqual(sensor._attr_entity_category, EntityCategory.DIAGNOSTIC)

    def test_starts_unavailable(self):
        sensor = _sensor()
        self.assertFalse(sensor.available)


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


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.sensor.get_device")
    @patch("custom_components.bluetti_modbus.sensor.dev_info")
    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_adds_a_sensor_per_field(self, config_cls, dev_info_fn, get_device_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        field = MagicMock(address=50001, name="d_num_inverters", unit=None)
        del field.category
        del field.device_class
        del field.state_class
        bluetti_device = MagicMock()
        bluetti_device.get_sensors.return_value = ["d_num_inverters"]
        bluetti_device.get_field.return_value = field
        get_device_fn.return_value = bluetti_device

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], BluettiSensor)

    @patch("custom_components.bluetti_modbus.sensor.FullDeviceConfig")
    async def test_no_coordinator_does_not_add_entities(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")

        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": MagicMock()}}}
        entry = MagicMock(entry_id="entry1")
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)

        async_add_entities.assert_not_called()
