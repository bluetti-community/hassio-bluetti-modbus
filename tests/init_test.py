import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.bluetti_modbus import (
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
        coordinator = MagicMock()
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

    async def test_setup_with_invalid_entry_data_returns_false(self):
        entry = MagicMock()
        entry.data = {}
        hass = MagicMock()

        result = await async_setup_entry(hass, entry)

        self.assertFalse(result)


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
