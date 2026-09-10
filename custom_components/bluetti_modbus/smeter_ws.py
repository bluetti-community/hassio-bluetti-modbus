"""Best-effort queries against the S Meter's own undocumented WebSocket API.

Real hardware (browser devtools, both a real S Meter and a real Balco260)
confirms both devices expose this over their own local web UI - S Meter
needs no authentication at all, Balco260 requires a token this integration
has no way to obtain and isn't implemented here.

Confirmed against a real S Meter's own capture: connecting to
"ws://<host>:<port>/8" (port 80, the mDNS-advertised web UI port - not
Modbus TCP's own port 502) and sending {"type": "getConfig", "data": {}}
and {"type": "getVersion", "data": {}} gets back a "getConfigRsp" (whose
data.modbus_tcp.enable says whether Modbus TCP is actually turned on) and a
"getVersionRsp" (whose data.firmwares[0].version is the running firmware).

This is unofficial and unconfirmed by BLUETTI (unlike this integration's
Modbus register maps) - it could change or disappear on a firmware update
with no changelog to warn us. Every failure mode here (timeout, connection
refused, an unexpected response shape) is therefore swallowed and reported
as "nothing learned" rather than raised - the real, BLUETTI-confirmed
Modbus-based discovery flow this supports must keep working unchanged even
if this guess about an undocumented API turns out to be wrong.
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


class SmeterWsInfo(NamedTuple):
    """Best-effort info from the S Meter's own WebSocket API.

    Both fields come from the same short-lived connection - either is None
    if that specific response was never received in time, and both are None
    together on any failure (see async_query_smeter's own docstring).
    """

    firmware_version: str | None
    modbus_tcp_enabled: bool | None


async def async_query_smeter(hass: HomeAssistant, host: str, port: int) -> SmeterWsInfo:
    """Best-effort query for firmware_version/modbus_tcp_enabled.

    Never raises. Each field is independently None if its own response was
    never received - the connection simply closing early (e.g. this device
    only ever sends one of the two) is not a failure, and whichever field
    did arrive is still safe to use on its own. A genuine failure instead
    (timeout, connection refused, a message that doesn't parse or match the
    expected shape) resets *both* fields to None rather than keeping
    whatever was parsed before it - at that point our assumptions about
    this undocumented protocol may be wrong, so nothing from that session
    should be trusted.
    """
    session = aiohttp_client.async_get_clientsession(hass)
    firmware_version: str | None = None
    modbus_tcp_enabled: bool | None = None
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            async with session.ws_connect(f"ws://{host}:{port}/8") as ws:
                await ws.send_json({"type": "getConfig", "data": {}})
                await ws.send_json({"type": "getVersion", "data": {}})

                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = msg.json()
                    msg_type = payload.get("type")
                    if msg_type == "getConfigRsp":
                        modbus_tcp_enabled = payload["data"]["modbus_tcp"]["enable"]
                    elif msg_type == "getVersionRsp":
                        firmwares = payload["data"]["firmwares"]
                        if firmwares:
                            firmware_version = firmwares[0]["version"]
                    if firmware_version is not None and modbus_tcp_enabled is not None:
                        break
    except (TimeoutError, aiohttp.ClientError, ValueError, KeyError, TypeError) as err:
        _LOGGER.debug("Best-effort S Meter WebSocket query failed: %s", err)
        return SmeterWsInfo(None, None)

    return SmeterWsInfo(firmware_version, modbus_tcp_enabled)
