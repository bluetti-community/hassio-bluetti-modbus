import json
import re
import unittest
from pathlib import Path

from custom_components.bluetti_modbus.const import (
    DEVICE_TYPE_DISPLAY_NAMES,
    FIELDS_NOT_SHOWN,
    FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO,
    FIELDS_SHOWN_VIA_BINARY_SENSOR,
    FIELDS_SHOWN_VIA_DEVICE_INFO,
    FIELDS_SHOWN_VIA_NUMBER,
    FIELDS_SHOWN_VIA_SELECT,
    FIELDS_SHOWN_VIA_SWITCH,
    SMETER_PHASE_FIELDS,
)
from custom_components.bluetti_modbus.sensor import (
    _CHILD_BATTERY_TRANSLATION_KEYS,
    PV_INPUT_FIELD,
    PV_INPUT_TRANSLATION_KEYS,
    _snake_case,
)
from custom_components.bluetti_modbus.vendor.bluetti_modbus_lib import get_device

_TRANSLATIONS_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "bluetti_modbus"
    / "translations"
    / "en.json"
)

# Every language the integration ships, English first.
_LANGUAGES = ("en", *sorted(p.stem for p in _TRANSLATIONS_PATH.parent.glob("*.json") if p.stem != "en"))


def _translations(lang):
    return json.loads(_TRANSLATIONS_PATH.with_name(f"{lang}.json").read_text())


def _flatten(node, prefix=""):
    if not isinstance(node, dict):
        return {prefix: node}
    flat = {}
    for key, value in node.items():
        flat.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
    return flat


# Every device type the integration knows, gated or not: a gated model is
# what an owner tests from a prerelease, and an untranslated field there
# shows the device's own name in place of the entity's.
_DEV_TYPES = tuple(DEVICE_TYPE_DISPLAY_NAMES)


# An S Meter's per-phase fields.
_PHASE_FIELDS = {name for names in SMETER_PHASE_FIELDS.values() for name in names}


def _sensor_key(name):
    """The translation key a sensor field is named by (sensor.py)."""
    pv_input = PV_INPUT_FIELD.match(name)
    return PV_INPUT_TRANSLATION_KEYS[pv_input.group(2)] if pv_input else name


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
        select_translated = set(translations["entity"].get("select", {}))

        missing = []
        for dev_type in _DEV_TYPES:
            device = get_device(dev_type)
            assert device is not None  # _DEV_TYPES are all real device types
            for name in device.field_names():
                if name in FIELDS_NOT_SHOWN:
                    continue
                if name in FIELDS_SHOWN_VIA_BINARY_SENSOR:
                    continue
                if name in FIELDS_SHOWN_VIA_DEVICE_INFO:
                    continue
                if name in FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO:
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
                if name in FIELDS_SHOWN_VIA_SELECT and field.writable:
                    if name not in select_translated:
                        missing.append(f"{dev_type}.{name} (select)")
                    continue
                # Named by device class on its phase's device.
                if name in _PHASE_FIELDS:
                    continue
                if _sensor_key(name) not in sensor_translated:
                    missing.append(f"{dev_type}.{name} (sensor)")

        self.assertEqual(missing, [])


class TestSelectOptionsHaveALabel(unittest.TestCase):
    """A select option with no state label shows its raw key."""

    def test_every_option_has_a_label_in_every_language(self):
        missing = []
        for dev_type in _DEV_TYPES:
            device = get_device(dev_type)
            assert device is not None
            for name in FIELDS_SHOWN_VIA_SELECT:
                field = device.get_field(name)
                if field is None or not field.writable:
                    continue
                for lang in _LANGUAGES:
                    states = _translations(lang)["entity"]["select"][name]["state"]
                    missing.extend(
                        f"{lang}: {dev_type}.{name}.{_snake_case(member.name)}"
                        for member in field.convert
                        if _snake_case(member.name) not in states
                    )
        self.assertEqual(missing, [])


class TestWorkingModeStatesHaveALabel(unittest.TestCase):
    """The Apex 300's working mode is an enum sensor: every state needs a label."""

    def test_every_state_has_a_label_in_every_language(self):
        field = get_device("pa030").get_field("d_working_mode")
        assert field is not None
        missing = [
            f"{lang}: {_snake_case(member.name)}"
            for lang in _LANGUAGES
            for member in field.convert
            if _snake_case(member.name)
            not in _translations(lang)["entity"]["sensor"]["d_working_mode"]["state"]
        ]
        self.assertEqual(missing, [])


