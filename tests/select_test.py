import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
from modbus_connection.exceptions import ModbusProtocolError

from custom_components.bluetti_modbus.select import (
    BluettiSelectEntity,
    async_setup_entry,
)
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import get_device
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib.enums import (
    ApexChargingMode,
    ChargingMode,
)


def _device_info():
    return {"name": "Test Device"}


def _select(field_name="d_charging_mode") -> BluettiSelectEntity:
    coordinator = MagicMock(config_entry=MagicMock(entry_id="test_entry_id"), data={})
    select = BluettiSelectEntity(coordinator, _device_info(), field_name, ChargingMode)
    select.async_write_ha_state = MagicMock()
    return select


class TestBluettiSelectEntityInit(unittest.TestCase):
    def test_translation_key_and_unique_id(self):
        select = _select()
        self.assertEqual(select._attr_translation_key, "d_charging_mode")
        self.assertEqual(select.unique_id, "test_entry_id_test_device_d_charging_mode")

    def test_options_are_the_enum_members_as_snake_case(self):
        self.assertEqual(_select().options, ["standard", "silent", "turbo"])

    def test_current_option_starts_unknown(self):
        self.assertIsNone(_select().current_option)

    def test_is_a_control_enabled_by_default(self):
        # Shown under Controls, next to the output switches, and enabled by
        # default as they are.
        select = _select()
        self.assertIsNone(select.entity_category)
        self.assertTrue(select.entity_registry_enabled_default)


class TestAsyncAddedToHass(unittest.IsolatedAsyncioTestCase):
    async def test_primes_current_option_from_data_already_on_the_coordinator(self):
        select = _select()
        select.coordinator.data = {"d_charging_mode": ChargingMode.Turbo}

        await select.async_added_to_hass()

        self.assertEqual(select.current_option, "turbo")


class TestAsyncSelectOption(unittest.IsolatedAsyncioTestCase):
    async def test_writes_the_enum_member_to_the_device(self):
        select = _select()
        select.coordinator.async_write = AsyncMock()

        await select.async_select_option("silent")

        select.coordinator.async_write.assert_awaited_once_with("d_charging_mode", ChargingMode.Silent)

    async def test_optimistically_updates_current_option(self):
        select = _select()
        select.coordinator.async_write = AsyncMock()

        await select.async_select_option("standard")

        self.assertEqual(select.current_option, "standard")
        select.async_write_ha_state.assert_called_once()

    async def test_write_failure_raises_homeassistant_error(self):
        select = _select()
        select.coordinator.async_write = AsyncMock(
            side_effect=ModbusProtocolError("write_register(57023, 2): Expected response to match request")
        )

        with self.assertRaises(HomeAssistantError) as raised:
            await select.async_select_option("turbo")

        self.assertEqual(raised.exception.translation_key, "write_failed")
        self.assertIn("Expected response", raised.exception.translation_placeholders["error"])
        # Not applied - the device never confirmed the write.
        self.assertIsNone(select.current_option)
        select.async_write_ha_state.assert_not_called()


class TestHandleCoordinatorUpdate(unittest.TestCase):
    def test_data_none_leaves_current_option_unknown(self):
        select = _select()
        select.coordinator.data = None
        select._handle_coordinator_update()
        self.assertIsNone(select.current_option)

    def test_missing_field_leaves_current_option_unknown(self):
        select = _select()
        select.coordinator.data = {}
        select._handle_coordinator_update()
        self.assertIsNone(select.current_option)

    def test_enum_member_value(self):
        select = _select()
        select.coordinator.data = {"d_charging_mode": ChargingMode.Silent}
        select._handle_coordinator_update()
        self.assertEqual(select.current_option, "silent")

    def test_plain_int_value(self):
        # What the coordinator keeps right after a write, or a raw read.
        select = _select()
        select.coordinator.data = {"d_charging_mode": 0}
        select._handle_coordinator_update()
        self.assertEqual(select.current_option, "standard")

    def test_unknown_int_value_leaves_current_option_unknown(self):
        select = _select()
        select.coordinator.data = {"d_charging_mode": 7}
        select._handle_coordinator_update()
        self.assertIsNone(select.current_option)


class TestAc200lProfile(unittest.TestCase):
    def test_charging_mode_is_a_writable_enum_at_57023(self):
        field = get_device("ac200l").get_field("d_charging_mode")
        self.assertIsNotNone(field)
        self.assertEqual(field.address, 57023)
        self.assertTrue(field.writable)
        self.assertIs(field.convert, ChargingMode)


class TestPa030Profile(unittest.TestCase):
    def test_charging_mode_adds_custom_to_the_ac200l_modes(self):
        field = get_device("pa030").get_field("d_charging_mode")
        self.assertIsNotNone(field)
        self.assertEqual(field.address, 57023)
        self.assertTrue(field.writable)
        self.assertIs(field.convert, ApexChargingMode)

    def test_the_select_offers_custom(self):
        coordinator = MagicMock(config_entry=MagicMock(entry_id="test_entry_id"), data={})
        select = BluettiSelectEntity(coordinator, _device_info(), "d_charging_mode", ApexChargingMode)
        self.assertEqual(select.options, ["standard", "silent", "turbo", "custom"])


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    def _entry(self, get_field_return):
        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.device.get_field.return_value = get_field_return
        entry = MagicMock(entry_id="entry1")
        entry.runtime_data = coordinator
        return entry

    @patch("custom_components.bluetti_modbus.select.dev_info")
    @patch("custom_components.bluetti_modbus.select.FullDeviceConfig")
    async def test_adds_an_entity_for_a_writable_enum_field(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="ac200l", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        added = []

        await async_setup_entry(MagicMock(), self._entry(MagicMock(writable=True, convert=ChargingMode)), added.extend)

        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], BluettiSelectEntity)
        self.assertEqual(added[0].options, ["standard", "silent", "turbo"])

    @patch("custom_components.bluetti_modbus.select.dev_info")
    @patch("custom_components.bluetti_modbus.select.FullDeviceConfig")
    async def test_skips_a_field_that_is_not_writable(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="ac200l", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        added = []

        await async_setup_entry(MagicMock(), self._entry(MagicMock(writable=False, convert=ChargingMode)), added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.select.dev_info")
    @patch("custom_components.bluetti_modbus.select.FullDeviceConfig")
    async def test_skips_a_field_not_backed_by_an_int_enum(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="ac200l", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        added = []

        await async_setup_entry(MagicMock(), self._entry(MagicMock(writable=True, convert=None)), added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.select.dev_info")
    @patch("custom_components.bluetti_modbus.select.FullDeviceConfig")
    async def test_skips_a_field_the_device_does_not_have(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()
        added = []

        await async_setup_entry(MagicMock(), self._entry(None), added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.select.FullDeviceConfig")
    async def test_no_coordinator_logs_error_and_adds_nothing(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="ac200l", address="10.2.1.60")
        entry = MagicMock(entry_id="entry1")
        entry.runtime_data = MagicMock()
        added = []

        await async_setup_entry(MagicMock(), entry, added.extend)

        self.assertEqual(added, [])
