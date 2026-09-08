"""Constants for the Bluetti Modbus integration."""

DOMAIN = "bluetti_modbus"
MANUFACTURER = "Bluetti"

CONF_OPTIONS = "options"

DATA_COORDINATOR = "coordinator"

# AC500 support (bluetti-modbus 0.15.0+) is community-confirmed against real
# hardware, not yet BLUETTI-support-confirmed like Balco260/S Meter - see
# bluetti-official/bluetti-modbus-tcp-slave#5. It was deliberately shipped
# as a beta pre-release (0.0.39-beta.1 through beta.5, GitHub "prerelease"
# flag) to keep it out of regular users' default update list while it was
# still being iterated on - `main` is a single linear branch, so any later,
# ordinary (non-beta) release built from it would otherwise have carried
# AC500 right along with it, since the code never left `main`.
#
# This flag decoupled AC500's visibility from release/version mechanics
# entirely: config_flow.py only offers "ac500" in its dropdown while this
# is True, regardless of what version is installed. Existing config entries
# already using "ac500" (from testing on the beta line) are unaffected
# either way - this only ever gated the dropdown for *new* entries.
#
# Flipped to True: ItsMe00007 confirmed the beta-line fixes (dc_o_switch
# naming, pv_1/2_i_type disabled, IoT v? firmware display, battery SoC
# device class) working on a real AC500 inside a real HA install and asked
# for AC500 to join the normal release line - see the discussion on
# bluetti-official/bluetti-modbus-tcp-slave#5.
AC500_CONFIRMED = True

# Balco 500 (bluetti-modbus 0.19.0+) reuses Balco260's own register set -
# BLUETTI's own official register spec files both under the same generic
# "BalcoXX" tab, not a Balco260-specific one (see bluetti-community/
# bluetti-registers#27). Unlike AC500, no community member has a physical
# unit yet at all, so this isn't just BLUETTI-support-unconfirmed the way
# AC500 is - it's entirely untested against real hardware. Same mechanism
# as AC500_CONFIRMED above: config_flow.py only offers "balco500" in its
# dropdown while this is True, decoupled from release/version mechanics.
# Flip to True once someone can actually test it on a real Balco 500.
BALCO500_CONFIRMED = False

# dev_type (config_flow's stored, lowercase value) -> the product's real
# display name, for DeviceInfo.model. Without this, the Devices page would
# show the raw stored string ("smeter") instead of "S Meter".
DEVICE_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "ac500": "AC500",
    "balco260": "Balco 260",
    "balco500": "Balco 500",
    "smeter": "S Meter",
}

# S Meter's per-phase fields (modbus-tcp/smeter.json) group under their own
# sub-device, one per phase - matches how Shelly's Pro 3EM integration groups
# its own per-channel energy-meter entities (home-assistant/core's shelly
# component, get_rpc_device_info()/via_device_id), rather than dumping all 31
# fields flat on one device. Everything else on S Meter (status, timestamp,
# grid frequency, and the *_total/*_avg/*_unbalance aggregates) stays on the
# main device - there's no phase to attribute them to.
SMETER_PHASE_FIELDS: dict[str, tuple[str, ...]] = {
    "a": ("ac_a_v", "ac_a_c", "ac_a_p", "ac_a_p_reactive", "ac_a_p_apparent", "ac_a_pf"),
    "b": ("ac_b_v", "ac_b_c", "ac_b_p", "ac_b_p_reactive", "ac_b_p_apparent", "ac_b_pf"),
    "c": ("ac_c_v", "ac_c_c", "ac_c_p", "ac_c_p_reactive", "ac_c_p_apparent", "ac_c_pf"),
}

# d_status (55111) decodes to a bool already (bluetti_modbus_lib's
# bit_flag()) - a confirmed, single-bit online status, unlike this project's
# other undecoded bitmap/status registers. Routed to binary_sensor.py
# instead of sensor.py, which only handles numeric/enum/string values.
FIELDS_SHOWN_VIA_BINARY_SENSOR = {"d_status"}

# d_inverter_fault/d_inverter_warning: no entity at all, on any platform.
# bluetti_modbus_lib's InverterFault/InverterWarning enums only declare
# their zero member (NoFault = 0 / NoWarning = 0), so a real, non-zero
# fault or warning code has nothing to decode to - modbus_connection
# decodes an unrecognized enum value to None, which reaches HA as
# "unknown". That means these read a steady "No Fault"/"No Warning" right
# up until something actually goes wrong, and then go blank: worse than
# absent, since a user watching them would read the blank as a glitch
# rather than the alarm it really is. Bring them back as binary sensors or
# proper enum sensors once the library decodes real codes - the same call
# the Core integration made for the same reason
# (home-assistant/core#180602's own EXCLUDED_FIELDS).
FIELDS_NOT_SHOWN = {"d_inverter_fault", "d_inverter_warning"}

