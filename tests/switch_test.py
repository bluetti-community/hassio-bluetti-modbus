import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.switch import SwitchDeviceClass

from custom_components.bluetti_modbus.switch import (
    BluettiSwitchEntity,
    async_setup_entry,
)


def _device_info():
    return {"name": "Test Device"}


def _switch(field_name="ac_o_switch") -> BluettiSwitchEntity:
    coordinator = MagicMock(config_entry=MagicMock(entry_id="test_entry_id"), data={})
    switch = BluettiSwitchEntity(coordinator, _device_info(), field_name)
    switch.async_write_ha_state = MagicMock()
    return switch


class TestBluettiSwitchEntityInit(unittest.TestCase):
    def test_translation_key_and_unique_id(self):
        switch = _switch("g_i_switch")
        self.assertEqual(switch._attr_translation_key, "g_i_switch")
        self.assertEqual(switch.unique_id, "test_entry_id_test_device_g_i_switch")

    def test_is_on_starts_unknown(self):
        switch = _switch()
        self.assertIsNone(switch.is_on)

    def test_device_class_is_switch_not_outlet(self):
        # These control internal AC/grid relays on the inverter, not a
        # literal power outlet - sets a sensible default icon; the user can
        # still override it per-entity regardless.
        switch = _switch()
        self.assertEqual(switch._attr_device_class, SwitchDeviceClass.SWITCH)


class TestAsyncAddedToHass(unittest.IsolatedAsyncioTestCase):
    async def test_primes_is_on_from_data_already_on_the_coordinator(self):
        # async_config_entry_first_refresh() already ran (see __init__.py)
        # before this entity was ever created - coordinator.data reflects
        # that read. Without priming here, is_on would stay unknown until
        # the coordinator's next scheduled poll (update_interval, 30s).
        switch = _switch("ac_o_switch")
        switch.coordinator.data = {"ac_o_switch": 1}

        await switch.async_added_to_hass()

        self.assertTrue(switch.is_on)


class TestAsyncTurnOnOff(unittest.IsolatedAsyncioTestCase):
    async def test_turn_on_writes_1_to_the_device(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.device.write = AsyncMock()

        await switch.async_turn_on()

        switch.coordinator.device.write.assert_awaited_once_with("ac_o_switch", 1)

    async def test_turn_off_writes_0_to_the_device(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.device.write = AsyncMock()

        await switch.async_turn_off()

        switch.coordinator.device.write.assert_awaited_once_with("ac_o_switch", 0)

    async def test_turn_on_optimistically_updates_is_on(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.device.write = AsyncMock()

        await switch.async_turn_on()

        self.assertTrue(switch.is_on)
        switch.async_write_ha_state.assert_called_once()

    async def test_turn_off_optimistically_updates_is_on(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.device.write = AsyncMock()

        await switch.async_turn_off()

        self.assertFalse(switch.is_on)
        switch.async_write_ha_state.assert_called_once()


class TestHandleCoordinatorUpdate(unittest.TestCase):
    def test_data_none_leaves_is_on_unknown(self):
        switch = _switch()
        switch.coordinator.data = None
        switch._handle_coordinator_update()
        self.assertIsNone(switch.is_on)

    def test_data_not_a_dict_leaves_is_on_unknown(self):
        switch = _switch()
        switch.coordinator.data = "not-a-dict"
        switch._handle_coordinator_update()
        self.assertIsNone(switch.is_on)

    def test_missing_field_leaves_is_on_unknown(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.data = {}
        switch._handle_coordinator_update()
        self.assertIsNone(switch.is_on)

    def test_non_int_value_leaves_is_on_unknown(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.data = {"ac_o_switch": None}
        switch._handle_coordinator_update()
        self.assertIsNone(switch.is_on)

    def test_zero_value_is_off(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.data = {"ac_o_switch": 0}
        switch._handle_coordinator_update()
        self.assertFalse(switch.is_on)

    def test_nonzero_value_is_on(self):
        switch = _switch("ac_o_switch")
        switch.coordinator.data = {"ac_o_switch": 1}
        switch._handle_coordinator_update()
        self.assertTrue(switch.is_on)


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.switch.dev_info")
    @patch("custom_components.bluetti_modbus.switch.FullDeviceConfig")
    async def test_adds_an_entity_per_writable_field(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        writable_field = MagicMock(writable=True)
        coordinator.device.get_field.return_value = writable_field
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(len(added), 3)
        self.assertTrue(all(isinstance(e, BluettiSwitchEntity) for e in added))
        self.assertEqual(
            {e._field_name for e in added},
            {"ac_o_switch", "g_i_switch", "g_o_switch"},
        )

    @patch("custom_components.bluetti_modbus.switch.dev_info")
    @patch("custom_components.bluetti_modbus.switch.FullDeviceConfig")
    async def test_skips_a_field_that_is_not_writable(self, config_cls, dev_info_fn):
        # e.g. EP2000 today: the schema knows about these fields, but
        # bluetti_modbus_lib doesn't mark them writable there yet.
        config_cls.from_dict.return_value = MagicMock(dev_type="ep2000", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.device.get_field.return_value = MagicMock(writable=False)
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.switch.dev_info")
    @patch("custom_components.bluetti_modbus.switch.FullDeviceConfig")
    async def test_skips_a_field_the_device_does_not_have(self, config_cls, dev_info_fn):
        config_cls.from_dict.return_value = MagicMock(dev_type="smeter", address="10.2.1.60")
        dev_info_fn.return_value = _device_info()

        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.device.get_field.return_value = None
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.switch.FullDeviceConfig")
    async def test_no_coordinator_logs_error_and_adds_nothing(self, config_cls):
        config_cls.from_dict.return_value = MagicMock(dev_type="balco260", address="10.2.1.60")

        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": MagicMock()}}}
        entry = MagicMock(entry_id="entry1")
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])

    @patch("custom_components.bluetti_modbus.switch.dev_info")
    async def test_invalid_config_data_adds_nothing(self, dev_info_fn):
        from custom_components.bluetti_modbus.coordinator import PollingCoordinator

        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        hass = MagicMock()
        hass.data = {"bluetti_modbus": {"entry1": {"coordinator": coordinator}}}
        entry = MagicMock(entry_id="entry1", data={})
        added = []

        await async_setup_entry(hass, entry, added.extend)

        self.assertEqual(added, [])
        dev_info_fn.assert_not_called()
