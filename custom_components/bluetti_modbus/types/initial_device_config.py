from typing import Any

CONF_ADDRESS = "address"
CONF_PORT = "port"
CONF_NAME = "name"
CONF_TYPE = "type"


class InitialDeviceConfig:
    def __init__(
        self,
        address: str,
        port: int,
        name: str,
        dev_type: str,
    ):
        self.address = address
        self.port = port
        self.name = name
        self.dev_type = dev_type

    @staticmethod
    def from_dict(raw: dict[str, Any]):
        if not InitialDeviceConfig.has_values(raw):
            return None

        return InitialDeviceConfig(
            raw.get(CONF_ADDRESS),
            raw.get(CONF_PORT),
            raw.get(CONF_NAME),
            raw.get(CONF_TYPE),
        )

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            CONF_ADDRESS: self.address,
            CONF_PORT: self.port,
            CONF_NAME: self.name,
            CONF_TYPE: self.dev_type,
        }

    @staticmethod
    def has_values(raw: dict[str, Any]) -> bool:
        return (
            isinstance(raw.get(CONF_ADDRESS), str)
            and isinstance(raw.get(CONF_PORT), int)
            and isinstance(raw.get(CONF_NAME), str)
            and isinstance(raw.get(CONF_TYPE), str)
        )
