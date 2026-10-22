import unittest
from unittest.mock import MagicMock, patch

import aiohttp

from custom_components.bluetti_modbus.web_page import (
    NO_NETWORK_STATUS,
    ModbusTcpSetting,
    NetworkStatus,
    async_query_modbus_setting,
    async_query_network_status,
)

_SESSION = "custom_components.bluetti_modbus.web_page.aiohttp_client.async_get_clientsession"

_GET_CONFIG = {"type": "getConfig", "data": {}}
_LOGIN = {"type": "login", "data": {"username": "admin", "password": ""}}


class _FakeMessage:
    def __init__(self, type_, data):
        self.type = type_
        self._data = data

    def json(self):
        return self._data


class _FakeWs:
    """Queues, after the n-th message the integration sends, replies[n]."""

    def __init__(self, replies):
        self._replies = list(replies)
        self._pending = []
        self.sent = []

    async def send_json(self, message):
        index = len(self.sent)
        self.sent.append(message)
        if index < len(self._replies):
            self._pending.extend(self._replies[index])

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        while self._pending:
            yield self._pending.pop(0)


class _FakeWsConnect:
    def __init__(self, ws=None, connect_error=None):
        self._ws = ws
        self._connect_error = connect_error

    async def __aenter__(self):
        if self._connect_error is not None:
            raise self._connect_error
        return self._ws

    async def __aexit__(self, *args):
        return False


def _text(data):
    return _FakeMessage(aiohttp.WSMsgType.TEXT, data)


def _login(err_code=0, token=None):
    result = {"errCode": err_code, "message": "Success" if err_code == 0 else "Fail"}
    if token is not None:
        result["token"] = token
    return _text({"type": "loginRsp", "result": result})


def _config(modbus_tcp=None):
    data = {"wifiAp": {"password": "secret"}}
    if modbus_tcp is not None:
        data["modbus_tcp"] = modbus_tcp
    return _text({"type": "getConfigRsp", "data": data})


_ON = {"enable": True, "crypt_enable": False, "port": 502}


async def _query(ws=None, connect_error=None):
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_FakeWsConnect(ws, connect_error))
    with patch(_SESSION, return_value=session):
        result = await async_query_modbus_setting(MagicMock(), "10.2.1.128")
    return result, session


class TestAsyncQueryModbusSetting(unittest.IsolatedAsyncioTestCase):
    async def test_a_page_that_needs_no_login_answers_the_first_request(self):
        # S Meter: getConfig answers at once, before any login.
        ws = _FakeWs([[_config(_ON)]])
        result, session = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))
        session.ws_connect.assert_called_once_with("ws://10.2.1.128:80/ws")
        self.assertEqual(ws.sent, [_GET_CONFIG, _LOGIN])

    async def test_a_page_that_needs_a_token_answers_after_the_login(self):
        # Balco 260: getConfig without a token carries no modbus_tcp block;
        # the token from result.token unlocks it.
        ws = _FakeWs([[_config()], [_login(token="t0k")], [_config(_ON)]])
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))
        self.assertEqual(ws.sent, [_GET_CONFIG, _LOGIN, {**_GET_CONFIG, "token": "t0k"}])

    async def test_a_login_without_a_token_asks_again_without_one(self):
        # FridgePower: the login opens a session, with no token returned.
        ws = _FakeWs([[], [_login()], [_config(_ON)]])
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))
        self.assertEqual(ws.sent, [_GET_CONFIG, _LOGIN, _GET_CONFIG])

    async def test_reports_a_disabled_or_encrypted_setting(self):
        for modbus_tcp, expected in (
            ({"enable": False, "crypt_enable": False}, ModbusTcpSetting(False, False)),
            ({"enable": True, "crypt_enable": True}, ModbusTcpSetting(True, True)),
        ):
            with self.subTest(modbus_tcp=modbus_tcp):
                result, _ = await _query(_FakeWs([[_config(modbus_tcp)]]))
                self.assertEqual(result, expected)

    async def test_a_missing_crypt_setting_is_unknown_not_a_failure(self):
        result, _ = await _query(_FakeWs([[_config({"enable": True})]]))

        self.assertEqual(result, ModbusTcpSetting(True, None))

    async def test_a_refused_login_learns_nothing_whatever_the_order(self):
        # The owner set a password: the default credentials are refused.
        for replies in (
            [[_login(err_code=1), _config()]],
            [[_config()], [_login(err_code=1)]],
        ):
            with self.subTest(replies=[[m._data["type"] for m in r] for r in replies]):
                ws = _FakeWs(replies)
                result, _ = await _query(ws)
                self.assertEqual(result, ModbusTcpSetting(None, None))
                self.assertEqual(ws.sent, [_GET_CONFIG, _LOGIN])

    async def test_ignores_non_text_and_unrelated_messages(self):
        ws = _FakeWs(
            [
                [
                    _FakeMessage(aiohttp.WSMsgType.BINARY, b"\x00"),
                    _text({"type": "monitorInfo", "data": {}}),
                    _config(_ON),
                ]
            ]
        )
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))

    async def test_a_closed_connection_without_an_answer_learns_nothing(self):
        result, _ = await _query(_FakeWs([[_config()], [_login(token="t0k")]]))

        self.assertEqual(result, ModbusTcpSetting(None, None))

    async def test_an_unexpected_shape_learns_nothing(self):
        for replies in (
            [[_text({"type": "loginRsp"})]],
            [[_text({"type": "loginRsp", "result": {}})]],
            [[_config({"enable": "yes"})]],
            [[_config({"enable": True, "crypt_enable": 1})]],
            [[_config({"crypt_enable": False})]],
        ):
            with self.subTest(replies=[m._data for m in replies[0]]):
                result, _ = await _query(_FakeWs(replies))
                self.assertEqual(result, ModbusTcpSetting(None, None))

    async def test_a_reply_without_data_counts_as_one_without_modbus_tcp(self):
        ws = _FakeWs([[_text({"type": "getConfigRsp"})], [_login(token="t")], [_config(_ON)]])
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))

    async def test_a_connection_failure_learns_nothing(self):
        result, _ = await _query(connect_error=aiohttp.ClientConnectionError("refused"))

        self.assertEqual(result, ModbusTcpSetting(None, None))

    async def test_a_timeout_learns_nothing(self):
        with (
            patch(_SESSION, return_value=MagicMock()),
            patch(
                "custom_components.bluetti_modbus.web_page.asyncio.timeout",
                side_effect=TimeoutError,
            ),
        ):
            result = await async_query_modbus_setting(MagicMock(), "10.2.1.128")

        self.assertEqual(result, ModbusTcpSetting(None, None))

    async def test_the_token_and_the_rest_of_the_configuration_are_not_logged(self):
        ws = _FakeWs(
            [[_config()], [_login(token="t0k")], [_config({"enable": True, "crypt_enable": "x"})]]
        )
        with self.assertLogs("custom_components.bluetti_modbus.web_page", "DEBUG") as logs:
            await _query(ws)

        output = "\n".join(logs.output)
        self.assertNotIn("t0k", output)
        self.assertNotIn("secret", output)
        self.assertIn("TypeError", output)


