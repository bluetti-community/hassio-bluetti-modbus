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


_POWER = FieldMetadata(device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT)
_VOLTAGE = FieldMetadata(device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT)
_CURRENT = FieldMetadata(device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT)
_ENERGY_DIAGNOSTIC = FieldMetadata(
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    category=EntityCategory.DIAGNOSTIC,
)
_DIAGNOSTIC = FieldMetadata(category=EntityCategory.DIAGNOSTIC)
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
    "b_soc_total": FieldMetadata(device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT),
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
    "d_status": _DIAGNOSTIC,
    "d_timestamp": _DIAGNOSTIC,
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
}


def metadata_for(field_name: str) -> FieldMetadata:
    """Return the HA entity metadata for a field, or a metadata-less default."""
    return FIELD_METADATA.get(field_name, FieldMetadata())
