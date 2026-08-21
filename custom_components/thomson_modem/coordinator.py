"""Data update coordinator for the Thomson Cable Modem integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN
from .parser import ModemDiagnostics, parse_diagnostics_page

_LOGGER = logging.getLogger(__name__)


class ThomsonModemCoordinator(DataUpdateCoordinator[ModemDiagnostics]):
    """Fetch diagnostics from a Thomson cable modem."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the coordinator."""
        self._url = config[CONF_URL]
        self._username = config.get(CONF_USERNAME, "")
        self._password = config.get(CONF_PASSWORD, "")
        self._session = async_get_clientsession(hass)

        update_interval = timedelta(
            seconds=config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> ModemDiagnostics:
        """Fetch and parse the diagnostics page."""
        auth = None
        if self._username and self._password:
            auth = aiohttp.BasicAuth(self._username, self._password)

        try:
            async with self._session.get(
                self._url,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                response.raise_for_status()
                html = await response.text()
        except aiohttp.ClientError as exc:
            _LOGGER.error("Failed to connect to modem at %s: %s", self._url, exc)
            raise UpdateFailed(f"Error communicating with modem: {exc}") from exc

        data = parse_diagnostics_page(html)
        if not data:
            raise UpdateFailed("No usable diagnostic data found on the page")

        return data
