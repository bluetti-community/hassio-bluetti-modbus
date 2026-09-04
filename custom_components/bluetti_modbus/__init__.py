"""Bluetti Modbus Integration"""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DATA_COORDINATOR,
    DEVICE_TYPE_DISPLAY_NAMES,
    DOMAIN,
    FIELDS_SHOWN_VIA_SWITCH,
    MANUFACTURER,
)
from .coordinator import PollingCoordinator
from .types import FullDeviceConfig as FullDeviceConfig
from .vendor.bluetti_modbus_lib import PACK_INFO_FIELDS

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bluetti Powerstation from a config entry."""

    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return False

    logger = logging.getLogger(f"{__name__}.{config.address}")

    logger.debug("Init Bluetti Modbus Integration")

    # Create data structure
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})

    # Create coordinator for polling
    logger.debug("Creating coordinator")
    coordinator = PollingCoordinator(
        hass,
        entry,
        config,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id].setdefault(DATA_COORDINATOR, coordinator)

    # Registered explicitly, before the platforms below create any entity:
    # S Meter's per-phase sub-devices (see phase_device_info()) link back to
    # this device via via_device_id, which only resolves against a device
    # already in the registry - matches home-assistant/core's shelly
    # integration, which registers its own main device the same way before
    # forwarding to platforms (ShellyRpcCoordinator.async_setup()).
    main_device_info = device_info(entry, coordinator)
    if main_device_info is not None:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, **main_device_info
        )

    logger.debug("Creating entities")
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    logger.debug("Setup done")

    return True


_CURRENT_VERSION = 10


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current version.

    Steps cascade through a local `version` variable rather than re-checking
    entry.version after each one and calling async_update_entry per step -
    an entry several versions behind must catch up entirely within this one
    call (HA only calls this function once per setup attempt), and relying
    on async_update_entry to mutate entry.version in place for that would
    make the cascade only as trustworthy as that side effect.

    1 -> 2: d_timestamp (S Meter, register 55112) switched to disabled by
    default (field_metadata.py), but entity_registry_enabled_default only
    applies the first time an entity is ever registered - an entry set up
    before that change already has the entity registered as enabled, and
    nothing about bumping this integration's version changes that on its
    own (confirmed against home-assistant/core's entity_registry.py:
    async_get_or_create() only passes disabled_by down the "create" path,
    never "update"). Disable it explicitly, once, here instead - and only
    if it's still enabled, so this never fights a user who re-enables it
    themselves afterward.

    2 -> 3: d_serial/d_ver_arm/d_ver_dsp (Balco260/EP2000) are no longer
    separate sensors - they feed DeviceInfo instead (see device_info()),
    matching bluetti-home-assistant's identical fix. Entities from before
    this change don't disappear on their own just because the code stops
    creating them, so remove them explicitly, once.

    3 -> 4: config_flow.py's default title used to strip every separator out
    of the address and port instead of keeping them - re.sub("[^A-Za-z0-9]+",
    "", "192.168.1.128" + "502") produced "1921681128502" instead of
    something legible. That broken title cascades into DeviceInfo.name, and
    when a sensor's own translation hasn't loaded yet, HA falls back to
    showing the device name for it - so this could show up as every
    sensor's displayed name, not just the config entry's own title. Fix it
    once here, but only if the title still matches exactly what the old code
    would have produced - never overwrite a title the user has since
    customized themselves.

    4 -> 5: "Balco260" (the product's real name is "Balco 260", two words,
    matching "S Meter") was used without a space in DEVICE_TYPE_DISPLAY_NAMES
    and therefore in every title built from it, including by the 3 -> 4 step
    above. Add the missing space, once, but only if the title still starts
    with the old unspaced prefix exactly.

    5 -> 6: config_flow.py no longer appends the serial number (or, lacking
    one, the address) to the default title - just the plain product name,
    matching how other integrations name a single device. Drop the
    now-unwanted suffix, once, but only if the title still matches exactly
    what the old code would have produced: either "<type> (<address>)", or
    "<type> " followed by nothing but digits (a serial number - not
    reconstructible exactly at migration time, since that needs a live
    device read this function doesn't have, so digits-only is the closest
    safe check without risking a coincidental match against something the
    user typed themselves).

    6 -> 7: ac_o_switch/g_i_switch/g_o_switch (Balco260's AC output/grid
    charging/grid feed-in controls) are no longer plain sensors - they're
    switch.py entities now, wherever bluetti_modbus_lib marks them
    writable=True. Entities from before this change don't disappear on their
    own just because the code stops creating them as sensors, so remove
    those old sensor entities explicitly, once - matches the 2 -> 3 step's
    identical pattern for d_serial/d_ver_arm/d_ver_dsp.

    7 -> 8: b_ver_1 (the battery's own BMS firmware version) is no longer a
    plain sensor - it joins ARM/DSP in DeviceInfo.sw_version instead (see
    _modbus_identity()), now that bluetti_modbus_lib decodes it into the
    same dotted major.minor.patch format, confirmed against real hardware
    and the Bluetti app. Remove the old sensor entity explicitly, once -
    matches the 2 -> 3 and 6 -> 7 steps' identical pattern. b_ver_2/3/4 are
    untouched - unlike b_ver_1, their meaning isn't confirmed, so they stay
    plain sensors.

    8 -> 9: d_iot_ver (the IoT/communication module's own firmware version)
    is no longer a plain sensor - it joins ARM/DSP/BMS in
    DeviceInfo.sw_version instead, for the same reason and using the same
    dotted format as the 7 -> 8 step. Remove the old sensor entity
    explicitly, once - matches the 2 -> 3, 6 -> 7, and 7 -> 8 steps'
    identical pattern. d_iot_model/d_iot_serial are untouched - DeviceInfo
    only has one name/model/serial slot each, already taken by the main
    device's own identity.

    9 -> 10: the battery (PACK_INFO_FIELDS, Balco260's own built-in one) gets
    its own sub-device now, like BC200 packs 2..5 already had - see
    battery_device_info() and sensor.py. Its serial_number/sw_version come
    from b_serial/b_ver_1 (the battery's own identity) instead of the main
    device's d_iot_serial/d_iot_ver/d_ver_arm/d_ver_dsp - and d_iot_serial
    ("IoT SN") replaces d_serial ("Inverter SN") as the main device's own
    serial_number, since a Balco260/EP2000 exposes 3 different serials
    (inverter/battery/IoT module) and only one can be "the" device's.
    d_serial becomes a plain sensor for the first time (never one before);
    every PACK_INFO_FIELDS name except b_ver_1 (already retired at 7 -> 8)
    was a plain sensor on the main device and needs its old entity removed,
    same pattern as every step above - they're all on the battery
    sub-device now.
    """
    version = entry.version
    if version >= _CURRENT_VERSION:
        return True

    config = FullDeviceConfig.from_dict(entry.data)
    registry = er.async_get(hass)
    new_title: str | None = None

    if version == 1:
        if config is not None and config.dev_type == "smeter":
            unique_id = get_unique_id(f"{entry.title} d_timestamp")
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                existing = registry.async_get(entity_id)
                if existing is not None and existing.disabled_by is None:
                    registry.async_update_entity(
                        entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )
        version = 2

    if version == 2:
        # Frozen to exactly what was true when this step was written - not
        # FIELDS_SHOWN_VIA_DEVICE_INFO, whose live contents have since
        # changed (b_ver_1 moved to the battery sub-device at the 7 -> 8
        # step, d_serial dropped and d_iot_serial added at 9 -> 10) in ways
        # this historical step was never about.
        if config is not None and config.dev_type in ("balco260", "ep2000"):
            for field_name in ("d_serial", "d_ver_arm", "d_ver_dsp"):
                unique_id = get_unique_id(f"{entry.title} {field_name}")
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
                if entity_id is not None:
                    registry.async_remove(entity_id)
        version = 3

    if version == 3:
        if config is not None:
            old_default = re.sub(
                "[^A-Za-z0-9]+", "", config.address + str(config.port)
            )
            if entry.title == old_default:
                display_type = DEVICE_TYPE_DISPLAY_NAMES.get(
                    config.dev_type, config.dev_type
                )
                new_title = f"{display_type} ({config.address})"
        version = 4

    if version == 4:
        # A cascading entry (version was 3 a moment ago) already has its new
        # title in new_title, not yet on entry.title - check that instead.
        title_to_check = new_title if new_title is not None else entry.title
        if title_to_check.startswith("Balco260 "):
            new_title = "Balco 260 " + title_to_check[len("Balco260 ") :]
        version = 5

    if version == 5:
        title_to_check = new_title if new_title is not None else entry.title
        if config is not None:
            display_type = DEVICE_TYPE_DISPLAY_NAMES.get(
                config.dev_type, config.dev_type
            )
            prefix = f"{display_type} "
            if title_to_check == f"{display_type} ({config.address})" or (
                title_to_check.startswith(prefix)
                and title_to_check[len(prefix) :].isdigit()
            ):
                new_title = display_type
        version = 6

    if version == 6:
        if config is not None and config.dev_type in ("balco260", "ep2000"):
            for field_name in FIELDS_SHOWN_VIA_SWITCH:
                unique_id = get_unique_id(f"{entry.title} {field_name}")
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
                if entity_id is not None:
                    registry.async_remove(entity_id)
        version = 7

    if version == 7:
        if config is not None and config.dev_type in ("balco260", "ep2000"):
            unique_id = get_unique_id(f"{entry.title} b_ver_1")
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)
        version = 8

    if version == 8:
        if config is not None and config.dev_type in ("balco260", "ep2000"):
            unique_id = get_unique_id(f"{entry.title} d_iot_ver")
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)
        version = 9

    if version == 9:
        if config is not None and config.dev_type in ("balco260", "ep2000"):
            unique_id = get_unique_id(f"{entry.title} d_iot_serial")
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)
            # Every PACK_INFO_FIELDS name except b_ver_1 (already retired at
            # the 7 -> 8 step) was a plain sensor on the main device -
            # they're all battery sub-device sensors now (see
            # battery_device_info() and sensor.py).
            for field_name in PACK_INFO_FIELDS:
                if field_name == "b_ver_1":
                    continue
                unique_id = get_unique_id(f"{entry.title} {field_name}")
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
                if entity_id is not None:
                    registry.async_remove(entity_id)
        version = 10

    if new_title is not None:
        hass.config_entries.async_update_entry(entry, title=new_title, version=version)
    else:
        hass.config_entries.async_update_entry(entry, version=version)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator: PollingCoordinator = data[DATA_COORDINATOR]
        await coordinator.async_shutdown()
        await coordinator.aclose()

    return unloaded


