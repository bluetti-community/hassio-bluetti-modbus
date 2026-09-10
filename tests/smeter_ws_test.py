import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from custom_components.bluetti_modbus.smeter_ws import SmeterWsInfo, async_query_smeter


class _FakeMessage:
    def __init__(self, type_, data):
        self.type = type_
        self._data = data

    def json(self):
        return self._data


class _FakeWs:
    def __init__(self, messages):
        self._messages = list(messages)
        self.send_json = AsyncMock()

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for message in self._messages:
            yield message


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


def _session(ws_connect_return):
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=ws_connect_return)
    return session


class TestAsyncQuerySmeter(unittest.IsolatedAsyncioTestCase):
    async def test_returns_firmware_and_modbus_enabled_on_success(self):
        ws = _FakeWs(
            [
                _FakeMessage(
                    aiohttp.WSMsgType.TEXT,
                    {"type": "getConfigRsp", "data": {"modbus_tcp": {"enable": True}}},
                ),
                _FakeMessage(
                    aiohttp.WSMsgType.TEXT,
                    {
                        "type": "getVersionRsp",
                        "data": {"firmwares": [{"model": "SMeter", "version": "V300510106"}]},
                    },
                ),
            ]
        )
        session = _session(_FakeWsConnect(ws))
        with patch(
            "custom_components.bluetti_modbus.smeter_ws.aiohttp_client.async_get_clientsession",
            return_value=session,
        ):
            result = await async_query_smeter(MagicMock(), "10.2.1.80", 80)

        self.assertEqual(result, SmeterWsInfo("V300510106", True))
        ws.send_json.assert_any_await({"type": "getConfig", "data": {}})
        ws.send_json.assert_any_await({"type": "getVersion", "data": {}})
        session.ws_connect.assert_called_once_with("ws://10.2.1.80:80/8")

    async def test_ignores_non_text_messages(self):
        ws = _FakeWs(
            [
                _FakeMessage(aiohttp.WSMsgType.BINARY, b"\x00"),
                _FakeMessage(
                    aiohttp.WSMsgType.TEXT,
                    {"type": "getConfigRsp", "data": {"modbus_tcp": {"enable": False}}},
                ),
            ]
        )
        session = _session(_FakeWsConnect(ws))
        with patch(
            "custom_components.bluetti_modbus.smeter_ws.aiohttp_client.async_get_clientsession",
            return_value=session,
        ):
            result = await async_query_smeter(MagicMock(), "10.2.1.80", 80)

        self.assertEqual(result, SmeterWsInfo(None, False))

    async def test_partial_response_keeps_whatever_field_did_arrive(self):
        # The device only ever sends one of the two responses (or closes
        # early) - not a failure, the field that did arrive is still safe
        # to use on its own (see async_query_smeter's own docstring).
        ws = _FakeWs(
            [
                _FakeMessage(
                    aiohttp.WSMsgType.TEXT,
                    {"type": "getConfigRsp", "data": {"modbus_tcp": {"enable": True}}},
                ),
            ]
        )
        session = _session(_FakeWsConnect(ws))
        with patch(
            "custom_components.bluetti_modbus.smeter_ws.aiohttp_client.async_get_clientsession",
            return_value=session,
        ):
            result = await async_query_smeter(MagicMock(), "10.2.1.80", 80)

        self.assertEqual(result, SmeterWsInfo(None, True))

    async def test_connection_failure_returns_none_none(self):
        session = _session(
            _FakeWsConnect(connect_error=aiohttp.ClientConnectionError("refused"))
        )
        with patch(
            "custom_components.bluetti_modbus.smeter_ws.aiohttp_client.async_get_clientsession",
            return_value=session,
        ):
            result = await async_query_smeter(MagicMock(), "10.2.1.80", 80)

        self.assertEqual(result, SmeterWsInfo(None, None))

    async def test_timeout_returns_none_none(self):
        with (
            patch(
                "custom_components.bluetti_modbus.smeter_ws.aiohttp_client.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.bluetti_modbus.smeter_ws.asyncio.timeout",
                side_effect=TimeoutError,
            ),
        ):
            result = await async_query_smeter(MagicMock(), "10.2.1.80", 80)

        self.assertEqual(result, SmeterWsInfo(None, None))

    async def test_malformed_response_discards_everything_learned_so_far(self):
        # A message that arrived first and parsed fine is discarded too once
        # a later one turns out malformed - a broken assumption about this
        # undocumented protocol means nothing from the session is trusted.
        ws = _FakeWs(
            [
                _FakeMessage(
                    aiohttp.WSMsgType.TEXT,
                    {"type": "getVersionRsp", "data": {"firmwares": [{"version": "V1"}]}},
                ),
                _FakeMessage(aiohttp.WSMsgType.TEXT, {"type": "getConfigRsp", "data": {}}),
            ]
        )
        session = _session(_FakeWsConnect(ws))
        with patch(
            "custom_components.bluetti_modbus.smeter_ws.aiohttp_client.async_get_clientsession",
            return_value=session,
        ):
            result = await async_query_smeter(MagicMock(), "10.2.1.80", 80)

        self.assertEqual(result, SmeterWsInfo(None, None))
