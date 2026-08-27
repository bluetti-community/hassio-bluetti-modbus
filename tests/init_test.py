import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.bluetti_modbus import (
    async_setup_entry,
    async_unload_entry,
    device_info,
    get_unique_id,
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
    @patch("custom_components.bluetti_modbus.PollingCoordinator")
    async def test_setup_creates_coordinator_and_forwards_platforms(self, coordinator_cls):
        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator_cls.return_value = coordinator

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
        self.assertEqual(info["model"], "balco260")

    def test_returns_none_for_invalid_entry(self):
        entry = MagicMock()
        entry.data = {}

        self.assertIsNone(device_info(entry))


class TestGetUniqueId(unittest.TestCase):
    def test_without_sensor_type(self):
        self.assertEqual(get_unique_id("My Sensor Name"), "my_sensor_name")

    def test_with_sensor_type(self):
        self.assertEqual(
            get_unique_id("My Sensor Name", "sensor"), "sensor.my_sensor_name"
        )