def _modbus_identity(coordinator: PollingCoordinator | None) -> tuple[str | None, str | None]:
    """(serial_number, sw_version) from d_iot_serial/d_iot_ver/d_ver_arm/
    d_ver_dsp, if read yet.

    d_iot_serial (the IoT/communication module's own serial number, per the
    official register spec's "IoT SN" abbreviation) is what
    DeviceInfo.serial_number uses - not d_serial (the inverter's own
    "Inverter SN") or b_serial (the battery's own "Pack SN", now the battery
    sub-device's own identity - see battery_device_info()). Unlike bluetti-
    home-assistant (which discards every serial - a cloud-known one already
    covers that role there), this integration has no such other source, so
    one of these three has to be picked as "the" serial; d_iot_serial was
    chosen as the closest match to "the unit itself", confirmed against real
    hardware and the user's own installation. (None, None) before the
    coordinator's first successful refresh, or if no coordinator is given
    (e.g. S Meter, which doesn't declare these fields at all).

    b_ver_1 (BMS, the battery's own firmware) is deliberately not here - it
    moved to battery_device_info()'s own sw_version, since BMS is the
    battery's firmware, not the main unit's.
    """
    if coordinator is None:
        return None, None
    data = coordinator.data or {}
    serial = data.get("d_iot_serial")
    iot = data.get("d_iot_ver")
    arm = data.get("d_ver_arm")
    dsp = data.get("d_ver_dsp")
    serial_number = str(serial) if serial is not None else None
    sw_version = None
    if iot is not None or arm is not None or dsp is not None:
        sw_version = (
            f"IoT v{iot if iot is not None else '?'}, "
            f"ARM v{arm if arm is not None else '?'}, "
            f"DSP v{dsp if dsp is not None else '?'}"
        )
    return serial_number, sw_version


