import unittest

from custom_components.bluetti_modbus.types import FullDeviceConfig, InitialDeviceConfig


class TestInitialDeviceConfig(unittest.TestCase):
    def test_from_dict_with_valid_data(self):
        config = InitialDeviceConfig.from_dict(
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        )
        self.assertEqual(config.address, "10.2.1.60")
        self.assertEqual(config.port, 502)
        self.assertEqual(config.dev_type, "balco260")

    def test_from_dict_missing_field_returns_none(self):
        self.assertIsNone(InitialDeviceConfig.from_dict({"address": "10.2.1.60"}))

    def test_from_dict_wrong_type_returns_none(self):
        self.assertIsNone(
            InitialDeviceConfig.from_dict(
                {"address": "10.2.1.60", "port": "not-an-int", "name": "n", "type": "t"}
            )
        )

    def test_as_dict_round_trips(self):
        config = InitialDeviceConfig("10.2.1.60", 502, "n", "balco260")
        self.assertEqual(
            config.as_dict,
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"},
        )

    def test_serial_defaults_to_none_and_is_omitted_from_as_dict(self):
        config = InitialDeviceConfig("10.2.1.60", 502, "n", "smeter")
        self.assertIsNone(config.serial)
        self.assertNotIn("serial", config.as_dict)

    def test_as_dict_includes_serial_when_given(self):
        config = InitialDeviceConfig(
            "10.2.1.60", 502, "n", "smeter", serial="1234567890123"
        )
        self.assertEqual(
            config.as_dict,
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "n",
                "type": "smeter",
                "serial": "1234567890123",
            },
        )

    def test_from_dict_recovers_the_serial(self):
        config = InitialDeviceConfig.from_dict(
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "n",
                "type": "smeter",
                "serial": "1234567890123",
            }
        )
        self.assertEqual(config.serial, "1234567890123")

    def test_from_dict_defaults_the_serial_to_none_when_absent(self):
        config = InitialDeviceConfig.from_dict(
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        )
        self.assertIsNone(config.serial)

    def test_firmware_version_defaults_to_none_and_is_omitted_from_as_dict(self):
        config = InitialDeviceConfig("10.2.1.60", 502, "n", "smeter")
        self.assertIsNone(config.firmware_version)
        self.assertNotIn("firmware_version", config.as_dict)

    def test_as_dict_includes_firmware_version_when_given(self):
        config = InitialDeviceConfig(
            "10.2.1.60", 502, "n", "smeter", firmware_version="V300510106"
        )
        self.assertEqual(
            config.as_dict,
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "n",
                "type": "smeter",
                "firmware_version": "V300510106",
            },
        )

    def test_from_dict_recovers_the_firmware_version(self):
        config = InitialDeviceConfig.from_dict(
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "n",
                "type": "smeter",
                "firmware_version": "V300510106",
            }
        )
        self.assertEqual(config.firmware_version, "V300510106")

    def test_from_dict_defaults_the_firmware_version_to_none_when_absent(self):
        config = InitialDeviceConfig.from_dict(
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        )
        self.assertIsNone(config.firmware_version)


class TestFullDeviceConfig(unittest.TestCase):
    def test_from_dict_with_valid_data(self):
        config = FullDeviceConfig.from_dict(
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        )
        self.assertEqual(config.address, "10.2.1.60")
        self.assertEqual(config.port, 502)
        self.assertEqual(config.name, "n")
        self.assertEqual(config.dev_type, "balco260")

    def test_from_dict_invalid_data_returns_none(self):
        self.assertIsNone(FullDeviceConfig.from_dict({}))

    def test_from_dict_recovers_the_serial(self):
        config = FullDeviceConfig.from_dict(
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "n",
                "type": "smeter",
                "serial": "1234567890123",
            }
        )
        self.assertEqual(config.serial, "1234567890123")

    def test_from_dict_defaults_the_serial_to_none_when_absent(self):
        config = FullDeviceConfig.from_dict(
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        )
        self.assertIsNone(config.serial)

    def test_from_dict_recovers_the_firmware_version(self):
        config = FullDeviceConfig.from_dict(
            {
                "address": "10.2.1.60",
                "port": 502,
                "name": "n",
                "type": "smeter",
                "firmware_version": "V300510106",
            }
        )
        self.assertEqual(config.firmware_version, "V300510106")

    def test_from_dict_defaults_the_firmware_version_to_none_when_absent(self):
        config = FullDeviceConfig.from_dict(
            {"address": "10.2.1.60", "port": 502, "name": "n", "type": "balco260"}
        )
        self.assertIsNone(config.firmware_version)
