"""Config flow for the Thomson Cable Modem integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_URL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN
from .parser import parse_diagnostics_page

_LOGGER = logging.getLogger(__name__)


class ThomsonModemConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thomson Cable Modem."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL]
            username = user_input.get(CONF_USERNAME, "")
            password = user_input.get(CONF_PASSWORD, "")
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            try:
                auth = None
                if username and password:
                    auth = aiohttp.BasicAuth(username, password)
                async with session.get(
                    url, auth=auth, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
                ) as response:
                    response.raise_for_status()
                    html = await response.text()
                    data = parse_diagnostics_page(html)
                    if not data.downstream and not data.upstream and not data.status:
                        errors["base"] = "no_data"
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("Unable to reach modem diagnostics page: %s", exc)
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    return self.async_create_entry(
                        title="Thomson Cable Modem",
                        data={
                            CONF_URL: url,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_SCAN_INTERVAL: scan_interval,
                        },
                    )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_URL, default="http://192.168.100.1/Diagnostics.asp"): str,
                vol.Optional(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
