"""The built-in battery's child device, against Home Assistant's real registries.

The other tests mock the registries; the conversion of an existing battery
device into a child, and what an existing entity keeps through it, only
happen in the real ones.
"""

import logging
import tempfile
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import frame, restore_state, translation
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.bluetti_modbus import async_setup_entry
from custom_components.bluetti_modbus.const import DOMAIN
from custom_components.bluetti_modbus.coordinator import PollingCoordinator
from custom_components.bluetti_modbus.sensor import async_setup_entry as sensor_setup
from custom_components.bluetti_modbus.types import FullDeviceConfig

ADDRESS = "10.2.1.60"
SERIAL = 2611110033917

# What a Balco 260 answers, as far as these tests look.
BALCO260_DATA = {
    "d_serial": SERIAL,
    "d_iot_ver": "50012.01.19",
    "d_ver_arm": "50011.01.12",
    "d_ver_dsp": "50014.01.10",
    "b_ver_count": 1,
    "b_ver_1": "50008.01.10",
    "b_serial": 2611110012345,
    "b_v": 53.2,
    "b_c": -1.5,
    "b_soc": 80,
    "b_soh": 100,
    "b_cycle_count": 12,
    "b_cell_count": 16,
    "b_ntc_count": 4,
    "b_i_e": 1000,
    "b_o_e": 900,
    "b_soc_total": 80,
}

# The built-in battery's readings Home Assistant's built-in bluetti_modbus
# puts on the child device, with the names they get there.
BATTERY_ENTITY_NAMES = {
    "b_v": "Voltage",
    "b_c": "Current",
    "b_soc": "SoC",
    "b_soh": "SoH",
    "b_cycle_count": "Cycle Count",
    "b_cell_count": "Cell Count",
    "b_ntc_count": "Temperature Sensor Count",
    "b_i_e": "Total Charged Energy",
    "b_o_e": "Total Discharged Energy",
}


