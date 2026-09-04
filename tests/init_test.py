import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.bluetti_modbus import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
    battery_device_info,
    device_info,
    get_unique_id,
    pack_device_info,
    phase_device_info,
)
from custom_components.bluetti_modbus.const import DATA_COORDINATOR, DOMAIN
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import PACK_INFO_FIELDS


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
            model="Balco 260",
            configuration_url="http://10.2.1.60",
        )

    @patch("custom_components.bluetti_modbus.dr")
    @patch("custom_components.bluetti_modbus.PollingCoordinator")
    async def test_setup_includes_serial_and_firmware_once_read(
        self, coordinator_cls, dr_module
    ):
        # d_ver_arm/d_ver_dsp/d_iot_ver already arrive as "major.minor.patch"
        # strings by this point - bluetti_modbus_lib's dotted_version()
        # decodes them before they ever reach coordinator.data. d_iot_serial
        # ("IoT SN"), not d_serial ("Inverter SN"), is the main device's
        # serial_number - and b_ver_1 (BMS) no longer feeds this at all, it's
        # the battery sub-device's own sw_version now (see
        # TestBatteryDeviceInfo).
        coordinator = MagicMock(
            data={
                "d_iot_serial": 1234567890123,
                "d_iot_ver": "50012.01.19",
                "d_ver_arm": "50011.01.12",
                "d_ver_dsp": "50014.01.10",
            }
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
        self.assertEqual(
            kwargs["sw_version"],
            "IoT v50012.01.19, ARM v50011.01.12, DSP v50014.01.10",
        )

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
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

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
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

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
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

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
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

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
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_removes_retired_sensors_for_balco260(self, er_module):
        # Cascading from version 2 all the way to 10 (see the docstring)
        # hits all five retired-sensor-removal steps for this dev_type:
        # 2 -> 3 (identity fields), 6 -> 7 (switch fields), 7 -> 8 (BMS
        # firmware version), 8 -> 9 (IoT firmware version), and 9 -> 10
        # (d_iot_serial + every PACK_INFO_FIELDS name except b_ver_1, now
        # the battery sub-device's own sensors).
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
                "sensor.my_device_ac_o_switch",
                "sensor.my_device_g_i_switch",
                "sensor.my_device_g_o_switch",
                "sensor.my_device_b_ver_1",
                "sensor.my_device_d_iot_ver",
                "sensor.my_device_d_iot_serial",
                *(
                    f"sensor.my_device_{name}"
                    for name in PACK_INFO_FIELDS
                    if name != "b_ver_1"
                ),
            },
        )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

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
    async def test_removes_retired_switch_sensors_for_an_entry_already_on_version_6(
        self, er_module
    ):
        # Not cascading from an earlier version - an entry that already sat
        # at version 6 with ac_o_switch/g_i_switch/g_o_switch still
        # registered as plain sensors. Cascading 6 -> 10 also hits the
        # 7 -> 8, 8 -> 9, and 9 -> 10 steps, same permissive side_effect
        # picking them up too.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.side_effect = lambda domain, dom, uid: f"sensor.{uid}"
        hass = MagicMock()
        entry = self._entry(version=6, dev_type="balco260")

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        removed = {c.args[0] for c in registry.async_remove.call_args_list}
        self.assertEqual(
            removed,
            {
                "sensor.my_device_ac_o_switch",
                "sensor.my_device_g_i_switch",
                "sensor.my_device_g_o_switch",
                "sensor.my_device_b_ver_1",
                "sensor.my_device_d_iot_ver",
                "sensor.my_device_d_iot_serial",
                *(
                    f"sensor.my_device_{name}"
                    for name in PACK_INFO_FIELDS
                    if name != "b_ver_1"
                ),
            },
        )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_skips_a_retired_switch_sensor_that_was_never_registered(
        self, er_module
    ):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry(version=6, dev_type="balco260")

        await async_migrate_entry(hass, entry)

        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_smeter_skips_retired_switch_sensor_removal(self, er_module):
        # ac_o_switch/g_i_switch/g_o_switch don't exist on S Meter at all.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=6, dev_type="smeter")

        await async_migrate_entry(hass, entry)

        registry.async_get_entity_id.assert_not_called()
        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_removes_retired_b_ver_1_sensor_for_an_entry_already_on_version_7(
        self, er_module
    ):
        # Not cascading from an earlier version - an entry that already sat
        # at version 7 with b_ver_1 still registered as a plain sensor.
        # Cascading 7 -> 10 also hits the 8 -> 9 (d_iot_ver) and 9 -> 10
        # steps, same permissive side_effect picking them up too.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.side_effect = lambda domain, dom, uid: f"sensor.{uid}"
        hass = MagicMock()
        entry = self._entry(version=7, dev_type="balco260")

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        removed = {c.args[0] for c in registry.async_remove.call_args_list}
        self.assertEqual(
            removed,
            {
                "sensor.my_device_b_ver_1",
                "sensor.my_device_d_iot_ver",
                "sensor.my_device_d_iot_serial",
                *(
                    f"sensor.my_device_{name}"
                    for name in PACK_INFO_FIELDS
                    if name != "b_ver_1"
                ),
            },
        )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_skips_a_retired_b_ver_1_sensor_that_was_never_registered(
        self, er_module
    ):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry(version=7, dev_type="balco260")

        await async_migrate_entry(hass, entry)

        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_smeter_skips_retired_b_ver_1_sensor_removal(self, er_module):
        # b_ver_1 doesn't exist on S Meter at all.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=7, dev_type="smeter")

        await async_migrate_entry(hass, entry)

        registry.async_get_entity_id.assert_not_called()
        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_removes_retired_d_iot_ver_sensor_for_an_entry_already_on_version_8(
        self, er_module
    ):
        # Not cascading from an earlier version - an entry that already sat
        # at version 8 with d_iot_ver still registered as a plain sensor.
        # Cascading 8 -> 10 also hits the 9 -> 10 step, same permissive
        # side_effect picking it up too.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.side_effect = lambda domain, dom, uid: f"sensor.{uid}"
        hass = MagicMock()
        entry = self._entry(version=8, dev_type="balco260")

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        removed = {c.args[0] for c in registry.async_remove.call_args_list}
        self.assertEqual(
            removed,
            {
                "sensor.my_device_d_iot_ver",
                "sensor.my_device_d_iot_serial",
                *(
                    f"sensor.my_device_{name}"
                    for name in PACK_INFO_FIELDS
                    if name != "b_ver_1"
                ),
            },
        )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_skips_a_retired_d_iot_ver_sensor_that_was_never_registered(
        self, er_module
    ):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry(version=8, dev_type="balco260")

        await async_migrate_entry(hass, entry)

        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_smeter_skips_retired_d_iot_ver_sensor_removal(self, er_module):
        # d_iot_ver doesn't exist on S Meter at all.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=8, dev_type="smeter")

        await async_migrate_entry(hass, entry)

        registry.async_get_entity_id.assert_not_called()
        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_removes_retired_battery_sensors_for_an_entry_already_on_version_9(
        self, er_module
    ):
        # Not cascading from an earlier version - an entry that already sat
        # at version 9 with d_iot_serial and every PACK_INFO_FIELDS name
        # (except b_ver_1, already retired at 7 -> 8) still registered as
        # plain sensors on the main device.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.side_effect = lambda domain, dom, uid: f"sensor.{uid}"
        hass = MagicMock()
        entry = self._entry(version=9, dev_type="balco260")

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        removed = {c.args[0] for c in registry.async_remove.call_args_list}
        self.assertEqual(
            removed,
            {
                "sensor.my_device_d_iot_serial",
                *(
                    f"sensor.my_device_{name}"
                    for name in PACK_INFO_FIELDS
                    if name != "b_ver_1"
                ),
            },
        )
        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_skips_a_retired_battery_sensor_that_was_never_registered(
        self, er_module
    ):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        registry.async_get_entity_id.return_value = None
        hass = MagicMock()
        entry = self._entry(version=9, dev_type="balco260")

        await async_migrate_entry(hass, entry)

        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_smeter_skips_retired_battery_sensor_removal(self, er_module):
        # d_iot_serial and PACK_INFO_FIELDS don't exist on S Meter at all.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=9, dev_type="smeter")

        await async_migrate_entry(hass, entry)

        registry.async_get_entity_id.assert_not_called()
        registry.async_remove.assert_not_called()

    @patch("custom_components.bluetti_modbus.er")
    async def test_renames_the_old_illegible_default_title(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=3, dev_type="balco260")
        # What config_flow.py's old re.sub("[^A-Za-z0-9]+", "", ...) title
        # generation would have produced for this entry's address+port.
        entry.title = "102160502"

        result = await async_migrate_entry(hass, entry)

        self.assertTrue(result)
        # The 5 -> 6 step (same cascading call) strips the address-based
        # title the 3 -> 4 step just produced down to the plain product
        # name - see its own docstring.
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry, title="Balco 260", version=10
        )

    @patch("custom_components.bluetti_modbus.er")
    async def test_does_not_rename_a_title_the_user_has_customized(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=3, dev_type="balco260")
        entry.title = "Garage Battery"

        await async_migrate_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_invalid_entry_data_skips_the_title_rename(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=3)
        entry.data = {}
        entry.title = "102160502"

        await async_migrate_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_adds_the_missing_space_for_an_entry_already_on_version_4(
        self, er_module
    ):
        # Not cascading from version 3 - an entry that already sat at
        # version 4 with the (still unspaced) "Balco260 ..." title.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=4, dev_type="balco260")
        entry.title = "Balco260 1234567890123"

        await async_migrate_entry(hass, entry)

        # The 5 -> 6 step (same cascading call) strips the serial number the
        # 4 -> 5 step just re-spaced down to the plain product name.
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry, title="Balco 260", version=10
        )

    @patch("custom_components.bluetti_modbus.er")
    async def test_drops_a_serial_suffixed_title_for_an_entry_already_on_version_5(
        self, er_module
    ):
        # Not cascading - an entry that already sat at version 5 with the
        # (already spaced) "Balco 260 <serial>" title.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=5, dev_type="balco260")
        entry.title = "Balco 260 1234567890123"

        await async_migrate_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(
            entry, title="Balco 260", version=10
        )

    @patch("custom_components.bluetti_modbus.er")
    async def test_drops_an_address_suffixed_title_for_an_entry_already_on_version_5(
        self, er_module
    ):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=5, dev_type="smeter")
        entry.title = "S Meter (10.2.1.60)"

        await async_migrate_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(
            entry, title="S Meter", version=10
        )

    @patch("custom_components.bluetti_modbus.er")
    async def test_does_not_drop_a_non_digit_suffix_the_user_added_themselves(
        self, er_module
    ):
        # "Balco 260 Garage" looks similar to the auto-generated pattern but
        # isn't pure digits after the prefix - a real user-chosen title, not
        # something this step's own old code would ever have produced.
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=5, dev_type="balco260")
        entry.title = "Balco 260 Garage"

        await async_migrate_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_invalid_entry_data_skips_the_serial_suffix_drop(self, er_module):
        registry = MagicMock()
        er_module.async_get.return_value = registry
        hass = MagicMock()
        entry = self._entry(version=5)
        entry.data = {}
        entry.title = "S Meter 12345"

        await async_migrate_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(entry, version=10)

    @patch("custom_components.bluetti_modbus.er")
    async def test_already_current_version_is_a_no_op(self, er_module):
        hass = MagicMock()
        entry = self._entry(version=10)

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
        self.assertEqual(info["model"], "Balco 260")
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


