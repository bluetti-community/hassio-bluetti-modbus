import json
import unittest
from pathlib import Path

from custom_components.bluetti_modbus.const import (
    FIELDS_SHOWN_VIA_BINARY_SENSOR,
    FIELDS_SHOWN_VIA_DEVICE_INFO,
    FIELDS_SHOWN_VIA_NUMBER,
    FIELDS_SHOWN_VIA_SWITCH,
)
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import get_device

_TRANSLATIONS_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "bluetti_modbus"
    / "translations"
    / "en.json"
)

# Only device types actually reachable via config_flow.py's dropdown - not
# EP2000, which isn't offered there yet.
_DEV_TYPES = ("balco260", "smeter")


class TestTranslationsCoverAllShownFields(unittest.TestCase):
    """Regression test for a real reported bug: a field with no translation
    entry displays with no name at all (has_entity_name=True resolves to no
    name, and the frontend falls back to showing the device's own name for
    every affected entity - see the fix that added 65 missing Balco 260
    entries, spotted this way on a real installation)."""

    def test_every_shown_field_has_a_translation(self):
        translations = json.loads(_TRANSLATIONS_PATH.read_text())
        sensor_translated = set(translations["entity"]["sensor"])
        number_translated = set(translations["entity"].get("number", {}))
        switch_translated = set(translations["entity"].get("switch", {}))

        missing = []
        for dev_type in _DEV_TYPES:
            device = get_device(dev_type)
            assert device is not None  # _DEV_TYPES are all real device types
            for name in device.field_names():
                if name in FIELDS_SHOWN_VIA_BINARY_SENSOR:
                    continue
                if name in FIELDS_SHOWN_VIA_DEVICE_INFO:
                    continue
                field = device.get_field(name)
                assert field is not None  # field_names() only yields real fields
                if name in FIELDS_SHOWN_VIA_NUMBER and field.writable:
                    if name not in number_translated:
                        missing.append(f"{dev_type}.{name} (number)")
                    continue
                if name in FIELDS_SHOWN_VIA_SWITCH and field.writable:
                    if name not in switch_translated:
                        missing.append(f"{dev_type}.{name} (switch)")
                    continue
                if name not in sensor_translated:
                    missing.append(f"{dev_type}.{name} (sensor)")

        self.assertEqual(missing, [])
