import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.bluetti_modbus import async_unload_entry
from custom_components.bluetti_modbus.const import DATA_COORDINATOR, DOMAIN


class TestAsyncUnloadEntry(unittest.IsolatedAsyncioTestCase):
    async def test_unload_success_shuts_down_coordinator_and_clears_data(self):
        entry = MagicMock()
        entry.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.async_shutdown = AsyncMock()

        hass = MagicMock()
        hass.data = {DOMAIN: {"test_entry": {DATA_COORDINATOR: coordinator}}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)

        self.assertTrue(result)
        coordinator.async_shutdown.assert_awaited_once()
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
