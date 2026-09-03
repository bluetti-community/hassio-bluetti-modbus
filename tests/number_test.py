import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.bluetti_modbus.number import (
    BluettiNumberEntity,
    async_setup_entry,
)


def _device_info():
    return {"name": "Test Device"}


def _number(field_name="b_soc_low") -> BluettiNumberEntity:
    number = BluettiNumberEntity(MagicMock(), _device_info(), field_name)
    number.async_write_ha_state = MagicMock()
    return number


class TestBluettiNumberEntityInit(unittest.TestCase):
    def test_min_max_step(self):
        number = _number()
        self.assertEqual(number._attr_native_min_value, 0)
        self.assertEqual(number._attr_native_max_value, 100)
        self.assertEqual(number._attr_native_step, 1)

    def test_translation_key_and_unique_id(self):
        number = _number("b_soc_high")
        self.assertEqual(number._attr_translation_key, "b_soc_high")
        self.assertEqual(number.unique_id, "test_device_b_soc_high")

    def test_native_value_starts_unknown(self):
        number = _number()
        self.assertIsNone(number.native_value)


class TestAsyncSetNativeValue(unittest.IsolatedAsyncioTestCase):
    async def test_writes_the_value_to_the_device(self):
        number = _number("b_soc_low")
        number.coordinator.device.write = AsyncMock()

        await number.async_set_native_value(42.0)

        number.coordinator.device.write.assert_awaited_once_with("b_soc_low", 42)

    async def test_optimistically_updates_native_value(self):
        number = _number("b_soc_low")
        number.coordinator.device.write = AsyncMock()

        await number.async_set_native_value(42.0)

        self.assertEqual(number.native_value, 42.0)
        number.async_write_ha_state.assert_called_once()


class TestHandleCoordinatorUpdate(unittest.TestCase):
    def test_data_none_leaves_native_value_unknown(self):
        number = _number()
        number.coordinator.data = None
        number._handle_coordinator_update()
        self.assertIsNone(number.native_value)

    def test_data_not_a_dict_leaves_native_value_unknown(self):
        number = _number()
        number.coordinator.data = "not-a-dict"
        number._handle_coordinator_update()
        self.assertIsNone(number.native_value)

    def test_missing_field_leaves_native_value_unknown(self):
        number = _number("b_soc_low")
        number.coordinator.data = {}
        number._handle_coordinator_update()
        self.assertIsNone(number.native_value)

    def test_non_int_value_leaves_native_value_unknown(self):
        number = _number("b_soc_low")
        number.coordinator.data = {"b_soc_low": None}
        number._handle_coordinator_update()
        self.assertIsNone(number.native_value)

    def test_valid_int_value_is_used(self):
        number = _number("b_soc_low")
        number.coordinator.data = {"b_soc_low": 20}
        number._handle_coordinator_update()
        self.assertEqual(number.native_value, 20)


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.number.dev_info")
    @patch("custom_components.bluetti_modbus.number.FullDeviceConfig")
    async def test_adds_an_entity_per_writable_field(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        writable_field = MagicMock(writable=True)
        coordinator.device.get_field.return_value = writable_field
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(len(added), 2)
        self.assertTrue(all(isinstance(e, BluettiNumberEntity) for e in added))
        self.assertEqual(
            {e._field_name for e in added},
            {"b_soc_low", "b_soc_high"},
        )

    @patch("custom_components.bluetti_modbus.number.dev_info")
    @patch("custom_components.bluetti_modbus.number.FullDeviceConfig")
    async def test_skips_a_field_that_is_not_writable(self, config_cls, dev_info_fn):
        # e.g. EP2000 today: the schema knows about b_soc_low/b_soc_high,
        # but bluetti_modbus_lib doesn't mark them writable there yet.
        config_cls.from_dict.return_value = MagicMock(dev_type="ep2000", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.device.get_field.return_value = MagicMock(writable=False)
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.number.dev_info")
    @patch("custom_components.bluetti_modbus.number.FullDeviceConfig")
    async def test_skips_a_field_the_device_does_not_have(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.device.get_field.return_value = None
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.number.FullDeviceConfig")
    async def test_no_coordinator_logs_error_and_adds_nothing(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")

        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": MagicMock()}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.number.dev_info")
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