class _RealRegistries(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._config_dir = tempfile.TemporaryDirectory()
        hass = HomeAssistant(self._config_dir.name)
        hass.config.language = "en"
        frame.async_setup(hass)
        # Its warning that a custom integration is loaded, on every test.
        logging.getLogger("homeassistant.loader").setLevel(logging.ERROR)
        loader.async_setup(hass)
        hass.config_entries = ConfigEntries(hass, {})
        await hass.config_entries.async_initialize()
        dr.async_setup(hass)
        for registry in (ar, fr, lr, dr, er):
            await registry.async_load(hass, load_empty=True)
        await restore_state.async_load(hass, load_empty=True)
        await translation.async_load_integrations(hass, {DOMAIN})
        self.hass = hass
        self.devices = dr.async_get(hass)
        self.entities = er.async_get(hass)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self._config_dir.cleanup()

    def _entry(self, dev_type="balco260", title="Balco 260"):
        entry = ConfigEntry(
            data={"address": ADDRESS, "port": 502, "name": "n", "type": dev_type},
            discovery_keys={},
            domain=DOMAIN,
            minor_version=1,
            options={},
            source="user",
            subentries_data=None,
            title=title,
            unique_id=str(SERIAL),
            version=27,
        )
        self.hass.config_entries._entries[entry.entry_id] = entry
        return entry

    async def _setup(self, entry, data):
        """Set the entry up with its sensor platform, the unit answering data."""
        coordinator = MagicMock(spec=PollingCoordinator)
        coordinator.hass = self.hass
        coordinator.config_entry = entry
        coordinator.config = FullDeviceConfig.from_dict(entry.data)
        coordinator.data = data
        coordinator.network = None
        coordinator.last_update_success = True
        coordinator.async_config_entry_first_refresh = AsyncMock()

        async def forward(entry, platforms):
            platform = EntityPlatform(
                hass=self.hass,
                logger=logging.getLogger(__name__),
                domain="sensor",
                platform_name=DOMAIN,
                platform=SimpleNamespace(async_setup_entry=sensor_setup),
                scan_interval=timedelta(seconds=30),
                entity_namespace=None,
            )
            self.assertTrue(await platform.async_setup_entry(entry))
            await self.hass.async_block_till_done()

        with (
            patch(
                "custom_components.bluetti_modbus.PollingCoordinator",
                return_value=coordinator,
            ),
            patch(
                "custom_components.bluetti_modbus.NetworkStatusCoordinator",
                return_value=MagicMock(async_refresh=AsyncMock()),
            ),
            patch.object(self.hass.config_entries, "async_forward_entry_setups", forward),
        ):
            self.assertTrue(await async_setup_entry(self.hass, entry))

    def _main_device(self, entry):
        device = self.devices.async_get_device_by_identifier((DOMAIN, ADDRESS), entry.entry_id)
        assert device is not None
        return device

    def _battery(self, entry):
        return self.devices.async_get_child_device_by_identifier(
            (DOMAIN, f"{SERIAL}_battery"), entry.entry_id
        )

    def _entity(self, field):
        entity_id = self.entities.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_{field}")
        assert entity_id is not None, field
        entity = self.entities.async_get(entity_id)
        assert entity is not None
        return entity


class TestBuiltInBatteryChildDevice(_RealRegistries):
    async def test_the_built_in_battery_is_a_child_of_the_station(self):
        entry = self._entry()

        await self._setup(entry, BALCO260_DATA)

        main = self._main_device(entry)
        battery = self._battery(entry)
        self.assertIsNotNone(battery)
        self.assertEqual(battery.parent_device_id, main.id)
        self.assertEqual(battery.name, "Built-in battery")
        self.assertEqual(
            battery.identifiers,
            {(DOMAIN, f"{ADDRESS}-battery"), (DOMAIN, f"{SERIAL}_battery")},
        )
        for field, name in BATTERY_ENTITY_NAMES.items():
            with self.subTest(field=field):
                entity = self._entity(field)
                self.assertEqual(entity.device_id, battery.id)
                self.assertEqual(entity.original_name, name)
        # The total over every battery stays on the station.
        self.assertEqual(self._entity("b_soc_total").device_id, main.id)

    async def test_a_new_install_names_the_entity_after_the_child_device(self):
        entry = self._entry()

        await self._setup(entry, BALCO260_DATA)

        self.assertEqual(
            self._entity("b_v").entity_id, "sensor.balco_260_built_in_battery_voltage"
        )
        self.assertEqual(
            self.hass.states.get("sensor.balco_260_built_in_battery_voltage").name,
            "Built-in battery Voltage",
        )

    async def test_the_station_carries_the_bms_version(self):
        for data, sw_version in (
            (
                BALCO260_DATA,
                "IoT v50012.01.19, ARM v50011.01.12, DSP v50014.01.10, BMS v50008.01.10",
            ),
            (
                {k: v for k, v in BALCO260_DATA.items() if k != "b_ver_1"},
                "IoT v50012.01.19, ARM v50011.01.12, DSP v50014.01.10",
            ),
        ):
            with self.subTest(sw_version=sw_version):
                entry = self._entry()

                await self._setup(entry, data)

                self.assertEqual(self._main_device(entry).sw_version, sw_version)
                self.devices.async_remove_device(self._main_device(entry).id)

    async def test_the_old_battery_device_becomes_the_child(self):
        entry = self._entry()
        area = ar.async_get(self.hass).async_create("Garage")
        main = self.devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}, name="Balco 260"
        )
        old = self.devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{ADDRESS}-battery")},
            name="Balco 260 Battery",
            model="Balco 260",
            serial_number="2611110012345",
            sw_version="BMS v50008.01.10",
            via_device_id=main.id,
        )
        self.devices.async_update_device(old.id, area_id=area.id, name_by_user="House battery")
        voltage = self.entities.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{SERIAL}_b_v",
            config_entry=entry,
            device_id=old.id,
            suggested_object_id="balco_260_battery_battery_voltage",
        )
        # Home Assistant restarts: the devices are no longer the live ones of
        # a setup.
        self.devices.async_config_entry_unloaded(entry.entry_id)

        await self._setup(entry, BALCO260_DATA)

        battery = self._battery(entry)
        self.assertIsNotNone(battery)
        self.assertEqual(battery.id, old.id)
        self.assertEqual(battery.parent_device_id, main.id)
        self.assertEqual(battery.area_id, area.id)
        self.assertEqual(battery.name_by_user, "House battery")
        self.assertEqual(
            battery.identifiers,
            {(DOMAIN, f"{ADDRESS}-battery"), (DOMAIN, f"{SERIAL}_battery")},
        )
        # The entity keeps its entity_id, and with it its history.
        entity = self._entity("b_v")
        self.assertEqual(entity.entity_id, voltage.entity_id)
        self.assertEqual(entity.device_id, battery.id)
        self.assertIsNone(self.entities.async_get("sensor.balco_260_built_in_battery_voltage"))

    async def test_removing_the_station_removes_its_battery(self):
        entry = self._entry()
        await self._setup(entry, BALCO260_DATA)
        battery = self._battery(entry)
        self.assertIsNotNone(battery)

        self.devices.async_remove_device(self._main_device(entry).id)

        self.assertIsNone(self._battery(entry))

    async def test_an_ep2000_battery_stays_a_device_of_its_own(self):
        entry = self._entry("ep2000", "EP2000")

        await self._setup(
            entry,
            {**BALCO260_DATA, "b_type": "HV800", "b_cell_count": 96, "b_ver_count": 3},
        )

        main = self._main_device(entry)
        self.assertIsNone(self._battery(entry))
        battery = self.devices.async_get_device_by_identifier(
            (DOMAIN, f"{ADDRESS}-battery"), entry.entry_id
        )
        self.assertIsNotNone(battery)
        self.assertEqual(battery.via_device_id, main.id)
        self.assertEqual(battery.model, "HV800 + 3 × B700")
        self.assertEqual(battery.serial_number, "2611110012345")
        self.assertEqual(self._entity("b_v").device_id, battery.id)
        # Its firmware is on its own page, not the station's.
        self.assertNotIn("BMS", main.sw_version)


