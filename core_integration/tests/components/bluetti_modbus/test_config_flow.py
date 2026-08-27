"""Test the Bluetti Modbus config flow."""

from unittest.mock import AsyncMock, patch

from modbus_connection.exceptions import ModbusConnectionError
from modbus_connection.mock import MockModbusConnection
import pytest

from homeassistant import config_entries
from homeassistant.components.bluetti_modbus.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import MOCK_USER_INPUT as USER_INPUT


async def test_user_flow_success(
    hass: HomeAssistant,
    mock_connection: MockModbusConnection,
    mock_setup_entry: AsyncMock,
) -> None:
    """A reachable device creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(
        "homeassistant.components.bluetti_modbus.config_flow.async_get_temporary_unit"
    ) as mock_get_unit:
        mock_get_unit.return_value.__aenter__.return_value = mock_connection.for_unit(1)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    mock_setup_entry.assert_awaited_once()


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable device re-shows the form with an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.bluetti_modbus.config_flow.async_get_temporary_unit",
        side_effect=ModbusConnectionError("no route to host"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
