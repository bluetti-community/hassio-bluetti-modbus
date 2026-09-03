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

# d_serial/d_ver_arm/d_ver_dsp/b_ver_1/d_iot_ver (Balco260/EP2000 only - S
# Meter's address range doesn't include these): the device's own identity,
# not readings - fed into DeviceInfo (serial_number/sw_version) instead of
# shown as plain sensors. d_serial/d_ver_arm/d_ver_dsp match bluetti-home-
# assistant's identical fix for those three fields (there they're excluded
# outright since a cloud-known serial already covers d_serial's role; there
# is no such other source here, so d_serial's own decoded value is what
# DeviceInfo.serial_number uses). b_ver_1 (the battery's own BMS firmware
# version) and d_iot_ver (the IoT/communication module's own firmware
# version) join ARM/DSP in sw_version for the same reason - it's part of
# "what firmware is this device running", not a sensor reading; both are
# confirmed against real hardware and the Bluetti app. b_ver_2/3/4 stay
# plain sensors - unlike b_ver_1, their meaning isn't confirmed (they read 0
# on real hardware with no BC200 pack attached). d_iot_model/d_iot_serial
# also stay plain sensors - DeviceInfo only has one name/model/serial slot
# each, already taken by the main device's own identity.
FIELDS_SHOWN_VIA_DEVICE_INFO = {"d_serial", "d_ver_arm", "d_ver_dsp", "b_ver_1", "d_iot_ver"}
