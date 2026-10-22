"""Best-effort read of the Modbus TCP setting from a device's own web page.

The web page of the Balco 260, Balco 500, Balco Transfer Hub, FridgePower,
S Meter, AC500, AC240, AC200L and EP500Pro talks to the device over a WebSocket at
/ws, and "getConfig" answers with data.modbus_tcp (enable, crypt_enable,
port; the AC family's page has no crypt_enable). Devices differ in what
they ask first:

- S Meter: answers getConfig without any login.
- AC500, AC240, EP500Pro and AC200L (IoT V9041.17): answer getConfig
  without any login; the AC500, the AC240 and the EP500Pro do so with a
  password set for the device too. An AC200L also answers after a login
  that returns no token.
- Balco 260 (IoT V500120120): answers getConfig without a token, but with
  no modbus_tcp block; after "login" with the page's default credentials
  (user "admin", blank password) it answers with a token in result.token,
  and getConfig sent with that token carries modbus_tcp.
- Balco Transfer Hub (IoT V30052.01.17): answers getConfig after the login,
  crypt_enable included.
- Balco 500 (IoT 50013.02.09): answers getConfig without any login,
  crypt_enable included.
- FridgePower: accepts the same login and then answers other requests
  without a token (https://github.com/freakdesign/bluetti-fridgepower-local).

So getConfig is sent at once, the login alongside it, and getConfig again
after the login, with the token when one comes back. The first answer that
carries modbus_tcp is the result. A Balco 260 refused a second WebSocket
client while its own web page was open, so an open page can make this
query fail.

The API is unofficial: every failure, including a login refused because the
owner set a password, is reported as "nothing learned" and never raised.
Only the modbus_tcp block is read; the rest of getConfig can carry Wi-Fi and
Bluetooth secrets and is neither kept nor logged, and neither is the token.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, NamedTuple

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

_LOGGER = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5

# Device types whose web page is asked when a Modbus probe fails.
WEB_PAGE_DEV_TYPES = frozenset(
    {
        "ac200l",
        "ac240",
        "ac500",
        "balco260",
        "balco500",
        "balcotrans",
        "ep500p",
        "fp",
        "smeter",
    }
)


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
    """Ask for the configuration with and without a login; keep modbus_tcp."""
    await ws.send_json({"type": "getConfig", "data": {}})
    await ws.send_json({"type": "login", "data": {"username": "admin", "password": ""}})
    login_refused = False
    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        payload = msg.json()
        msg_type = payload.get("type")
        if msg_type == "loginRsp":
            result = payload["result"]
            if result["errCode"] != 0:
                login_refused = True
                continue
            request: dict[str, Any] = {"type": "getConfig", "data": {}}
            if (token := result.get("token")) is not None:
                request["token"] = token
            await ws.send_json(request)
        elif msg_type == "getConfigRsp":
            modbus_tcp = (payload.get("data") or {}).get("modbus_tcp")
            if modbus_tcp is None:
                # Not allowed without a login: wait for the one after it,
                # unless the login was refused too.
                if login_refused:
                    break
                continue
            enabled = modbus_tcp["enable"]
            encrypted = modbus_tcp.get("crypt_enable")
            if not isinstance(enabled, bool) or not isinstance(encrypted, bool | None):
                raise TypeError("unexpected modbus_tcp shape")
            return ModbusTcpSetting(enabled, encrypted)
    return ModbusTcpSetting(None, None)


class NetworkStatus(NamedTuple):
    """The device's own network status; None where it was not learned."""

    rssi: int | None
    cloud_enabled: bool | None
    cloud_connected: bool | None
    wifi_connected: bool | None = None
    lan_reachable: bool | None = None
    wan_reachable: bool | None = None
    # Why nothing was learned, for the log; None when the page answered.
    failure: str | None = None


NO_NETWORK_STATUS = NetworkStatus(None, None, None)


async def async_query_network_status(
    hass: HomeAssistant, host: str, port: int = 80
) -> NetworkStatus:
    """Read the Wi-Fi signal and the cloud link from the web page. Never raises.

    The page asks "getNetworkStatus" after its login and gets
    "networkStatusRsp", whose data carries rssi (dBm), mqtt_enabled and
    mqtt_connected (the link to BLUETTI's cloud), wifi_connected,
    lan_reachable and wan_reachable (the internet), confirmed on a Balco 260.
    Only those six are kept: the same answer holds the network's addresses
    and the access point's name.
    """
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            async with session.ws_connect(f"ws://{host}:{port}/ws") as ws:
                return await _async_read_network_status(ws)
    except (TimeoutError, aiohttp.ClientError, ValueError, KeyError, TypeError) as err:
        # The error's type only: a message could quote the device's reply.
        failure = type(err).__name__
    return NO_NETWORK_STATUS._replace(failure=failure)


async def _async_read_network_status(ws: aiohttp.ClientWebSocketResponse) -> NetworkStatus:
    """Log in, ask for the network status, keep the signal and the cloud link."""
    await ws.send_json({"type": "login", "data": {"username": "admin", "password": ""}})
    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        payload = msg.json()
        msg_type = payload.get("type")
        if msg_type == "loginRsp":
            result = payload["result"]
            if result["errCode"] != 0:
                return NO_NETWORK_STATUS._replace(failure="login refused")
            request: dict[str, Any] = {"type": "getNetworkStatus", "data": {}}
            if (token := result.get("token")) is not None:
                request["token"] = token
            await ws.send_json(request)
        elif msg_type == "networkStatusRsp":
            data = payload.get("data") or {}
            rssi = data.get("rssi")
            return NetworkStatus(
                rssi if isinstance(rssi, int) and not isinstance(rssi, bool) else None,
                _flag(data, "mqtt_enabled"),
                _flag(data, "mqtt_connected"),
                _flag(data, "wifi_connected"),
                _flag(data, "lan_reachable"),
                _flag(data, "wan_reachable"),
            )
    return NO_NETWORK_STATUS._replace(failure="no answer")


def _flag(data: dict[str, Any], key: str) -> bool | None:
    """A yes/no field of the answer, None when it is missing or not a bool."""
    value = data.get(key)
    return value if isinstance(value, bool) else None
