from typing import Any, Dict

from .InitialDeviceConfig import InitialDeviceConfig


class FullDeviceConfig:
    def __init__(
        self,
        initial: InitialDeviceConfig,
    ):
        self.address = initial.address
        self.port = initial.port
        self.name = initial.name
        self.dev_type = initial.dev_type

    @staticmethod
    def from_dict(raw: Dict[str, Any]):
        initial = InitialDeviceConfig.from_dict(raw)

        if initial is None:
            return None

        return FullDeviceConfig(
            initial,
        )
