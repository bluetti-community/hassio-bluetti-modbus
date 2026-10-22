import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.bluetti_modbus import async_setup_entry, async_unload_entry
from custom_components.bluetti_modbus.binary_sensor import (
    NETWORK_FLAGS,
    BluettiCloudConnectionBinarySensor,
    BluettiNetworkBinarySensor,
)
from custom_components.bluetti_modbus.binary_sensor import (
    async_setup_entry as binary_sensor_setup,
)
from custom_components.bluetti_modbus.coordinator import PollingCoordinator
from custom_components.bluetti_modbus.network import (
    NETWORK_STATUS_SCAN_INTERVAL,
    NetworkStatusCoordinator,
)
from custom_components.bluetti_modbus.sensor import BluettiWifiSignalSensor
from custom_components.bluetti_modbus.sensor import async_setup_entry as sensor_setup
from custom_components.bluetti_modbus.web_page import NO_NETWORK_STATUS, NetworkStatus


def _network(data):
    network = MagicMock(spec=NetworkStatusCoordinator)
    network.data = data
    return network


class TestNetworkStatusCoordinator(unittest.IsolatedAsyncioTestCase):
    async def test_reads_the_web_page_every_few_minutes(self):
        hass = MagicMock()
        with patch(
            "custom_components.bluetti_modbus.network.async_query_network_status",
            new=AsyncMock(return_value=NetworkStatus(-70, True, True)),
        ) as query:
            coordinator = NetworkStatusCoordinator(hass, MagicMock(), "10.2.1.128")
            result = await coordinator._async_update_data()

        self.assertEqual(result, NetworkStatus(-70, True, True))
        query.assert_awaited_once_with(hass, "10.2.1.128")
        self.assertEqual(coordinator.update_interval, NETWORK_STATUS_SCAN_INTERVAL)


    async def test_logs_once_when_the_page_stops_answering_and_once_when_it_is_back(self):
        failed = NO_NETWORK_STATUS._replace(failure="TimeoutError")
        answers = [failed, failed, NetworkStatus(-70, True, True), NetworkStatus(-71, True, True)]
        with patch(
            "custom_components.bluetti_modbus.network.async_query_network_status",
            new=AsyncMock(side_effect=answers),
        ):
            coordinator = NetworkStatusCoordinator(MagicMock(), MagicMock(), "10.2.1.128")
            with self.assertLogs(coordinator.logger, "INFO") as logs:
                for _ in answers:
                    await coordinator._async_update_data()

        self.assertEqual(len(logs.output), 2)
        self.assertIn("does not answer the network status (TimeoutError)", logs.output[0])
        self.assertIn("answers the network status again", logs.output[1])


class TestEntities(unittest.TestCase):
    def test_the_signal_sensor_shows_the_rssi_in_dbm(self):
        sensor = BluettiWifiSignalSensor(_network(NetworkStatus(-75, True, True)), {}, "uid")

        self.assertEqual(sensor.native_value, -75)
        self.assertEqual(sensor.native_unit_of_measurement, "dBm")
        self.assertEqual(sensor.device_class, SensorDeviceClass.SIGNAL_STRENGTH)
        self.assertEqual(sensor.entity_category, EntityCategory.DIAGNOSTIC)
        self.assertEqual(sensor.translation_key, "wifi_rssi")
        self.assertEqual(sensor.unique_id, "uid")

    def test_the_cloud_sensor_shows_the_link_and_whether_it_is_enabled(self):
        sensor = BluettiCloudConnectionBinarySensor(
            _network(NetworkStatus(-75, True, False)), {}, "uid"
        )

        self.assertFalse(sensor.is_on)
        self.assertEqual(sensor.extra_state_attributes, {"cloud_enabled": True})
        self.assertEqual(sensor.device_class, BinarySensorDeviceClass.CONNECTIVITY)
        self.assertEqual(sensor.entity_category, EntityCategory.DIAGNOSTIC)
        self.assertEqual(sensor.translation_key, "cloud_connected")

    def test_the_network_flags_show_their_field(self):
        status = NetworkStatus(-75, True, True, True, True, False)
        for field, expected in (
            ("wifi_connected", True),
            ("lan_reachable", True),
            ("wan_reachable", False),
        ):
            with self.subTest(field=field):
                sensor = BluettiNetworkBinarySensor(_network(status), {}, "uid", field)
                self.assertIs(sensor.is_on, expected)
                self.assertEqual(sensor.translation_key, field)
                self.assertEqual(sensor.device_class, BinarySensorDeviceClass.CONNECTIVITY)
                self.assertEqual(sensor.entity_category, EntityCategory.DIAGNOSTIC)
                # Wi-Fi and the local network can only read "on" while the
                # page answers: only the internet one starts enabled.
                self.assertEqual(
                    sensor.entity_registry_enabled_default, field == "wan_reachable"
                )

    def test_the_network_flags_are_unknown_before_any_answer(self):
        for data in (None, NO_NETWORK_STATUS):
            with self.subTest(data=data):
                sensor = BluettiNetworkBinarySensor(_network(data), {}, "u", "wan_reachable")
                self.assertIsNone(sensor.is_on)

    def test_both_are_unknown_before_any_answer(self):
        for data in (None, NO_NETWORK_STATUS):
            with self.subTest(data=data):
                network = _network(data)
                self.assertIsNone(BluettiWifiSignalSensor(network, {}, "u").native_value)
                cloud = BluettiCloudConnectionBinarySensor(network, {}, "u")
                self.assertIsNone(cloud.is_on)
                self.assertEqual(cloud.extra_state_attributes, {"cloud_enabled": None})


