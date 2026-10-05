"""Coordinator for BLUETTI integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection.exceptions import ModbusError

from .const import INDIVIDUAL_BC260_PACKS_CONFIRMED
from .types import FullDeviceConfig
from .vendor.bluetti_modbus_lib import (
    AC200L,
    AC500,
    EP500P,
    EP2000,
    FP,
    MAX_BATTERY_PACKS,
    PA030,
    Balco260,
    Balco500,
    Balcotrans,
    SMeter,
    aggregate_pack_summary,
    battery_pack,
    get_device,
    pack_is_reporting,
    pack_slave_id,
)
from .vendor.bluetti_modbus_lib.modbus.client import BluettiModbusClient

# Every profile the library can build - what get_device() returns, minus None.
BluettiProfile = (
    AC200L | AC500 | FP | PA030 | Balco260 | Balco500 | Balcotrans | EP2000 | EP500P | SMeter
)

# Failed polls in a row a coordinator rides out on its last values before
# its entities go unavailable. A Balco 260 fails about one poll an hour even
# after the library's own retries (a dropped connection, a corrupted reply,
# a timeout - always recovered by the next poll); without this, every such
# poll flipped a hundred entities to unavailable and logged an error. The
# grace period is 90 s on stale values before the entities say so, which at
# the 15 s readings cycle (READINGS_SCAN_INTERVAL below) is five tolerated
# failures - kept in time rather than in polls, so reading faster does not
# make entities go unavailable sooner.
POLL_FAILURES_TOLERATED = 5

# The data area is read on every cycle and the settings block on its own,
# slower one - the split home-assistant/core's sofar and solaredge_modbus
# integrations make between readings and settings. 57001 is where BLUETTI's
# register list starts its "Inverter Set" block: output switches, grid
# charging, SOC thresholds. Those change when an owner changes them, so
# reading them a quarter as often takes requests off a Modbus stack this
# device is known to struggle with, which is what pays for reading the data
# area twice as fast.
READINGS_SCAN_INTERVAL = timedelta(seconds=15)
SETTINGS_SCAN_INTERVAL = timedelta(seconds=60)
SETTINGS_FIRST_ADDRESS = 57001
# A device applies a write at once but serves the old value for a moment
# afterwards - on a Balco 260, b_soc_low written 15 -> 16 read back 15, and 16
# a moment later. The library's bluetti-modwrite waits this long before its
# own read-back for the same reason.
SETTINGS_WRITE_SETTLE = timedelta(seconds=2)


class PollingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polling coordinator."""

    # Narrows DataUpdateCoordinator's own `config_entry: ConfigEntry | None`
    # - always a real ConfigEntry here, __init__ below never omits it (the
    # base class only leaves it None when a caller skips the parameter
    # entirely, using contextvars as a fallback instead - not something this
    # coordinator ever does). Entity classes rely on this being non-None to
    # read entry_id for their own unique_id (see e.g. sensor.py).
    config_entry: ConfigEntry

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
            name="BLUETTI polling coordinator",
            # BLUETTI's Modbus TCP stack is fragile under frequent connections -
            # a rapid burst of TCP connections during testing once made the
            # device's web interface unresponsive and required a factory
            # reset to recover. The connection is persistent and the settings
            # block only comes along every fourth cycle (see
            # SETTINGS_SCAN_INTERVAL), which is what makes this rate safe.
            update_interval=READINGS_SCAN_INTERVAL,
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
        # Confirmed on real hardware: a switch/number write landing while the
        # periodic poll below is mid-flight can come back as
        # ModbusProtocolError("Expected response to match request") - not
        # because the write was rejected (the official BLUETTI app shows the
        # new value took effect regardless), but because this device's
        # Modbus TCP stack is fragile under overlapping requests on the same
        # connection (see this class's own update_interval comment) and
        # returns a response that doesn't match either request. Serializing
        # every read and write through this lock means the device only ever
        # sees one request in flight at a time, regardless of what HA
        # schedules concurrently.
        self._io_lock = asyncio.Lock()
        # Split the profile's read plan in two - see SETTINGS_SCAN_INTERVAL.
        # self._schema keeps the whole profile, unpolled, for everything that
        # needs every field: the platforms building entities, writes, and the
        # raw diagnostics dump. On a profile with no settings field there is
        # nothing to split, and all three stay the client's own device.
        self._schema: BluettiProfile = self._client.device
        self._settings: BluettiProfile | None = None
        self._settings_values: dict[str, Any] = {}
        # Monotonic deadline for the next settings read; 0.0 = on this poll.
        self._settings_due_at = 0.0
        self._split_read_plan()
        # Balco260 only - BC260 packs beyond the first, built lazily once
        # d_num_battery_packs is known from the main device's own read, keyed
        # by pack number (2..MAX_BATTERY_PACKS). Pack 1's data already comes
        # from the main device's own fields (same Modbus slave address); the
        # others answer at slave 41 and up, pack_slave_id() does the
        # arithmetic - see bluetti_modbus_lib.battery_pack()'s docstring.
        self._packs: dict[int, Balco260] = {}
        # Balco260 only - the aggregate "Pack Summary" block (51001-51008,
        # including d_num_battery_packs itself), which only reports
        # correctly at a different Modbus slave address (250) than the main
        # device's own - see bluetti_modbus_lib.aggregate_pack_summary()'s
        # docstring. Built lazily on first use, same as self._packs.
        self._aggregate_summary: Balco260 | None = None
        # Failed polls since the last successful one - see
        # POLL_FAILURES_TOLERATED.
        self._failed_polls = 0

    @property
    def device(self) -> BluettiProfile:
        """The underlying bluetti_modbus_lib device - for reading fields.

        Not for writing - call async_write() instead of device.write()
        directly, so a write is serialized against the periodic poll below
        via self._io_lock (see its own comment in __init__).
        """
        return self._schema

    def _split_read_plan(self) -> None:
        """Move the settings fields out of the client's every-cycle read.

        The client's own device keeps the data area and is what each poll
        reads; a second component on the same connection keeps the settings
        and is read on SETTINGS_SCAN_INTERVAL; a third, whole and unpolled,
        becomes the schema the device property returns.
        """
        device = self._client.device
        settings_names = [
            name
            for name in device.field_names()
            if (field := device.get_field(name)) is not None
            and field.address >= SETTINGS_FIRST_ADDRESS
        ]
        if not settings_names:
            return
        unit = self._client.conn.for_unit(1)
        schema = get_device(self.config.dev_type, unit)
        settings = get_device(self.config.dev_type, unit)
        # The client already built this profile, so get_device() cannot miss.
        assert schema is not None and settings is not None
        wanted = set(settings_names)
        readings_names = [n for n in device.field_names() if n not in wanted]
        settings.restrict_fields(settings_names)
        device.restrict_fields(readings_names)
        self._schema = schema
        self._settings = settings

    async def async_read_raw_registers(self) -> dict[str, dict[str, dict[int, int | bool]]]:
        """Read every declared register block again and return it undecoded.

        For a diagnostics dump only - one extra Modbus read of the same
        blocks the poll reads, on the same connection, serialized against
        the poll via self._io_lock like a write is. Each entry is what
        modbus_connection's own Component.async_read_raw() returns,
        {address space: {address: word}}, i.e. what the device put on the
        wire before any decode - the one thing that settles "decode bug or
        device bug" (width, sign, word order) when a decoded value looks
        wrong, which the decoded snapshot in coordinator.data can't.

        "device" is the main device at its own unit id; "aggregate_pack_summary"
        is the Balco260-only Pack Summary block at unit 250 (see
        aggregate_pack_summary()'s docstring), present once the poll has
        built that component. Raises the same ModbusError subclasses as a
        poll - the caller decides how to present a failed read.
        """
        async with self._io_lock:
            raw = {"device": await self.device.async_read_raw(notify=False)}
            if self._aggregate_summary is not None:
                raw["aggregate_pack_summary"] = await self._aggregate_summary.async_read_raw(
                    notify=False
                )
        return raw

    async def async_write(self, field_name: str, value: int) -> None:
        """Write a single field, serialized against the periodic poll.

        The device's own way of confirming a write - at its internal
        register address rather than the Modbus one - is recognised by the
        library's BluettiDevice.write(), which logs the echoed address
        (debug when it is the one on file, warning when it isn't); nothing
        to handle here beyond the serialization.
        """
        async with self._io_lock:
            await self.device.write(field_name, value)
        # Keep what was just written in the settings snapshot, and confirm it
        # on the first poll after the device has settled. Both halves matter:
        # without the first, a poll before the next settings read would merge
        # the old value back in and the switch would snap back; without the
        # settle, a settings read straight after the write would read the old
        # value - see SETTINGS_WRITE_SETTLE - and then keep it for a minute.
        if self._settings is not None and self._settings.get_field(field_name) is not None:
            self._settings_values[field_name] = value
            self._settings_due_at = time.monotonic() + SETTINGS_WRITE_SETTLE.total_seconds()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device."""
        try:
            async with self._io_lock:
                data = await self._client.read()
                result = {k: v for k, v in [[d.name, d.value] for d in data]}
                await self._async_read_settings_if_due()
                result = {**self._settings_values, **result}
                await self._async_update_battery_packs(result)
        except ModbusError as err:
            # The library already retried the transient failures this
            # device is known for; reaching here means the whole poll
            # failed. Ride out the first POLL_FAILURES_TOLERATED on the last
            # values (the next poll recovers in nearly every case), then
            # surface it as an ordinary failed update rather than letting it
            # fall through to DataUpdateCoordinator's "unexpected exception"
            # path, which would log a full traceback for an expected,
            # recoverable condition.
            if self.data is not None and self._failed_polls < POLL_FAILURES_TOLERATED:
                self._failed_polls += 1
                self.logger.debug(
                    "Poll failed (%d of %d tolerated), keeping the last values: %s",
                    self._failed_polls,
                    POLL_FAILURES_TOLERATED,
                    err,
                )
                return self.data
            raise UpdateFailed(str(err)) from err

        self._failed_polls = 0
        return result

    async def _async_read_settings_if_due(self) -> None:
        """Read the settings block when its own interval has come round.

        Runs inside the poll's lock, on the connection the poll just used. A
        failure here does not fail the poll: the settings keep their last
        values and the next cycle tries again, the reasoning behind
        POLL_FAILURES_TOLERATED applied to a block read a quarter as often.
        """
        if self._settings is None:
            return
        now = time.monotonic()
        if now < self._settings_due_at:
            return
        try:
            await self._settings.async_update_with_retry()
        except ModbusError as err:
            self.logger.debug("Settings read failed, keeping the last values: %s", err)
            return
        self._settings_values = dict(self._settings.values)
        self._settings_due_at = now + SETTINGS_SCAN_INTERVAL.total_seconds()

    async def _async_update_battery_packs(self, result: dict[str, Any]) -> None:
        """Overwrite the aggregate "Pack Summary" fields in result (they
        only report correctly at a different slave address than the main
        device's own - see aggregate_pack_summary()'s docstring), then read
        BC260 packs 2..N into result as pack_{n}_{field}.

        Balco260 only, per this integration's current scope - EP2000's
        battery-pack behavior is unconfirmed on real hardware. Packs share
        the main device's own Modbus connection (a different slave address,
        not a new TCP connection), so this must run after self._client.read()
        already established it, within the same update cycle.
        """
        if not isinstance(self.device, Balco260):
            return

        if self._aggregate_summary is None:
            self._aggregate_summary = aggregate_pack_summary(self._client.conn)
        await self._aggregate_summary.async_update_with_retry()
        result.update(self._aggregate_summary.values)

        # Individual packs - see INDIVIDUAL_BC260_PACKS_CONFIRMED's own
        # comment for the hardware this was confirmed on.
        if not INDIVIDUAL_BC260_PACKS_CONFIRMED:
            return

        num_packs = result.get("d_num_battery_packs")
        if not isinstance(num_packs, int):
            return

        for pack_num in range(2, min(num_packs, MAX_BATTERY_PACKS) + 1):
            pack = self._packs.get(pack_num)
            if pack is None:
                pack = battery_pack(self._client.conn, pack_slave_id(pack_num))
                self._packs[pack_num] = pack
            await pack.async_update_with_retry()
            # A slot that reports nothing but its serial number (every
            # other field 0 - a firmware issue BLUETTI has confirmed and
            # plans to fix) publishes nothing: its entities then read "No
            # data" and go unavailable, instead of showing 0 %, 0 V and the
            # 3000 A that b_c's raw 0 decodes to.
            if not pack_is_reporting(pack.values):
                continue
            for name, value in pack.values.items():
                result[f"pack_{pack_num}_{name}"] = value

    async def aclose(self) -> None:
        """Close the underlying Modbus connection."""
        await self._client.aclose()
