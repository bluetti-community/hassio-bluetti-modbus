import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.bluetti_modbus import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
    device_info,
    get_unique_id,
    phase_device_info,
)
from custom_components.bluetti_modbus.const import DATA_COORDINATOR, DOMAIN


class TestAsyncUnloadEntry(unittest.IsolatedAsyncioTestCase):
    async def test_unload_success_shuts_down_coordinator_and_clears_data(self):
        entry = MagicMock()
        entry.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.async_shutdown = AsyncMock()
        coordinator.aclose = AsyncMock()

        hass = MagicMock()
        hass.data = {DOMAIN: {"test_entry": {DATA_COORDINATOR: coordinator}}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)

        self.assertTrue(result)
        coordinator.async_shutdown.assert_awaited_once()
        coordinator.aclose.assert_awaited_once()
        self.assertNotIn("test_entry", hass.data[DOMAIN])

    async def test_unload_failure_leaves_data_and_coordinator_untouched(self):
        entry = MagicMock()
        entry.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.async_shutdown = AsyncMock()

        hass = MagicMock()
        hass.data = {DOMAIN: {"test_entry": {DATA_COORDINATOR: coordinator}}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, entry)

        self.assertFalse(result)
        coordinator.async_shutdown.assert_not_awaited()
        self.assertIn("test_entry", hass.data[DOMAIN])


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    @patch("custom_components.bluetti_modbus.dr")
    @patch("custom_components.bluetti_modbus.PollingCoordinator")
    async def test_setup_creates_coordinator_and_forwards_platforms(
        self, coordinator_cls, dr_module
    ):
        # Empty data: d_serial/d_ver_arm/d_ver_dsp haven't been read yet (no
        # poll has happened), so the registered DeviceInfo shouldn't carry
        # serial_number/sw_version at all - see the next test for the case
        # where they have been.
        coordinator = MagicMock(data={})
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator_cls.return_value = coordinator
        device_registry = MagicMock()
        dr_module.async_get.return_value = device_registry

        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}

        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_forward_entry_setups = AsyncMock()

        result = await async_setup_entry(hass, entry)

        self.assertTrue(result)
        coordinator.async_config_entry_first_refresh.assert_awaited_once()
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()
        self.assertIs(hass.data[DOMAIN]["entry1"][DATA_COORDINATOR], coordinator)
        # The main device is registered explicitly, before platform setup -
        # S Meter's per-phase sub-devices (see phase_device_info()) need it
        # already present to resolve via_device_id against.
        device_registry.async_get_or_create.assert_called_once_with(
            config_entry_id="entry1",
            identifiers={(DOMAIN, "10.2.1.60")},
            name=entry.title,
            manufacturer="Bluetti",
            model="Balco260",
            configuration_url="http://10.2.1.60",
        )

    @patch("custom_components.bluetti_modbus.dr")
    @patch("custom_components.bluetti_modbus.PollingCoordinator")
    async def test_setup_includes_serial_and_firmware_once_read(
        self, coordinator_cls, dr_module
    ):
        coordinator = MagicMock(
            data={"d_serial": 1234567890123, "d_ver_arm": 500110112, "d_ver_dsp": 500140110}
        )
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator_cls.return_value = coordinator
        device_registry = MagicMock()
        dr_module.async_get.return_value = device_registry

        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}

        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_forward_entry_setups = AsyncMock()

        await async_setup_entry(hass, entry)

        _, kwargs = device_registry.async_get_or_create.call_args
        self.assertEqual(kwargs["serial_number"], "1234567890123")
        self.assertEqual(kwargs["sw_version"], "ARM 500110112, DSP 500140110")

    async def test_setup_with_invalid_entry_data_returns_false(self):
        entry = MagicMock()
        entry.data = {}
        hass = MagicMock()

        result = await async_setup_entry(hass, entry)

        self.assertFalse(result)


