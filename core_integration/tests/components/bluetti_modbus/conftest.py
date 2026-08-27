"""Common fixtures for the Bluetti Modbus tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from modbus_connection.mock import MockModbusConnection
import pytest

from homeassistant.components.bluetti_modbus.const import DOMAIN
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

MOCK_USER_INPUT = {
    "host": "10.2.1.60",
    "port": 502,
    "unit_id": 1,
    "device_type": "balco260",
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry - for config-flow-only tests."""
    with patch(
        "homeassistant.components.bluetti_modbus.async_setup_entry",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_connection() -> MockModbusConnection:
    """A fake Modbus TCP connection seeded as a Balco260."""
    connection = MockModbusConnection()
    connection.for_unit(1).holding[50001] = 1  # d_num_inverters
    connection.for_unit(1).holding[51221] = 1000  # b_soc
    return connection


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Mock a Bluetti Modbus config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="10.2.1.60:502",
        data=MOCK_USER_INPUT,
        title="Bluetti balco260 (10.2.1.60)",
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> MockConfigEntry:
    """Set up the Bluetti Modbus integration for testing."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetti_modbus.async_get_unit",
        side_effect=lambda hass, entry, params, unit_id: mock_connection.for_unit(unit_id),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    return mock_config_entry