def device_info(
    entry: ConfigEntry, coordinator: PollingCoordinator | None = None
) -> DeviceInfo | None:
    """Device info.

    coordinator is only needed to fill in serial_number/sw_version (from
    d_iot_serial/d_iot_ver/d_ver_arm/d_ver_dsp) - omit it for a per-entity DeviceInfo dict
    (sensor.py/binary_sensor.py/number.py), where entity_platform only ever
    applies the keys actually present, so leaving these two out there never
    overwrites what async_setup_entry's own main-device registration
    already set with a coordinator.
    """
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    info = DeviceInfo(
        identifiers={(DOMAIN, config.address)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_DISPLAY_NAMES.get(config.dev_type, config.dev_type),
        # The device's own local web server, the same one Modbus TCP has to
        # be enabled through in the first place - see the README's setup
        # steps. Port 80: the Modbus port (config.port) is a different,
        # unrelated service on the same device.
        configuration_url=f"http://{config.address}",
    )

    # Only set when actually known (coordinator given and already read at
    # least once) - a key present with value None would overwrite what the
    # main device registration already set, see this function's docstring.
    serial_number, sw_version = _modbus_identity(coordinator)
    if serial_number is not None:
        info["serial_number"] = serial_number
    if sw_version is not None:
        info["sw_version"] = sw_version

    return info


def phase_device_info(
    hass: HomeAssistant, entry: ConfigEntry, phase: str
) -> DeviceInfo | None:
    """Device info for one of S Meter's per-phase sub-devices (phase: 'a'/'b'/'c')."""
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    return DeviceInfo(
        identifiers={(DOMAIN, f"{config.address}-phase-{phase}")},
        name=f"{entry.title} Phase {phase.upper()}",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_DISPLAY_NAMES.get(config.dev_type, config.dev_type),
        # Groups this sub-device under the main S Meter device on the
        # Devices page, the same way home-assistant/core's shelly
        # integration groups its own per-channel energy-meter sub-devices
        # under one physical Shelly Pro 3EM (get_rpc_device_info() there).
        # The main device is registered explicitly in async_setup_entry()
        # above before this can ever be resolved.
        via_device_id=dr.async_get_device_id_by_identifier(
            hass, (DOMAIN, config.address), config_entry_id=entry.entry_id
        ),
    )


def pack_device_info(
    hass: HomeAssistant, entry: ConfigEntry, pack_num: int
) -> DeviceInfo | None:
    """Device info for one of Balco260's BC200 battery pack sub-devices.

    pack_num: 2..MAX_BATTERY_PACKS - pack 1's data is shown on the main
    device (same Modbus slave address), see coordinator.py's
    _async_update_battery_packs().
    """
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    return DeviceInfo(
        identifiers={(DOMAIN, f"{config.address}-pack-{pack_num}")},
        name=f"{entry.title} Pack {pack_num}",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_DISPLAY_NAMES.get(config.dev_type, config.dev_type),
        # Groups this sub-device under the main Balco260 device on the
        # Devices page - same pattern as phase_device_info() above. The main
        # device is registered explicitly in async_setup_entry() above
        # before this can ever be resolved.
        via_device_id=dr.async_get_device_id_by_identifier(
            hass, (DOMAIN, config.address), config_entry_id=entry.entry_id
        ),
    )


def battery_device_info(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: PollingCoordinator | None = None
) -> DeviceInfo | None:
    """Device info for Balco260's own built-in battery, as a sub-device.

    Unlike BC200 packs 2..MAX_BATTERY_PACKS (pack_device_info() above), this
    one always exists - a Balco260 always has a built-in battery - so unlike
    those, it doesn't depend on d_num_battery_packs having been read yet.

    serial_number/sw_version come from b_serial ("Pack SN") and b_ver_1
    ("BMS", the battery's own firmware) - both properties of the battery
    itself, not the main unit (which uses d_iot_serial/d_iot_ver/d_ver_arm/
    d_ver_dsp instead, see _modbus_identity()). coordinator is optional for
    the same reason as device_info()'s own docstring explains: omit it for a
    per-entity DeviceInfo dict, where leaving these keys out never overwrites
    what async_setup_entry's own registration already set with one.
    """
    config = FullDeviceConfig.from_dict(entry.data)

    if config is None:
        return None

    info = DeviceInfo(
        identifiers={(DOMAIN, f"{config.address}-battery")},
        name=f"{entry.title} Battery",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_DISPLAY_NAMES.get(config.dev_type, config.dev_type),
        # Groups this sub-device under the main Balco260 device on the
        # Devices page - same pattern as pack_device_info() above. The main
        # device is registered explicitly in async_setup_entry() above
        # before this can ever be resolved.
        via_device_id=dr.async_get_device_id_by_identifier(
            hass, (DOMAIN, config.address), config_entry_id=entry.entry_id
        ),
    )

    if coordinator is not None:
        data = coordinator.data or {}
        serial = data.get("b_serial")
        bms = data.get("b_ver_1")
        if serial is not None:
            info["serial_number"] = str(serial)
        if bms is not None:
            info["sw_version"] = f"BMS v{bms}"

    return info


def get_unique_id(name: str, sensor_type: str | None = None) -> str:
    """Generate an unique id."""
    res = re.sub("[^A-Za-z0-9]+", "_", name).lower()
    if sensor_type is not None:
        return f"{sensor_type}.{res}"
    return res
