import unittest
from unittest.mock import MagicMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.bluetti_modbus.binary_sensor import (
    BluettiOnlineBinarySensor,
    async_setup_entry,
)


def _device_info():
    return {"name": "Test Device"}


def _sensor() -> BluettiOnlineBinarySensor:
    sensor = BluettiOnlineBinarySensor(MagicMock(), _device_info())
    sensor.async_write_ha_state = MagicMock()
    return sensor


class TestBluettiOnlineBinarySensorInit(unittest.TestCase):
    def test_device_class_is_connectivity(self):
        sensor = _sensor()
        self.assertEqual(sensor._attr_device_class, BinarySensorDeviceClass.CONNECTIVITY)

    def test_translation_key_and_unique_id(self):
        sensor = _sensor()
        self.assertEqual(sensor._attr_translation_key, "d_status")
        self.assertEqual(sensor.unique_id, "test_device_d_status")

    def test_is_on_starts_unknown(self):
        # No available/_attr_available override here - that's
        # CoordinatorEntity's own (coordinator.last_update_success), not
        # reimplemented on this class. is_on itself starts unknown (None),
        # BinarySensorEntity's own default.
        sensor = _sensor()
        self.assertIsNone(sensor.is_on)


class TestHandleCoordinatorUpdate(unittest.TestCase):
    def test_data_none_leaves_is_on_unknown(self):
        sensor = _sensor()
        sensor.coordinator.data = None
        sensor._handle_coordinator_update()
        self.assertIsNone(sensor.is_on)

    def test_data_not_a_dict_leaves_is_on_unknown(self):
        sensor = _sensor()
        sensor.coordinator.data = "not-a-dict"
        sensor._handle_coordinator_update()
        self.assertIsNone(sensor.is_on)

    def test_missing_d_status_leaves_is_on_unknown(self):
        sensor = _sensor()
        sensor.coordinator.data = {}
        sensor._handle_coordinator_update()
        self.assertIsNone(sensor.is_on)

    def test_non_bool_d_status_leaves_is_on_unknown(self):
        # bluetti_modbus_lib decodes d_status to a bool (bit_flag()) - a
        # raw int here would mean a stale/unexpected vendored copy, not a
        # value this entity should trust or try to interpret itself. Bit
        # extraction is that library's job, not this integration's - see
        # bit_flag()'s own tests for that.
        sensor = _sensor()
        sensor.coordinator.data = {"d_status": 4}
        sensor._handle_coordinator_update()
        self.assertIsNone(sensor.is_on)

    def test_d_status_false_is_offline(self):
        sensor = _sensor()
        sensor.coordinator.data = {"d_status": False}
        sensor._handle_coordinator_update()
        self.assertFalse(sensor.is_on)

    def test_d_status_true_is_online(self):
        sensor = _sensor()
        sensor.coordinator.data = {"d_status": True}
        sensor._handle_coordinator_update()
        self.assertTrue(sensor.is_on)


class TestAsyncAddedToHass(unittest.IsolatedAsyncioTestCase):
    async def test_primes_is_on_from_data_already_on_the_coordinator(self):
        # async_config_entry_first_refresh() already ran (see __init__.py)
        # before this entity was ever created - coordinator.data reflects
        # that read. Without priming here, is_on would stay unknown until
        # the coordinator's next scheduled poll (update_interval, 30s).
        sensor = _sensor()
        sensor.coordinator.data = {"d_status": True}

        await sensor.async_added_to_hass()

        self.assertTrue(sensor.is_on)


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.binary_sensor.dev_info")
    @patch("custom_components.bluetti_modbus.binary_sensor.FullDeviceConfig")
    async def test_adds_online_sensor_for_smeter(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], BluettiOnlineBinarySensor)
        self.assertEqual(added[0].device_info, _device_info())

    @patch("custom_components.bluetti_modbus.binary_sensor.dev_info")
    @patch("custom_components.bluetti_modbus.binary_sensor.FullDeviceConfig")
    async def test_no_entities_for_non_smeter_device(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.binary_sensor.FullDeviceConfig")
    async def test_no_coordinator_logs_error_and_adds_nothing(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")

        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": MagicMock()}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.binary_sensor.dev_info")
    async def test_invalid_config_data_adds_nothing(self, dev_info_fn):
        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1", data={})
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])
        dev_info_fn.assert_not_called()
