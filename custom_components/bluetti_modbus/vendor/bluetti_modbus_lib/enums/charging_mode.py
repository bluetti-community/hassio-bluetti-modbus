from enum import IntEnum, unique


# bluetti-registers' "Charging Mode" enum (schemas/enums.json), the values
# the BLUETTI app's AC charging speed setting writes: on an AC200PL, Modbus
# register 57023 read 0, 1 and 2 as the app was switched between these three
# (bluetti-registers#48). IntEnum, not Enum: the field is writable, and
# modbus_connection's enum() encodes a write with int(value).
@unique
class ChargingMode(IntEnum):
    Standard = 0
    Silent = 1
    Turbo = 2