class TestAsyncMigrateEntry(unittest.IsolatedAsyncioTestCase):
    def _entry(self, *, version=1, dev_type="smeter"):
        entry = MagicMock()
        entry.version = version
        entry.title = "My Device"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": dev_type}
        return entry

    @patch("custom_components.bluetti_modbus.er")
    async def test_disables_an_already_enabled_d_timestamp_entity(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = "sensor.my_device_d_timestamp"
        registry.async_get.return_value = MagicMock(disabled_by=None)
        hass = MagicMock()
        entry = self._entry()

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        registry.async_get_entity_id.assert_any_call(
            "sensor", DOMAIN, get_unique_id("My Device d_timestamp")
        )
        registry.async_update_entity.assert_called_once_with(
            "sensor.my_device_d_timestamp",
            disabled_by=er_module.RegistryEntryDisabler.INTEGRATION,
        )
        # A version-1 entry cascades all the way to the current version in
        # one call - see async_migrate_entry's own docstring for why.
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=3)

    @patch("custom_components.bluetti_modbus.er")
    async def test_does_not_touch_an_already_disabled_d_timestamp_entity(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = "sensor.my_device_d_timestamp"
        registry.async_get.return_value = MagicMock(disabled_by="user")
        hass = MagicMock()
        entry = self._entry()

        await async_migrate_entry(hass, entry)

        registry.async_update_entity.assert_not_called()
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=3)

    @patch("custom_components.bluetti_modbus.er")
    async def test_d_timestamp_not_yet_registered_is_a_no_op(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry()

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        registry.async_get.assert_not_called()
        registry.async_update_entity.assert_not_called()
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=3)

    @patch("custom_components.bluetti_modbus.er")
    async def test_non_smeter_device_skips_d_timestamp_handling(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry(dev_type="balco260")

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        registry.async_update_entity.assert_not_called()
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=3)

    @patch("custom_components.bluetti_modbus.er")
    async def test_invalid_entry_data_still_bumps_the_version(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry()
        entry.data = {}

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        registry.async_get_entity_id.assert_not_called()
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=3)

    @patch("custom_components.bluetti_modbus.er")
    async def test_removes_retired_identity_sensors_for_balco260(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.side_effect = lambda domain, dom, uid: f"sensor.{uid}"
        hass = MagicMock()
        entry = self._entry(version=2, dev_type="balco260")

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        removed = {c.args[0] for c in registry.async_remove.call_args_list}
        self.assertEqual(
            removed,
            {
                "sensor.my_device_d_serial",
                "sensor.my_device_d_ver_arm",
                "sensor.my_device_d_ver_dsp",
            },
        )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=3)

    @patch("custom_components.bluetti_modbus.er")
    async def test_skips_a_retired_sensor_that_was_never_registered(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry(version=2, dev_type="balco260")

        await async_migrate_entry(hass, entry)

        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_smeter_skips_retired_identity_sensor_removal(self, er_module):
        # d_serial/d_ver_arm/d_ver_dsp don't exist on S Meter at all.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=2, dev_type="smeter")

        await async_migrate_entry(hass, entry)

        registry.async_get_entity_id.assert_not_called()
        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_already_current_version_is_a_no_op(self, er_module):
        hass = MagicMock()
        entry = self._entry(version=3)

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        er_module.async_get.assert_not_called()
        hass.config_entries.async_update_entry.assert_not_called()


class TestDeviceInfo(unittest.TestCase):
    def test_returns_device_info_for_valid_entry(self):
        entry = MagicMock()
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        entry.title = "My Balco260"

        info = device_info(entry)

        self.assertEqual(info["identifiers"], {(DOMAIN, "10.2.1.60")})
        self.assertEqual(info["name"], "My Balco260")
        self.assertEqual(info["model"], "Balco260")
        self.assertEqual(info["configuration_url"], "http://10.2.1.60")

    def test_returns_none_for_invalid_entry(self):
        entry = MagicMock()
        entry.data = {}

        self.assertIsNone(device_info(entry))


class TestPhaseDeviceInfo(unittest.TestCase):
    @patch("custom_components.bluetti_modbus.dr")
    def test_returns_sub_device_info_linked_to_the_main_device(self, dr_module):
        dr_module.async_get_device_id_by_identifier.return_value = "main-device-id"
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "smeter"}
        entry.title = "My S Meter"
        hass = MagicMock()

        info = phase_device_info(hass, entry, "a")

        self.assertEqual(info["identifiers"], {(DOMAIN, "10.2.1.60-phase-a")})
        self.assertEqual(info["name"], "My S Meter Phase A")
        self.assertEqual(info["via_device_id"], "main-device-id")
        dr_module.async_get_device_id_by_identifier.assert_called_once_with(
            hass, (DOMAIN, "10.2.1.60"), config_entry_id="entry1"
        )

    def test_returns_none_for_invalid_entry(self):
        entry = MagicMock()
        entry.data = {}
        hass = MagicMock()

        self.assertIsNone(phase_device_info(hass, entry, "a"))


class TestGetUniqueId(unittest.TestCase):
    def test_without_sensor_type(self):
        self.assertEqual(get_unique_id("My Sensor Name"), "my_sensor_name")

    def test_with_sensor_type(self):
        self.assertEqual(
            get_unique_id("My Sensor Name", "sensor"), "sensor.my_sensor_name"
        )