def _entry(dev_type="balco260"):
    entry = MagicMock(entry_id="entry1")
    entry.data = {"address": "10.2.1.128", "port": 502, "name": "n", "type": dev_type}
    return entry


class TestPlatforms(unittest.IsolatedAsyncioTestCase):
    def _coordinator(self, network):
        coordinator = MagicMock(spec=PollingCoordinator, config_entry=MagicMock(), data={})
        coordinator.network = network
        coordinator.device.get_sensors.return_value = []
        return coordinator

    @patch("custom_components.bluetti_modbus.sensor.get_device")
    async def test_the_sensor_platform_adds_the_signal_sensor_when_read(self, get_device_fn):
        get_device_fn.return_value.get_sensors.return_value = []
        for network, expected in ((_network(None), 1), (None, 0)):
            with self.subTest(network=network):
                entry = _entry()
                entry.runtime_data = self._coordinator(network)
                added = []
                await sensor_setup(MagicMock(), entry, added.extend)
                signal = [e for e in added if isinstance(e, BluettiWifiSignalSensor)]
                self.assertEqual(len(signal), expected)

    async def test_the_binary_sensor_platform_adds_the_cloud_link_when_read(self):
        for network, expected in ((_network(None), 1), (None, 0)):
            with self.subTest(network=network):
                entry = _entry()
                entry.runtime_data = self._coordinator(network)
                added = []
                await binary_sensor_setup(MagicMock(), entry, added.extend)
                cloud = [e for e in added if isinstance(e, BluettiCloudConnectionBinarySensor)]
                self.assertEqual(len(cloud), expected)
                flags = [e for e in added if isinstance(e, BluettiNetworkBinarySensor)]
                self.assertEqual(len(flags), expected * len(NETWORK_FLAGS))


class TestSetupAndUnload(unittest.IsolatedAsyncioTestCase):
    async def _setup(self, dev_type):
        coordinator = MagicMock(data={})
        coordinator.async_config_entry_first_refresh = AsyncMock()
        hass = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        with (
            patch("custom_components.bluetti_modbus.PollingCoordinator", return_value=coordinator),
            patch("custom_components.bluetti_modbus.dr"),
            patch("custom_components.bluetti_modbus.NetworkStatusCoordinator") as network_cls,
        ):
            network_cls.return_value.async_refresh = AsyncMock()
            await async_setup_entry(hass, _entry(dev_type))
        return coordinator, network_cls

    async def test_a_balco_260_reads_its_network_status_without_holding_up_setup(self):
        coordinator, network_cls = await self._setup("balco260")

        network_cls.assert_called_once()
        self.assertEqual(network_cls.call_args.args[2], "10.2.1.128")
        network_cls.return_value.async_refresh.assert_awaited_once()
        self.assertIs(coordinator.network, network_cls.return_value)

    async def test_other_devices_do_not(self):
        _, network_cls = await self._setup("smeter")

        network_cls.assert_not_called()

    async def test_unload_shuts_the_network_status_down_too(self):
        coordinator = MagicMock()
        coordinator.async_shutdown = AsyncMock()
        coordinator.network = MagicMock(spec=NetworkStatusCoordinator)
        coordinator.network.async_shutdown = AsyncMock()
        entry = MagicMock(runtime_data=coordinator)
        hass = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        self.assertTrue(await async_unload_entry(hass, entry))

        coordinator.network.async_shutdown.assert_awaited_once()
