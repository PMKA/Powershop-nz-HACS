"""Powershop sensors."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import PowershopAPIClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)

SENSORS = [
    SensorEntityDescription(
        key="off_peak_rate",
        name="Off Peak Rate",
        native_unit_of_measurement="c/kWh",
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="peak_rate",
        name="Peak Rate", 
        native_unit_of_measurement="c/kWh",
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        icon="mdi:clock-alert",
    ),
    SensorEntityDescription(
        key="shoulder_rate",
        name="Shoulder Rate",
        native_unit_of_measurement="c/kWh", 
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        icon="mdi:clock",
    ),
]

class PowershopDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from Powershop API."""

    def __init__(self, hass: HomeAssistant, client: PowershopAPIClient) -> None:
        """Initialize."""
        self.client = client
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def async_shutdown(self) -> None:
        """Clean up resources."""
        await self.client.close()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data via library."""
        try:
            # Ensure we're still authenticated
            if not self.client.customer_id:
                auth_result = await self.client.authenticate()
                if not auth_result:
                    raise UpdateFailed("Authentication failed")
            
            # Get rate data
            rate_data = await self.client.get_rate_data()
            rate_data['last_updated'] = datetime.now()
            
            # Get usage data if available
            try:
                usage_data = await self.client.get_usage_data()
                rate_data.update(usage_data)
            except Exception as e:
                _LOGGER.warning(f"Could not fetch usage data: {e}")
                rate_data['usage_available'] = False
            
            return rate_data
            
        except aiohttp.ClientError as e:
            raise UpdateFailed(f"Network error: {e}")
        except Exception as e:
            raise UpdateFailed(f"Error communicating with API: {e}")

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    
    # Get credentials from config
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    
    # Create API client
    client = PowershopAPIClient(username, password)
    
    # Create coordinator
    coordinator = PowershopDataUpdateCoordinator(hass, client)
    
    # Store coordinator for cleanup
    hass.data[DOMAIN][f"{config_entry.entry_id}_coordinator"] = coordinator
    
    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()
    
    # Create sensors
    entities = []
    for sensor_description in SENSORS:
        entities.append(PowershopSensor(coordinator, sensor_description))
    
    async_add_entities(entities)

class PowershopSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Powershop sensor."""

    def __init__(
        self,
        coordinator: PowershopDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{coordinator.client.customer_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.client.customer_id)},
            "name": f"Powershop Account {coordinator.client.customer_id}",
            "manufacturer": "Powershop",
            "model": "Customer Account",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        rate_periods = self.coordinator.data.get("rate_periods", {})
        
        if self.entity_description.key == "off_peak_rate":
            # Look for off-peak rate
            for period_name, period_data in rate_periods.items():
                if "off peak" in period_name.lower():
                    return period_data["rate"]
            return None
            
        elif self.entity_description.key == "peak_rate":
            # Look for peak rate (prefer weekday peak)
            for period_name, period_data in rate_periods.items():
                if "peak" in period_name.lower() and "weekday" in period_name.lower():
                    return period_data["rate"]
            # Fallback to any peak
            for period_name, period_data in rate_periods.items():
                if "peak" in period_name.lower():
                    return period_data["rate"]
            return None
            
        elif self.entity_description.key == "shoulder_rate":
            # Look for shoulder rate
            for period_name, period_data in rate_periods.items():
                if "shoulder" in period_name.lower():
                    return period_data["rate"]
            return None
        
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
            
        # Basic attributes for all sensors
        attrs = {
            "customer_id": self.coordinator.client.customer_id,
            "last_updated": self.coordinator.data.get("last_updated"),
        }
        
        rate_periods = self.coordinator.data.get("rate_periods", {})
        
        # Find the specific period data for this sensor
        period_data = None
        period_name = None
        
        if self.entity_description.key == "off_peak_rate":
            for name, data in rate_periods.items():
                if "off peak" in name.lower():
                    period_data = data
                    period_name = name
                    break
                    
        elif self.entity_description.key == "peak_rate":
            # Prefer weekday peak
            for name, data in rate_periods.items():
                if "peak" in name.lower() and "weekday" in name.lower():
                    period_data = data
                    period_name = name
                    break
            # Fallback to any peak
            if not period_data:
                for name, data in rate_periods.items():
                    if "peak" in name.lower():
                        period_data = data
                        period_name = name
                        break
                        
        elif self.entity_description.key == "shoulder_rate":
            for name, data in rate_periods.items():
                if "shoulder" in name.lower():
                    period_data = data
                    period_name = name
                    break
        
        # Add sensor-specific attributes
        if period_data and period_name:
            attrs.update({
                "period_name": period_name,
                "time_range": period_data["time_range"],
                "rate_value": period_data["rate"],
                "rate_formatted": period_data["rate_formatted"]
            })
        
        return attrs