class TestPackDeviceInfo(unittest.TestCase):
    @patch("custom_components.bluetti_modbus.dr")
    def test_returns_sub_device_info_linked_to_the_main_device(self, dr_module):
        dr_module.async_get_device_id_by_identifier.return_value = "main-device-id"
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        entry.title = "My Balco260"
        hass = MagicMock()

        info = pack_device_info(hass, entry, 2)

        self.assertEqual(info["identifiers"], {(DOMAIN, "10.2.1.60-pack-2")})
        self.assertEqual(info["name"], "My Balco260 Pack 2")
        self.assertEqual(info["via_device_id"], "main-device-id")
        dr_module.async_get_device_id_by_identifier.assert_called_once_with(
            hass, (DOMAIN, "10.2.1.60"), config_entry_id="entry1"
        )

    def test_returns_none_for_invalid_entry(self):
        entry = MagicMock()
        entry.data = {}
        hass = MagicMock()

        self.assertIsNone(pack_device_info(hass, entry, 2))


class TestBatteryDeviceInfo(unittest.TestCase):
    @patch("custom_components.bluetti_modbus.dr")
    def test_returns_sub_device_info_linked_to_the_main_device(self, dr_module):
        dr_module.async_get_device_id_by_identifier.return_value = "main-device-id"
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        entry.title = "My Balco260"
        hass = MagicMock()

        info = battery_device_info(hass, entry)

        self.assertEqual(info["identifiers"], {(DOMAIN, "10.2.1.60-battery")})
        self.assertEqual(info["name"], "My Balco260 Battery")
        self.assertEqual(info["via_device_id"], "main-device-id")
        dr_module.async_get_device_id_by_identifier.assert_called_once_with(
            hass, (DOMAIN, "10.2.1.60"), config_entry_id="entry1"
        )
        # No coordinator given - same "don't overwrite what's already set"
        # guarantee as device_info()'s own docstring explains.
        self.assertNotIn("serial_number", info)
        self.assertNotIn("sw_version", info)

    @patch("custom_components.bluetti_modbus.dr")
    def test_fills_in_serial_and_firmware_once_read(self, dr_module):
        dr_module.async_get_device_id_by_identifier.return_value = "main-device-id"
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        entry.title = "My Balco260"
        hass = MagicMock()
        coordinator = MagicMock(data={"b_serial": 1234567890123, "b_ver_1": "50008.01.10"})

        info = battery_device_info(hass, entry, coordinator)

        self.assertEqual(info["serial_number"], "1234567890123")
        self.assertEqual(info["sw_version"], "BMS v50008.01.10")

    @patch("custom_components.bluetti_modbus.dr")
    def test_omits_serial_and_firmware_before_the_first_read(self, dr_module):
        dr_module.async_get_device_id_by_identifier.return_value = "main-device-id"
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        entry.title = "My Balco260"
        hass = MagicMock()
        coordinator = MagicMock(data={})

        info = battery_device_info(hass, entry, coordinator)

        self.assertNotIn("serial_number", info)
        self.assertNotIn("sw_version", info)

    def test_returns_none_for_invalid_entry(self):
        entry = MagicMock()
        entry.data = {}
        hass = MagicMock()

        self.assertIsNone(battery_device_info(hass, entry))


class TestGetUniqueId(unittest.TestCase):
    def test_without_sensor_type(self):
        self.assertEqual(get_unique_id("My Sensor Name"), "my_sensor_name")

    def test_with_sensor_type(self):
        self.assertEqual(
            get_unique_id("My Sensor Name", "sensor"), "sensor.my_sensor_name"
        )
