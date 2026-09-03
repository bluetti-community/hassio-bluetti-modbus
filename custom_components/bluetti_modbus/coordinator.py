"""Coordinator for Bluetti integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection.exceptions import ModbusError

from .types import FullDeviceConfig
from .vendor.bluetti_modbus_lib import (
    EP2000,
    MAX_BATTERY_PACKS,
    Balco260,
    SMeter,
    battery_pack,
)
from .vendor.bluetti_modbus_lib.modbus.client import BluettiModbusClient


class PollingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polling coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        config: FullDeviceConfig,
    ):
        """Initialize coordinator."""
        super().__init__(
            hass,
            logging.getLogger(f"{__name__}.{config.address}"),
            config_entry=config_entry,
            name="Bluetti polling coordinator",
            # Bluetti's Modbus TCP stack is fragile under frequent connections -
            # a rapid burst of TCP connections during testing once made the
            # device's web interface unresponsive and required a factory
            # reset to recover. Keep this conservative.
            update_interval=timedelta(seconds=30),
        )

        self.config = config
        # One persistent client for the lifetime of this coordinator, not one
        # per poll - a fresh connection on every poll is exactly the pattern
        # that has made the device's Modbus TCP stack unresponsive under load.
        self._client = BluettiModbusClient(
            config.address,
            config.port,
            config.dev_type,
        )
        # Balco260 only - BC200 packs beyond the first, built lazily once
        # d_num_battery_packs is known from the main device's own read, keyed
        # by pack number (2..MAX_BATTERY_PACKS). Pack 1's data already comes
        # from the main device's own fields (same Modbus slave address) - see
        # bluetti_modbus_lib.battery_pack()'s docstring.
        self._packs: dict[int, Balco260] = {}

    @property
    def device(self) -> Balco260 | EP2000 | SMeter:
        """The underlying bluetti_modbus_lib device - write() lives here."""
        return self._client.device

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device."""
        try:
            data = await self._client.read()
            result = {k: v for k, v in [[d.name, d.value] for d in data]}
            await self._async_update_battery_packs(result)
        except ModbusError as err:
            # bluetti-modbus-lib already retries once on transient
            # ACKNOWLEDGE/SERVER_DEVICE_BUSY and corrupted/timed-out
            # responses this device is known to occasionally return -
            # reaching here means a more persistent connectivity problem.
            # Surface it as an ordinary failed update rather than letting it
            # fall through to DataUpdateCoordinator's "unexpected exception"
            # path, which would log a full traceback for an expected,
            # recoverable condition.
            raise UpdateFailed(str(err)) from err

        return result

    async def _async_update_battery_packs(self, result: dict[str, Any]) -> None:
        """Read BC200 packs 2..N into result as pack_{n}_{field}.

        Balco260 only, per this integration's current scope - EP2000's
        battery-pack behavior is unconfirmed on real hardware. Packs share
        the main device's own Modbus connection (a different slave address,
        not a new TCP connection), so this must run after self._client.read()
        already established it, within the same update cycle.
        """
        if not isinstance(self.device, Balco260):
            return

        num_packs = result.get("d_num_battery_packs")
        if not isinstance(num_packs, int):
            return

        for pack_num in range(2, min(num_packs, MAX_BATTERY_PACKS) + 1):
            pack = self._packs.get(pack_num)
            if pack is None:
                pack = battery_pack(self._client.conn, pack_num)
                self._packs[pack_num] = pack
            await pack.async_update_with_retry()
            for name, value in pack.values.items():
                result[f"pack_{pack_num}_{name}"] = value

    async def aclose(self) -> None:
        """Close the underlying Modbus connection."""
        await self._client.aclose()
