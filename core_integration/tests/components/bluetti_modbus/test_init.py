"""Test Bluetti Modbus setup."""

from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


async def test_setup_entry(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """A config entry sets up successfully and produces sensor entities."""
    assert init_integration.state.value == "loaded"
    state = hass.states.get("sensor.bluetti_balco260_10_2_1_60_number_of_inverters")
    assert state is not None
    assert state.state == "1"
