import unittest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

from custom_components.bluetti_modbus.field_metadata import FIELD_METADATA, metadata_for


class TestMetadataFor(unittest.TestCase):
    def test_known_power_field(self):
        metadata = metadata_for("ac_o_p_total")
        self.assertEqual(metadata.device_class, SensorDeviceClass.POWER)
        self.assertEqual(metadata.state_class, SensorStateClass.MEASUREMENT)
        self.assertIsNone(metadata.category)

    def test_known_diagnostic_energy_field(self):
        metadata = metadata_for("b_i_e")
        self.assertEqual(metadata.device_class, SensorDeviceClass.ENERGY)
        self.assertEqual(metadata.state_class, SensorStateClass.TOTAL_INCREASING)
        self.assertEqual(metadata.category, EntityCategory.DIAGNOSTIC)

    def test_only_b_soc_is_device_class_battery_not_b_soc_total(self):
        # Real hardware regression: with two device_class=BATTERY sensors on
        # one device, HA's Devices-page summary column picked b_soc_total
        # (0% on a bare Balco260 with no BC260 pack) instead of b_soc (the
        # correct, always-populated 77% reading at the same moment). Only
        # one sensor per device may claim to be "the" battery.
        self.assertEqual(metadata_for("b_soc").device_class, SensorDeviceClass.BATTERY)
        self.assertIsNone(metadata_for("b_soc_total").device_class)
        self.assertEqual(metadata_for("b_soc_total").state_class, SensorStateClass.MEASUREMENT)

    def test_known_config_field(self):
        metadata = metadata_for("b_soc_high")
        self.assertIsNone(metadata.device_class)
        self.assertIsNone(metadata.state_class)
        self.assertEqual(metadata.category, EntityCategory.CONFIG)

    def test_smeter_timestamp_field_is_disabled_by_default(self):
        # 55112 ("Unix timestamp") is the meter's own internal clock reading -
        # not something anyone watches day to day, so it starts disabled
        # rather than adding to entity clutter.
        metadata = metadata_for("d_timestamp")
        self.assertEqual(metadata.category, EntityCategory.DIAGNOSTIC)
        self.assertFalse(metadata.enabled_by_default)

    def test_local_inverter_fields_are_disabled_by_default(self):
        # Real-hardware testing (2026-09-06) found these 5 "(Single)"/
        # per-inverter Balco260 fields permanently read a clean, error-free
        # 0, while their _total/phase-1 counterparts (same measurement)
        # demonstrably changed in real time on the same live device - not a
        # width/sign decode bug, since both registers of each pair match
        # what the official spec declares. Flagged with BLUETTI support, not
        # yet confirmed either way - disabled rather than removed, since a
        # genuinely multi-inverter Balco260 might need them if this turns
        # out to work there.
        for field in (
            "ac_o_e_local",
            "ac_o_p_local",
            "g_i_e_local",
            "g_i_p_local",
            "g_o_e_local",
        ):
            metadata = metadata_for(field)
            self.assertFalse(metadata.enabled_by_default, field)

    def test_never_populated_balco260_fields_are_disabled_by_default(self):
        # 11 days of continuous data on a real Balco260 (2026-09-05 to
        # 2026-09-15): a flat 0 day and night while the reading each stands
        # for was available elsewhere (_total counterparts, raw register
        # dump). Reported to BLUETTI; disabled rather than removed.
        for field, device_class in (
            ("b_t_avg", SensorDeviceClass.TEMPERATURE),
            ("b_time_to_full", SensorDeviceClass.DURATION),
            ("b_time_to_empty", SensorDeviceClass.DURATION),
            ("d_self_consumption", None),
            ("pv_ac_p_local", SensorDeviceClass.POWER),
            ("pv_ac_e_local", SensorDeviceClass.ENERGY),
            ("pv_i_e_local", SensorDeviceClass.ENERGY),
        ):
            metadata = metadata_for(field)
            self.assertFalse(metadata.enabled_by_default, field)
            # Disabled, not stripped: the classification survives for
            # whoever re-enables one.
            self.assertEqual(metadata.device_class, device_class, field)
            self.assertIsNotNone(metadata.state_class, field)

    def test_the_working_totals_behind_those_fields_stay_enabled(self):
        for field in ("b_time_to_full_total", "b_time_to_empty_total", "pv_i_e_total", "pv_ac_e", "pv_ac_p"):
            self.assertTrue(metadata_for(field).enabled_by_default, field)

    def test_switch_field_has_no_metadata(self):
        metadata = metadata_for("ac_o_switch")
        self.assertIsNone(metadata.device_class)
        self.assertIsNone(metadata.state_class)
        self.assertIsNone(metadata.category)

    def test_unknown_field_returns_metadata_less_default(self):
        metadata = metadata_for("not_a_real_field")
        self.assertIsNone(metadata.device_class)
        self.assertIsNone(metadata.state_class)
        self.assertIsNone(metadata.category)

    def test_every_entry_has_at_least_one_attribute_or_is_a_deliberate_switch(self):
        # Guards against a copy-paste FieldMetadata() placeholder that should
        # have carried real metadata.
        deliberately_bare = {"ac_o_switch", "g_i_switch", "g_o_switch"}
        for name, metadata in FIELD_METADATA.items():
            if name in deliberately_bare:
                continue
            self.assertTrue(
                metadata.device_class or metadata.state_class or metadata.category,
                f"{name} has no metadata at all - is that intentional?",
            )
