"""Constants for the Bluetti Modbus integration."""

DOMAIN = "bluetti_modbus"
MANUFACTURER = "Bluetti"

CONF_OPTIONS = "options"

DATA_COORDINATOR = "coordinator"

# dev_type (config_flow's stored, lowercase value) -> the product's real
# display name, for DeviceInfo.model. Without this, the Devices page would
# show the raw stored string ("smeter") instead of "S Meter".
DEVICE_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "balco260": "Balco 260",
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

# b_soc_low/b_soc_high (57016/57017): battery empty/full SOC thresholds,
# 0-100% - genuinely user-configurable settings, not readings. Routed to
# number.py instead of sensor.py, but only where bluetti_modbus_lib actually
# marks the field writable=True (currently Balco260 only - see that
# library's import.py) - sensor.py falls back to its normal read-only
# handling for a device where it isn't, so nothing is lost there.
FIELDS_SHOWN_VIA_NUMBER = {"b_soc_low", "b_soc_high"}

# ac_o_switch/g_i_switch/g_o_switch (57001/57009/57010): AC output, grid
# charging, and grid feed-in controls - genuinely user-actuated switches, not
# readings. Routed to switch.py instead of sensor.py, but only where
# bluetti_modbus_lib actually marks the field writable=True (currently
# Balco260 only - see that library's import.py), same gating as
# FIELDS_SHOWN_VIA_NUMBER below - sensor.py falls back to its normal
# read-only handling for a device where it isn't, so nothing is lost there.
FIELDS_SHOWN_VIA_SWITCH = {"ac_o_switch", "g_i_switch", "g_o_switch"}

# d_ver_arm/d_ver_dsp/d_iot_ver/d_iot_serial (Balco260/EP2000 only - S
# Meter's address range doesn't include these): the main unit's own
# identity, not readings - fed into the main DeviceInfo (serial_number/
# sw_version, see _modbus_identity() in __init__.py) instead of shown as
# plain sensors. d_iot_serial ("IoT SN") is DeviceInfo.serial_number - not
# d_serial ("Inverter SN", now just a plain diagnostic sensor - EP2000/
# Balco260 both actually expose 3 different serials: inverter, battery, and
# IoT module; only one can be "the" device serial, and d_iot_serial was
# chosen as the closest match to "the unit itself") and not b_serial
# ("Pack SN", the battery's own - see FIELDS_SHOWN_VIA_BATTERY_DEVICE_INFO
# below). d_iot_model stays a plain sensor - DeviceInfo only has one
# name/model slot, already taken by the main device's own identity.
FIELDS_SHOWN_VIA_DEVICE_INFO = {"d_ver_arm", "d_ver_dsp", "d_iot_ver", "d_iot_serial"}

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