class TestNoDuplicateSensorNames(unittest.TestCase):
    """Regression test for a real reported bug: pv_ac_p ("Total PV to AC
    power") and pv_ac_p_local ("PV to AC power, this inverter") both
    translated to the plain "PV AC Power" - HA silently disambiguated with
    a "_2" suffix on whichever field got created second, which read as a
    mystery entity rather than the two genuinely different readings they
    are (same bug hit pv_ac_e/pv_ac_e_local)."""

    def test_every_sensor_field_has_a_distinct_translated_name(self):
        for lang in _LANGUAGES:
            with self.subTest(lang=lang):
                self._assert_distinct_names(_translations(lang)["entity"]["sensor"])

    def _assert_distinct_names(self, sensor_names):
        duplicates = []
        for dev_type in _DEV_TYPES:
            device = get_device(dev_type)
            assert device is not None  # _DEV_TYPES are all real device types
            names_seen: dict[str, str] = {}
            for name in device.field_names():
                if name in FIELDS_NOT_SHOWN:
                    continue
                if name in FIELDS_SHOWN_VIA_BINARY_SENSOR:
                    continue
                if name in FIELDS_SHOWN_VIA_DEVICE_INFO:
                    continue
                if name in FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO:
                    continue
                field = device.get_field(name)
                assert field is not None  # field_names() only yields real fields
                if name in FIELDS_SHOWN_VIA_NUMBER and field.writable:
                    continue
                if name in FIELDS_SHOWN_VIA_SWITCH and field.writable:
                    continue
                # One name per PV input, each on its own device.
                if PV_INPUT_FIELD.match(name):
                    continue
                # One device per phase, its readings named by device class.
                if name in _PHASE_FIELDS:
                    continue
                entry = sensor_names.get(name)
                if entry is None:
                    continue  # already reported by the coverage test above
                display_name = entry["name"]
                if display_name in names_seen:
                    duplicates.append(
                        f"{dev_type}: {names_seen[display_name]!r} and {name!r} "
                        f"both translate to {display_name!r}"
                    )
                else:
                    names_seen[display_name] = name

        self.assertEqual(duplicates, [])


class TestPvInputNames(unittest.TestCase):
    """Each PV input's child device and its entities (sensor.py)."""

    def test_the_devices_and_keys_have_a_name_in_every_language(self):
        for lang in _LANGUAGES:
            translations = _translations(lang)
            for device in ("pv_input", "mppt"):
                self.assertIn("{input}", translations["device"][device]["name"], lang)
            sensor = translations["entity"]["sensor"]
            self.assertEqual(set(PV_INPUT_TRANSLATION_KEYS.values()) - set(sensor), set(), lang)
            self.assertEqual(
                set(sensor["input_type"]["state"]),
                {"reserve", "car", "adapter", "other", "dc_pv", "ac_pv"},
                lang,
            )


class TestPhaseNames(unittest.TestCase):
    """An S Meter phase's child device (sensor.py)."""

    def test_the_device_has_a_name_in_every_language(self):
        for lang in _LANGUAGES:
            translations = _translations(lang)
            self.assertIn("{phase}", translations["device"]["phase"]["name"], lang)

    def test_the_readings_have_no_name_of_their_own(self):
        # Their device class names them: a key left behind would be unused.
        for lang in _LANGUAGES:
            sensor = _translations(lang)["entity"]["sensor"]
            self.assertEqual(_PHASE_FIELDS & set(sensor), set(), lang)


class TestBuiltInBatteryNames(unittest.TestCase):
    """The built-in battery's child device and its entities (sensor.py)."""

    def test_the_child_device_and_its_keys_have_a_name_in_every_language(self):
        keys = {key for key in _CHILD_BATTERY_TRANSLATION_KEYS.values() if key is not None}
        for lang in _LANGUAGES:
            translations = _translations(lang)
            self.assertIn("name", translations["device"]["built_in_battery"], lang)
            self.assertEqual(keys - set(translations["entity"]["sensor"]), set(), lang)

    def test_the_child_device_names_are_distinct(self):
        for lang in _LANGUAGES:
            sensor = _translations(lang)["entity"]["sensor"]
            names = [
                sensor[key]["name"]
                for key in _CHILD_BATTERY_TRANSLATION_KEYS.values()
                if key is not None
            ]
            self.assertEqual(len(names), len(set(names)), lang)


class TestEveryLanguageMatchesEnglish(unittest.TestCase):
    """A language that misses a key shows English there; one with another
    placeholder fails to format the message at all."""

    def test_every_language_has_exactly_the_english_keys(self):
        english = set(_flatten(_translations("en")))
        for lang in _LANGUAGES[1:]:
            with self.subTest(lang=lang):
                self.assertEqual(set(_flatten(_translations(lang))) ^ english, set())

    def test_every_language_keeps_the_english_placeholders(self):
        english = _flatten(_translations("en"))
        for lang in _LANGUAGES[1:]:
            for key, text in _flatten(_translations(lang)).items():
                with self.subTest(lang=lang, key=key):
                    self.assertEqual(
                        sorted(re.findall(r"\{\w+\}", text)),
                        sorted(re.findall(r"\{\w+\}", english[key])),
                    )
