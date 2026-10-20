"""The device's network status, read from its own web page."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .web_page import NetworkStatus, async_query_network_status

# Devices whose web page answers getNetworkStatus (a Balco 260).
NETWORK_STATUS_DEV_TYPES = frozenset({"balco260"})

# Rarely: the page's WebSocket may accept one client at a time, and an open
# browser tab on the page would otherwise keep losing it to this read.
NETWORK_STATUS_SCAN_INTERVAL = timedelta(minutes=5)


class NetworkStatusCoordinator(DataUpdateCoordinator[NetworkStatus]):
    """Reads the Wi-Fi signal and the cloud link every few minutes.

    Apart from the Modbus polling: a failed read leaves the values unknown
    and never touches the readings.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, host: str) -> None:
        """Init the coordinator."""
        super().__init__(
            hass,
            logging.getLogger(f"{__name__}.{host}"),
            config_entry=config_entry,
            name="BLUETTI network status",
            update_interval=NETWORK_STATUS_SCAN_INTERVAL,
        )
        self._host = host
        self._unanswered = False

    async def _async_update_data(self) -> NetworkStatus:
        """Read the network status; unknown values when the page does not answer.

        Logged once when the page stops answering, with why, and once when
        it answers again.
        """
        status = await async_query_network_status(self.hass, self._host)
        if status.failure is not None:
            if not self._unanswered:
                self._unanswered = True
                self.logger.info(
                    "The device's web page does not answer the network status (%s): "
                    "the Wi-Fi signal and the cloud connection are unknown until it does",
                    status.failure,
                )
        elif self._unanswered:
            self._unanswered = False
            self.logger.info("The device's web page answers the network status again")
        return status