# g_i_switch (57009, same address as Balco260's, a real switch there): reads
# a clean, error-free 1 regardless of state on real AC500 hardware, per two
# independent testers (bluetti-official/bluetti-modbus-tcp-slave#5,
# bluetti-community/bluetti-registers#13: "the AC500 does not have Grid
# Input/output switches") - a stuck, always-1 reading carries no real
# information, so it doesn't even earn a diagnostic sensor. Balco260/EP2000
# are unaffected - g_i_switch is a genuine, working switch there (see
# FIELDS_SHOWN_VIA_SWITCH below). A flat set, not a dict keyed by dev_type
# like DEVICE_TYPE_DISPLAY_NAMES above - AC500 is the only device with a
# per-field exclusion like this so far, and a dict for one entry would be
# premature.
AC500_FIELDS_NOT_SHOWN = {"g_i_switch"}

# b_soc_low/b_soc_high (57016/57017): battery empty/full SOC thresholds,
# 0-100% - genuinely user-configurable settings, not readings. Routed to
# number.py instead of sensor.py, but only where bluetti_modbus_lib actually
# marks the field writable=True (currently Balco260 only - see that
# library's import.py) - sensor.py falls back to its normal read-only
# handling for a device where it isn't, so nothing is lost there.
FIELDS_SHOWN_VIA_NUMBER = {"b_soc_low", "b_soc_high"}

# ac_o_switch/g_i_switch/g_o_switch (57001/57009/57010, Balco260) and
# dc_o_switch (57005, AC500 only) - AC output, grid charging, grid feed-in,
# and DC output controls - genuinely user-actuated switches, not readings.
# Routed to switch.py instead of sensor.py, but only where
# bluetti_modbus_lib actually marks the field writable=True (Balco260's
# ac_o_switch/g_i_switch/g_o_switch, and - each independently confirmed on
# real hardware by a different tester, see
# bluetti-official/bluetti-modbus-tcp-slave#5 - AC500's ac_o_switch/
# dc_o_switch; AC500's own g_i_switch is confirmed non-functional there
# instead, see AC500_FIELDS_NOT_SHOWN above), same gating as
# FIELDS_SHOWN_VIA_NUMBER below - sensor.py falls back to its normal
# read-only handling for a device where a name here isn't writable, so
# nothing is lost there.
FIELDS_SHOWN_VIA_SWITCH = {"ac_o_switch", "dc_o_switch", "g_i_switch", "g_o_switch"}

# d_ver_arm/d_ver_dsp/d_iot_ver/d_serial (Balco260/EP2000 only - S Meter's
# address range doesn't include these): the main unit's own identity, not
# readings - fed into the main DeviceInfo (serial_number/sw_version, see
# _modbus_identity() in __init__.py) instead of shown as plain sensors.
# d_serial ("Inverter SN") is DeviceInfo.serial_number - confirmed by
# BLUETTI support directly (email, 2026-09-06): the app's own "Numéro de
# série" (the unqualified, primary one - distinct from "Numéro de série
# carte de communication") is exactly the device model name prefixed to
# this register's decoded uint64 value (e.g. "Balco2602611110033917").
# d_iot_serial ("IoT SN", the communication/IoT module's own identity - what
# the app itself calls the *secondary* serial) previously held this slot;
# now demoted to a plain sensor, same treatment BLUETTI's own app gives it.
# Not b_serial ("Pack SN", the battery's own - see
# FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO below). d_iot_model stays a plain
# sensor - DeviceInfo only has one name/model slot, already taken by the
# main device's own identity.
FIELDS_SHOWN_VIA_DEVICE_INFO = {"d_ver_arm", "d_ver_dsp", "d_iot_ver", "d_serial"}

# b_serial/b_ver_1 (part of PACK_INFO_FIELDS, i.e. Balco260's built-in
# battery, address block 51200-51249): the battery's own identity, not
# readings - fed into the battery sub-device's own DeviceInfo instead (see
# battery_device_info() in __init__.py), same reasoning as
# FIELDS_SHOWN_VIA_DEVICE_INFO above but for the battery specifically.
# b_serial ("Pack SN") is the battery sub-device's serial_number; b_ver_1
# ("BMS", the battery's own firmware, confirmed against real hardware and
# the Bluetti app) is its sw_version. Every other PACK_INFO_FIELDS name
# becomes a plain sensor on that same sub-device instead of the main
# device - see sensor.py.
FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO = {"b_serial", "b_ver_1"}

# d_num_battery_packs is now read correctly (bluetti_modbus_lib's
# aggregate_pack_summary(), slave 250 - see coordinator.py), but real
# hardware testing on a Balco260 with 3 confirmed, app-active BC260 packs
# found individual pack data (battery_pack(), slave 2 and up) still reads a
# clean, error-free 0 for every field - indistinguishable from a Balco260
# with zero packs attached (see bluetti-community/bluetti-modbus's own
# README caveat on battery_pack(), added the same day this was found).
#
# Creating per-pack devices/entities now that d_num_battery_packs is
# accurate would surface them showing 0% SOC, 0V, no serial, etc. for every
# real pack beyond the first - worse than not showing them at all, since it
# reads as a broken sensor rather than an absent feature. Keep this False
# until BLUETTI clarifies the actual mechanism (a follow-up email is
# pending) and it's confirmed against real hardware; flip it back on then -
# this is the only gate needed, both coordinator.py and sensor.py check it
# before doing anything with packs 2+.
INDIVIDUAL_BC260_PACKS_CONFIRMED = False