PV_DATA = {
    **BALCO260_DATA,
    "pv_dc_count": 2,
    "pv_ac_count": 0,
    "pv_i_p_total": 300,
    **{f"pv_{n}_i_{k}": 1 for n in (1, 2, 3, 4) for k in ("p", "v", "c")},
}


class TestPvInputChildDevices(_RealRegistries):
    def _pv_input(self, entry, n):
        return self.devices.async_get_child_device_by_identifier(
            (DOMAIN, f"{SERIAL}_pv_{n}"), entry.entry_id
        )

    async def test_each_pv_input_is_a_child_of_the_station(self):
        entry = self._entry()

        await self._setup(entry, PV_DATA)

        main = self._main_device(entry)
        for n in (1, 2):
            with self.subTest(input=n):
                pv_input = self._pv_input(entry, n)
                self.assertIsNotNone(pv_input)
                self.assertEqual(pv_input.parent_device_id, main.id)
                self.assertEqual(pv_input.name, f"PV {n}")
                self.assertEqual(
                    pv_input.identifiers,
                    {(DOMAIN, f"{ADDRESS}-pv-{n}"), (DOMAIN, f"{SERIAL}_pv_{n}")},
                )
                for field, name in (
                    (f"pv_{n}_i_p", "Input Power"),
                    (f"pv_{n}_i_v", "Input Voltage"),
                    (f"pv_{n}_i_c", "Input Current"),
                    (f"pv_{n}_i_type", "Input Type"),
                ):
                    entity = self._entity(field)
                    self.assertEqual(entity.device_id, pv_input.id, field)
                    self.assertEqual(entity.original_name, name, field)
        # The totals stay on the station.
        for field in ("pv_i_p_total", "pv_dc_count", "pv_ac_count"):
            self.assertEqual(self._entity(field).device_id, main.id, field)

    async def test_a_new_install_keeps_todays_entity_id(self):
        entry = self._entry()

        await self._setup(entry, PV_DATA)

        self.assertEqual(self._entity("pv_1_i_p").entity_id, "sensor.balco_260_pv_1_input_power")

    async def test_inputs_beyond_the_reported_count_have_no_entity_or_device(self):
        entry = self._entry()

        await self._setup(entry, PV_DATA)

        for n in (3, 4):
            with self.subTest(input=n):
                self.assertIsNone(self._pv_input(entry, n))
                self.assertIsNone(
                    self.entities.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_pv_{n}_i_p")
                )

    async def test_what_was_registered_beyond_the_count_is_removed(self):
        # 3.2.0-rc.1 gave every input a device; the versions before it put
        # the inputs' entities, disabled, on the station.
        entry = self._entry()
        main = self.devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}, name="Balco 260"
        )
        pv_3 = self.devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{ADDRESS}-pv-3")}, name="PV 3"
        )
        on_pv_3 = self.entities.async_get_or_create(
            "sensor", DOMAIN, f"{SERIAL}_pv_3_i_p", config_entry=entry, device_id=pv_3.id
        )
        on_station = self.entities.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{SERIAL}_pv_4_i_p",
            config_entry=entry,
            device_id=main.id,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )
        self.devices.async_config_entry_unloaded(entry.entry_id)

        await self._setup(entry, PV_DATA)

        self.assertIsNone(self.devices.async_get(pv_3.id))
        self.assertIsNone(self.entities.async_get(on_pv_3.entity_id))
        self.assertIsNone(self.entities.async_get(on_station.entity_id))
        self.assertIsNotNone(self._pv_input(entry, 2))

    async def test_an_existing_entity_moves_to_its_input_as_it_was(self):
        entry = self._entry()
        main = self.devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}, name="Balco 260"
        )
        power = self.entities.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{SERIAL}_pv_1_i_p",
            config_entry=entry,
            device_id=main.id,
            suggested_object_id="balco_260_pv_1_input_power",
        )
        self.devices.async_config_entry_unloaded(entry.entry_id)

        await self._setup(entry, PV_DATA)

        entity = self._entity("pv_1_i_p")
        self.assertEqual(entity.entity_id, power.entity_id)
        self.assertEqual(entity.device_id, self._pv_input(entry, 1).id)

    async def test_an_ep2000_names_its_inputs_after_its_mppts(self):
        entry = self._entry("ep2000", "EP2000")

        await self._setup(
            entry,
            {**PV_DATA, "b_type": "HV800", "b_cell_count": 96, "b_ver_count": 3},
        )

        for n in (1, 2):
            with self.subTest(input=n):
                self.assertEqual(self._pv_input(entry, n).name, f"MPPT {n}")
        self.assertIsNone(self._pv_input(entry, 3))
        self.assertEqual(self._entity("pv_1_i_p").entity_id, "sensor.ep2000_mppt_1_input_power")
