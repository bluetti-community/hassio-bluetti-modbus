from collections.abc import Mapping
from typing import Any

CONF_ADDRESS = "address"
CONF_PORT = "port"
CONF_NAME = "name"
CONF_TYPE = "type"
CONF_SERIAL = "serial"
CONF_FIRMWARE_VERSION = "firmware_version"


class InitialDeviceConfig:
    def __init__(
        self,
        address: str,
        port: int,
        name: str,
        dev_type: str,
        serial: str | None = None,
        firmware_version: str | None = None,
    ):
        self.address = address
        self.port = port
        self.name = name
        self.dev_type = dev_type
        # Only ever known out-of-band, at zeroconf discovery time (see
        # config_flow.py) - never set by a manually added device
        # (async_step_user), which has no equivalent out-of-band source.
        # S Meter has no serial-equivalent Modbus register at all, so this
        # is its only possible source, ever - see _modbus_identity()'s own
        # docstring in __init__.py. Balco260 already gets a live one from
        # Modbus on every poll and doesn't need this as a fallback the way
        # S Meter does, but zeroconf discovery learns it anyway as a
        # byproduct of its own connectivity check - harmless to store: it's
        # never actually read back for a device whose live Modbus value is
        # already available (see device_info()'s own fallback order), and
        # gives a real, correct serial to show before that first live read
        # happens at all.
        self.serial = serial
        # Only ever known out-of-band too, from a best-effort query against
        # the S Meter's own undocumented WebSocket API during zeroconf
        # discovery (see smeter_ws.py) - captured once at add time and
        # never refreshed afterwards (unlike sw_version for other device
        # types, which is read live from Modbus on every poll), so this can
        # go stale after a firmware update. Accepted trade-off - see
        # smeter_ws.py's own docstring for why nothing better is available
        # for S Meter today.
        self.firmware_version = firmware_version

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> "InitialDeviceConfig | None":
        if not InitialDeviceConfig.has_values(raw):
            return None

        return InitialDeviceConfig(
            raw[CONF_ADDRESS],
            raw[CONF_PORT],
            raw[CONF_NAME],
            raw[CONF_TYPE],
            raw.get(CONF_SERIAL),
            raw.get(CONF_FIRMWARE_VERSION),
        )

    @property
    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            CONF_ADDRESS: self.address,
            CONF_PORT: self.port,
            CONF_NAME: self.name,
            CONF_TYPE: self.dev_type,
        }
        if self.serial is not None:
            data[CONF_SERIAL] = self.serial
        if self.firmware_version is not None:
            data[CONF_FIRMWARE_VERSION] = self.firmware_version
        return data

    @staticmethod
    def has_values(raw: Mapping[str, Any]) -> bool:
        return (
            isinstance(raw.get(CONF_ADDRESS), str)
            and isinstance(raw.get(CONF_PORT), int)
            and isinstance(raw.get(CONF_NAME), str)
            and isinstance(raw.get(CONF_TYPE), str)
        )
