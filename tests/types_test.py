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