if __name__ == "__main__":
    unittest.main()


def _network(data, err_code=0):
    return _text(
        {
            "type": "networkStatusRsp",
            "result": {"errCode": err_code, "message": "Success"},
            "data": data,
        }
    )


_STATUS = {
    "ip": "10.2.1.128",
    "rssi": -75,
    "wifi_connected": True,
    "lan_reachable": True,
    "wan_reachable": False,
    "ap_ssid": "Balco2601234567890123",
    "mqtt_enabled": True,
    "mqtt_connected": True,
    "mqtt_step": 5,
}


async def _query_network(ws=None, connect_error=None):
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_FakeWsConnect(ws, connect_error))
    with patch(_SESSION, return_value=session):
        result = await async_query_network_status(MagicMock(), "10.2.1.128")
    return result, session


class TestAsyncQueryNetworkStatus(unittest.IsolatedAsyncioTestCase):
    async def test_the_token_from_the_login_asks_for_the_network_status(self):
        # Balco 260: the page logs in, then sends getNetworkStatus with the
        # token and gets networkStatusRsp back.
        ws = _FakeWs([[_login(token="t0k")], [_network(_STATUS)]])
        result, session = await _query_network(ws)

        self.assertEqual(result, NetworkStatus(-75, True, True, True, True, False))
        session.ws_connect.assert_called_once_with("ws://10.2.1.128:80/ws")
        self.assertEqual(
            ws.sent, [_LOGIN, {"type": "getNetworkStatus", "data": {}, "token": "t0k"}]
        )

    async def test_a_login_without_a_token_asks_without_one(self):
        ws = _FakeWs([[_login()], [_network({**_STATUS, "mqtt_connected": False})]])
        result, _ = await _query_network(ws)

        self.assertEqual(result, NetworkStatus(-75, True, False, True, True, False))
        self.assertEqual(ws.sent, [_LOGIN, {"type": "getNetworkStatus", "data": {}}])

    async def test_a_refused_login_learns_nothing(self):
        result, _ = await _query_network(_FakeWs([[_login(err_code=1)]]))

        self.assertEqual(result, NO_NETWORK_STATUS._replace(failure="login refused"))

    async def test_unexpected_values_are_unknown(self):
        for data in ({}, {"rssi": True, "mqtt_enabled": 1, "mqtt_connected": "yes"}, None):
            with self.subTest(data=data):
                ws = _FakeWs([[_login(token="t")], [_network(data)]])
                result, _ = await _query_network(ws)
                self.assertEqual(result, NetworkStatus(None, None, None))

    async def test_ignores_other_messages_and_learns_nothing_when_closed(self):
        ws = _FakeWs(
            [[_FakeMessage(aiohttp.WSMsgType.BINARY, b"\x00"), _config(_ON), _login(token="t")]]
        )
        result, _ = await _query_network(ws)

        self.assertEqual(result, NO_NETWORK_STATUS._replace(failure="no answer"))

    async def test_a_connection_failure_learns_nothing(self):
        result, _ = await _query_network(
            connect_error=aiohttp.ClientConnectionError("refused")
        )

        self.assertEqual(result, NO_NETWORK_STATUS._replace(failure="ClientConnectionError"))

    async def test_an_unexpected_login_shape_learns_nothing(self):
        result, _ = await _query_network(_FakeWs([[_text({"type": "loginRsp"})]]))

        self.assertEqual(result, NO_NETWORK_STATUS._replace(failure="KeyError"))
