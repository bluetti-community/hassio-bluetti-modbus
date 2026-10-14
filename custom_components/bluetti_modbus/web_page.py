"""Best-effort read of the Modbus TCP setting from a Balco-family web page.

The Balco 260, Balco 500, Balco Transfer Hub and FridgePower share one IoT
module whose local web page talks to the device over a WebSocket at /ws. A
"login" message with the page's default credentials (user "admin", blank
password) answers with a token in result.token, and "getConfig" with that
token answers with data.modbus_tcp (enable, crypt_enable, port). Confirmed
on a Balco 260 (IoT V500120120) and on a FridgePower
(https://github.com/freakdesign/bluetti-fridgepower-local).

The API is unofficial: every failure, including a login refused because the
owner set a password, is reported as "nothing learned" and never raised.
Only the modbus_tcp block is read; the rest of getConfig carries Wi-Fi and
Bluetooth secrets and is neither kept nor logged, and neither is the token.
"""

from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

_LOGGER = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5

# Device types whose web page is the shared Balco-family one above.
WEB_PAGE_LOGIN_DEV_TYPES = frozenset({"balco260", "balco500", "balcotrans", "fp"})


class ModbusTcpSetting(NamedTuple):
    """The device's own Modbus TCP setting; None where it was not learned."""

    enabled: bool | None
    encrypted: bool | None


async def async_query_modbus_setting(
    hass: HomeAssistant, host: str, port: int = 80
) -> ModbusTcpSetting:
    """Read the Modbus TCP setting from the device's web page. Never raises."""
    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            async with session.ws_connect(f"ws://{host}:{port}/ws") as ws:
                return await _async_read_setting(ws)
    except (TimeoutError, aiohttp.ClientError, ValueError, KeyError, TypeError) as err:
        # The error's type only: a message could quote the device's reply.
        _LOGGER.debug("Best-effort web page query failed: %s", type(err).__name__)
    return ModbusTcpSetting(None, None)


async def _async_read_setting(ws: aiohttp.ClientWebSocketResponse) -> ModbusTcpSetting:
    """Log in, then ask for the configuration and keep its modbus_tcp block."""
    await ws.send_json({"type": "login", "data": {"username": "admin", "password": ""}})
    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        payload = msg.json()
        msg_type = payload.get("type")
        if msg_type == "loginRsp":
            result = payload["result"]
            if result["errCode"] != 0:
                return ModbusTcpSetting(None, None)
            await ws.send_json({"type": "getConfig", "data": {}, "token": result["token"]})
        elif msg_type == "getConfigRsp":
            modbus_tcp = payload["data"]["modbus_tcp"]
            enabled = modbus_tcp["enable"]
            encrypted = modbus_tcp.get("crypt_enable")
            if not isinstance(enabled, bool) or not isinstance(encrypted, bool | None):
                raise TypeError("unexpected modbus_tcp shape")
            return ModbusTcpSetting(enabled, encrypted)
    return ModbusTcpSetting(None, None)
