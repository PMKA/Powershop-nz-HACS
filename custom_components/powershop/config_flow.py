"""Config flow for Powershop integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .api import PowershopAPIClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

class PowershopConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Powershop."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            client = None
            try:
                # Test authentication
                client = PowershopAPIClient(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD]
                )
                
                auth_result = await client.authenticate()
                if auth_result and client.customer_id:
                    # Check if already configured
                    customer_id_for_unique = client.customer_id if client.customer_id != "unknown" else user_input[CONF_USERNAME]
                    await self.async_set_unique_id(customer_id_for_unique)
                    self._abort_if_unique_id_configured()
                    
                    # Clean up test client
                    await client.close()
                    
                    return self.async_create_entry(
                        title=f"Powershop ({user_input[CONF_USERNAME]})",
                        data={
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            "customer_id": client.customer_id,
                        },
                    )
                else:
                    _LOGGER.error(f"Authentication failed for {user_input[CONF_USERNAME]}")
                    errors["base"] = "invalid_auth"
                    
            except Exception as e:
                _LOGGER.error(f"Config flow error: {e}")
                errors["base"] = "cannot_connect"
            finally:
                # Ensure client is cleaned up
                if client:
                    try:
                        await client.close()
                    except Exception:
                        pass  # Ignore cleanup errors

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )