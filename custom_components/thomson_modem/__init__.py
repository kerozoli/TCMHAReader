"""The Thomson Cable Modem integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ThomsonModemCoordinator

PLATFORMS = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


type ThomsonModemConfigEntry = ConfigEntry[ThomsonModemCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ThomsonModemConfigEntry) -> bool:
    """Set up Thomson Cable Modem from a config entry."""
    coordinator = ThomsonModemCoordinator(hass, entry.data)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThomsonModemConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
