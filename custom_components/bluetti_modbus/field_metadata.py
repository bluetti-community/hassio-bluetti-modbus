"""
Home Assistant entity metadata (device_class/state_class/entity_category) for
each bluetti_modbus_lib field name.

This lives here, not in bluetti_modbus_lib, deliberately: device_class,
state_class, and entity_category are Home Assistant entity concepts, not
Modbus/protocol ones - they describe how a value should be presented in an
HA UI, which is this integration's job, not the device library's. (Feedback
from Paul Schoutsen, applied by removing the library's own
FieldCategory/FieldStateClass/DeviceClass enums.)

Built from bluetti-registers' modbus-tcp/balco260.json schema, which still
carries this classification as data.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory


@dataclass(frozen=True)
class FieldMetadata:
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    category: EntityCategory | None = None
    enabled_by_default: bool = True


_POWER = FieldMetadata(device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT)
_VOLTAGE = FieldMetadata(device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT)
_CURRENT = FieldMetadata(device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT)
_ENERGY_DIAGNOSTIC = FieldMetadata(
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    category=EntityCategory.DIAGNOSTIC,
)
_DIAGNOSTIC = FieldMetadata(category=EntityCategory.DIAGNOSTIC)
# The official register spec (55112, "Unix timestamp") has no remark beyond
# "Read" - it's the meter's own internal clock reading, not something anyone
# watches day to day. Off by default so it doesn't add to entity clutter;
# still available to enable manually for whoever does want it.
_DIAGNOSTIC_DISABLED = FieldMetadata(category=EntityCategory.DIAGNOSTIC, enabled_by_default=False)
_DIAGNOSTIC_MEASUREMENT = FieldMetadata(
    state_class=SensorStateClass.MEASUREMENT, category=EntityCategory.DIAGNOSTIC
)
_CONFIG = FieldMetadata(category=EntityCategory.CONFIG)
_REACTIVE_POWER = FieldMetadata(
    device_class=SensorDeviceClass.REACTIVE_POWER, state_class=SensorStateClass.MEASUREMENT
)
_APPARENT_POWER = FieldMetadata(
    device_class=SensorDeviceClass.APPARENT_POWER, state_class=SensorStateClass.MEASUREMENT
)
_POWER_FACTOR = FieldMetadata(
    device_class=SensorDeviceClass.POWER_FACTOR, state_class=SensorStateClass.MEASUREMENT
)
_MEASUREMENT = FieldMetadata(state_class=SensorStateClass.MEASUREMENT)
_DURATION = FieldMetadata(device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT)

FIELD_METADATA: dict[str, FieldMetadata] = {
    "d_num_inverters": _DIAGNOSTIC,
    "ac_o_p_total": _POWER,
    "pv_i_p_total": _POWER,
    "g_i_p_total": _POWER,
    "d_inverter_total": _POWER,
    "pv_ac_p": _POWER,
    "ac_o_e_total": _ENERGY_DIAGNOSTIC,
    "pv_i_e_total": _ENERGY_DIAGNOSTIC,
    "g_i_e_total": _ENERGY_DIAGNOSTIC,
    "g_o_e_total": _ENERGY_DIAGNOSTIC,
    "pv_ac_e": _ENERGY_DIAGNOSTIC,
    "d_inverter_status": _DIAGNOSTIC,
    "d_inverter_warning": _DIAGNOSTIC,
    "d_inverter_fault": _DIAGNOSTIC,
    "d_inverter_type": _DIAGNOSTIC,
    "g_i_f": FieldMetadata(device_class=SensorDeviceClass.FREQUENCY, state_class=SensorStateClass.MEASUREMENT),
    "pv_1_i_p": _POWER,
    "pv_1_i_v": _VOLTAGE,
    "pv_1_i_c": _CURRENT,
    "pv_2_i_p": _POWER,
    "pv_2_i_v": _VOLTAGE,
    "pv_2_i_c": _CURRENT,
    "pv_3_i_p": _POWER,
    "pv_3_i_v": _VOLTAGE,
    "pv_3_i_c": _CURRENT,
    "pv_4_i_p": _POWER,
    "pv_4_i_v": _VOLTAGE,
    "pv_4_i_c": _CURRENT,
    "d_num_battery_packs": _DIAGNOSTIC,
    "b_v_total": _VOLTAGE,
    "b_c_total": _CURRENT,
    # Not device_class=BATTERY - a device can only have one "the battery"
    # entity for HA's Devices-page summary column, and b_soc (the per-pack,
    # always-populated reading) is that one. b_soc_total read 0 on a bare
    # Balco260 with no BC200 pack while b_soc read 76% at the same moment
    # (confirmed against real hardware) - two BATTERY-class sensors on one
    # device made HA's summary column pick the wrong one.
    "b_soc_total": _MEASUREMENT,
    "b_soh_total": _DIAGNOSTIC_MEASUREMENT,
    "b_type": _DIAGNOSTIC,
    "b_v": _VOLTAGE,
    "b_c": _CURRENT,
    "b_soc": FieldMetadata(device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT),
    "b_soh": _DIAGNOSTIC_MEASUREMENT,
    "b_cycle_count": _DIAGNOSTIC_MEASUREMENT,
    "b_t_avg": FieldMetadata(device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    "b_cell_count": _DIAGNOSTIC,
    "b_ntc_count": _DIAGNOSTIC,
    "b_i_e": _ENERGY_DIAGNOSTIC,
    "b_o_e": _ENERGY_DIAGNOSTIC,
    "ac_o_switch": FieldMetadata(),
    "g_i_switch": FieldMetadata(),
    "g_o_switch": FieldMetadata(),
    "b_soc_low": _CONFIG,
    "b_soc_high": _CONFIG,
    # S Meter (modbus-tcp/smeter.json) - g_i_f/g_i_e_total/g_o_e_total above
    # are shared field names with Balco260 and already covered.
    # d_status (55111) isn't here - it's a binary_sensor (see const.py's
    # FIELDS_SHOWN_VIA_BINARY_SENSOR), not a sensor.
    "d_timestamp": _DIAGNOSTIC_DISABLED,
    "ac_a_v": _VOLTAGE,
    "ac_b_v": _VOLTAGE,
    "ac_c_v": _VOLTAGE,
    "ac_a_c": _CURRENT,
    "ac_b_c": _CURRENT,
    "ac_c_c": _CURRENT,
    "ac_a_p": _POWER,
    "ac_b_p": _POWER,
    "ac_c_p": _POWER,
    "ac_a_p_reactive": _REACTIVE_POWER,
    "ac_b_p_reactive": _REACTIVE_POWER,
    "ac_c_p_reactive": _REACTIVE_POWER,
    "ac_a_p_apparent": _APPARENT_POWER,
    "ac_b_p_apparent": _APPARENT_POWER,
    "ac_c_p_apparent": _APPARENT_POWER,
    "ac_a_pf": _POWER_FACTOR,
    "ac_b_pf": _POWER_FACTOR,
    "ac_c_pf": _POWER_FACTOR,
    "ac_v_avg": _VOLTAGE,
    "ac_c_avg": _CURRENT,
    "ac_c_unbalance": _MEASUREMENT,
    "ac_c_total": _CURRENT,
    "ac_p_total": _POWER,
    "ac_p_reactive_total": _REACTIVE_POWER,
    "ac_p_apparent_total": _APPARENT_POWER,
    "ac_pf_total": _POWER_FACTOR,
    # The 65 fields added by a later bluetti-registers sync (see
    # field_metadata.py's git history / translations/en.json) never got
    # entries here - each fell back to metadata_for()'s bare, icon-less
    # default. Real installation, real report: every one of these showed up
    # with no icon at all, unlike their already-categorized siblings above.
    "ac_1_o_c": _CURRENT,
    "ac_1_o_p": _POWER,
    "ac_1_o_v": _VOLTAGE,
    "ac_2_o_c": _CURRENT,
    "ac_2_o_p": _POWER,
    "ac_2_o_v": _VOLTAGE,
    "ac_3_o_c": _CURRENT,
    "ac_3_o_p": _POWER,
    "ac_3_o_v": _VOLTAGE,
    "ac_o_e_local": _ENERGY_DIAGNOSTIC,
    "ac_o_p_local": _POWER,
    "ac_phase_count": _DIAGNOSTIC,
    "b_alarm_portable": _DIAGNOSTIC,
    "b_alarm_residential": _DIAGNOSTIC,
    "b_error": _DIAGNOSTIC,
    "b_protect": _DIAGNOSTIC,
    "b_serial": _DIAGNOSTIC,
    "b_status": _DIAGNOSTIC,
    # b_time_to_full/empty (pack-level) and their _total (all-packs)
    # counterparts read 0 whenever the battery isn't actively charging or
    # discharging (confirmed against real hardware: 0 while b_status is
    # "Idle") - that's the device correctly reporting "no ETA to estimate
    # right now", not a decode bug.
    "b_time_to_empty": _DURATION,
    "b_time_to_empty_total": _DURATION,
    "b_time_to_full": _DURATION,
    "b_time_to_full_total": _DURATION,
    # b_ver_1 isn't here - it feeds DeviceInfo.sw_version instead (see
    # const.py's FIELDS_SHOWN_VIA_DEVICE_INFO). b_ver_2/3/4 stay plain
    # sensors - their meaning isn't confirmed the way b_ver_1's is.
    "b_ver_2": _DIAGNOSTIC,
    "b_ver_3": _DIAGNOSTIC,
    "b_ver_4": _DIAGNOSTIC,
    "d_inverter_1_c": _CURRENT,
    "d_inverter_1_p": _POWER,
    "d_inverter_1_status": _DIAGNOSTIC,
    "d_inverter_1_v": _VOLTAGE,
    "d_inverter_2_c": _CURRENT,
    "d_inverter_2_p": _POWER,
    "d_inverter_2_status": _DIAGNOSTIC,
    "d_inverter_2_v": _VOLTAGE,
    "d_inverter_3_c": _CURRENT,
    "d_inverter_3_p": _POWER,
    "d_inverter_3_status": _DIAGNOSTIC,
    "d_inverter_3_v": _VOLTAGE,
    "d_inverter_phase_count": _DIAGNOSTIC,
    "d_iot_model": _DIAGNOSTIC,
    # d_iot_serial (the IoT/communication module's own serial number) is a
    # third, distinct serial from d_serial (the inverter's own, already in
    # DeviceInfo.serial_number) and b_serial (the battery pack's own,
    # confirmed against the official register spec's own abbreviations:
    # "Inverter SN", "Pack SN", "IoT SN" respectively) - HA's DeviceInfo only
    # has room for one serial_number, so this one stays its own sensor.
    "d_iot_serial": _DIAGNOSTIC,
    # d_iot_ver isn't here - it joins ARM/DSP/BMS in DeviceInfo.sw_version
    # instead (see const.py's FIELDS_SHOWN_VIA_DEVICE_INFO).
    "d_phase_count": _DIAGNOSTIC,
    "d_self_consumption": _MEASUREMENT,
    "g_1_i_c": _CURRENT,
    "g_1_i_p": _POWER,
    "g_1_i_v": _VOLTAGE,
    "g_2_i_c": _CURRENT,
    "g_2_i_p": _POWER,
    "g_2_i_v": _VOLTAGE,
    "g_3_i_c": _CURRENT,
    "g_3_i_p": _POWER,
    "g_3_i_v": _VOLTAGE,
    "g_i_e_local": _ENERGY_DIAGNOSTIC,
    "g_i_p_local": _POWER,
    "g_o_e_local": _ENERGY_DIAGNOSTIC,
    # pv_1-4_i_type: an enum (0/1/2/3 = reserve/car/adapter/other, 100/101 =
    # DC PV/AC PV per the official register spec's remark column - not
    # sequential) - bluetti_modbus_lib doesn't decode it yet, so this reads
    # as a raw int (100 on real hardware) rather than a label for now.
    # Diagnostic either way.
    "pv_1_i_type": _DIAGNOSTIC,
    "pv_2_i_type": _DIAGNOSTIC,
    "pv_3_i_type": _DIAGNOSTIC,
    "pv_4_i_type": _DIAGNOSTIC,
    "pv_ac_e_local": _ENERGY_DIAGNOSTIC,
    "pv_ac_p_local": _POWER,
    "pv_count": _DIAGNOSTIC,
    "pv_i_e_local": _ENERGY_DIAGNOSTIC,
    "pv_i_p_local": _POWER,
}


def metadata_for(field_name: str) -> FieldMetadata:
    """Return the HA entity metadata for a field, or a metadata-less default."""
    return FIELD_METADATA.get(field_name, FieldMetadata())
