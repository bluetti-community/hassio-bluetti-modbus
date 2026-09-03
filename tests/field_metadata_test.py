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
        # (0% on a bare Balco260 with no BC200 pack) instead of b_soc (the
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
