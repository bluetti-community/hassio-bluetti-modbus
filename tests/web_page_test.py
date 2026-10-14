import unittest
from unittest.mock import MagicMock, patch

import aiohttp

from custom_components.bluetti_modbus.web_page import (
    ModbusTcpSetting,
    async_query_modbus_setting,
)

_SESSION = "custom_components.bluetti_modbus.web_page.aiohttp_client.async_get_clientsession"


class _FakeMessage:
    def __init__(self, type_, data):
        self.type = type_
        self._data = data

    def json(self):
        return self._data


class _FakeWs:
    """Answers each message the integration sends with the next canned replies."""

    def __init__(self, replies_after_send):
        self._replies_after_send = list(replies_after_send)
        self._pending = []
        self.sent = []

    async def send_json(self, message):
        self.sent.append(message)
        if self._replies_after_send:
            self._pending.extend(self._replies_after_send.pop(0))

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


def _login_ok():
    return _text(
        {"type": "loginRsp", "result": {"errCode": 0, "message": "Success", "token": "t0k"}}
    )


def _config(modbus_tcp):
    return _text(
        {
            "type": "getConfigRsp",
            "data": {"wifiAp": {"password": "secret"}, "modbus_tcp": modbus_tcp},
        }
    )


async def _query(ws=None, connect_error=None):
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_FakeWsConnect(ws, connect_error))
    with patch(_SESSION, return_value=session):
        result = await async_query_modbus_setting(MagicMock(), "10.2.1.128")
    return result, session


class TestAsyncQueryModbusSetting(unittest.IsolatedAsyncioTestCase):
    async def test_logs_in_then_reads_the_modbus_tcp_block(self):
        ws = _FakeWs(
            [
                [_login_ok()],
                [_config({"enable": True, "crypt_enable": False, "port": 502})],
            ]
        )
        result, session = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))
        session.ws_connect.assert_called_once_with("ws://10.2.1.128:80/ws")
        self.assertEqual(
            ws.sent,
            [
                {"type": "login", "data": {"username": "admin", "password": ""}},
                {"type": "getConfig", "data": {}, "token": "t0k"},
            ],
        )

    async def test_reports_a_disabled_or_encrypted_setting(self):
        for modbus_tcp, expected in (
            ({"enable": False, "crypt_enable": False}, ModbusTcpSetting(False, False)),
            ({"enable": True, "crypt_enable": True}, ModbusTcpSetting(True, True)),
        ):
            with self.subTest(modbus_tcp=modbus_tcp):
                ws = _FakeWs([[_login_ok()], [_config(modbus_tcp)]])
                result, _ = await _query(ws)
                self.assertEqual(result, expected)

    async def test_a_missing_crypt_setting_is_unknown_not_a_failure(self):
        ws = _FakeWs([[_login_ok()], [_config({"enable": True})]])
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, None))

    async def test_a_refused_login_learns_nothing_and_asks_nothing_more(self):
        # The owner set a password: the default credentials are refused.
        ws = _FakeWs(
            [[_text({"type": "loginRsp", "result": {"errCode": 1, "message": "Fail"}})]]
        )
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(None, None))
        self.assertEqual(len(ws.sent), 1)

    async def test_ignores_non_text_and_unrelated_messages(self):
        ws = _FakeWs(
            [
                [
                    _FakeMessage(aiohttp.WSMsgType.BINARY, b"\x00"),
                    _text({"type": "pong", "data": {}}),
                    _login_ok(),
                ],
                [_config({"enable": True, "crypt_enable": False})],
            ]
        )
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(True, False))

    async def test_a_closed_connection_without_an_answer_learns_nothing(self):
        ws = _FakeWs([[_login_ok()]])
        result, _ = await _query(ws)

        self.assertEqual(result, ModbusTcpSetting(None, None))

    async def test_an_unexpected_shape_learns_nothing(self):
        for reply in (
            _text({"type": "loginRsp"}),
            _text({"type": "loginRsp", "result": {"errCode": 0}}),
            _config({"enable": "yes"}),
            _config({"enable": True, "crypt_enable": 1}),
        ):
            with self.subTest(reply=reply._data):
                if reply._data["type"] == "getConfigRsp":
                    ws = _FakeWs([[_login_ok()], [reply]])
                else:
                    ws = _FakeWs([[reply]])
                result, _ = await _query(ws)
                self.assertEqual(result, ModbusTcpSetting(None, None))

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
        ws = _FakeWs([[_login_ok()], [_config({"enable": True, "crypt_enable": "x"})]])
        with self.assertLogs("custom_components.bluetti_modbus.web_page", "DEBUG") as logs:
            await _query(ws)

        output = "\n".join(logs.output)
        self.assertNotIn("t0k", output)
        self.assertNotIn("secret", output)
        self.assertIn("TypeError", output)


if __name__ == "__main__":
    unittest.main()
