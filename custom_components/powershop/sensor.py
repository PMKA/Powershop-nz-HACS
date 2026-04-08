"""Powershop sensors."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_DOLLAR, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import AuthError, PowershopAPIClient
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_PROPERTY_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)

# Keyword sets used for matching rate labels from the API
_OFF_PEAK_KEYWORDS = {"off peak", "offpeak", "night", "low", "uncontrolled"}
_PEAK_KEYWORDS = {"peak", "day", "weekday peak", "high"}
_SHOULDER_KEYWORDS = {"shoulder", "weekend", "controlled"}
_STANDING_KEYWORDS = {"daily", "standing", "fixed", "supply"}

SENSORS = [
    SensorEntityDescription(
        key="balance",
        name="Balance",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-usd",
    ),
    SensorEntityDescription(
        key="off_peak_rate",
        name="Off Peak Rate",
        native_unit_of_measurement="c/kWh",
        state_class=None,
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="peak_rate",
        name="Peak Rate",
        native_unit_of_measurement="c/kWh",
        state_class=None,
        icon="mdi:clock-alert",
    ),
    SensorEntityDescription(
        key="shoulder_rate",
        name="Shoulder Rate",
        native_unit_of_measurement="c/kWh",
        state_class=None,
        icon="mdi:clock",
    ),
    SensorEntityDescription(
        key="usage_today",
        name="Usage Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:lightning-bolt",
    ),
    SensorEntityDescription(
        key="usage_billing_period",
        name="Usage This Billing Period",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:lightning-bolt-circle",
    ),
    SensorEntityDescription(
        key="cost_billing_period",
        name="Cost This Billing Period",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
    ),
    SensorEntityDescription(
        key="voucher_balance",
        name="Voucher Balance",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:ticket-percent",
    ),
    SensorEntityDescription(
        key="period_used_cost",
        name="Used This Billing Period",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-check",
    ),
    SensorEntityDescription(
        key="period_estimated_cost",
        name="Estimated Cost This Billing Period",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-clock",
    ),
    SensorEntityDescription(
        key="period_still_to_buy",
        name="Still To Buy This Billing Period",
        native_unit_of_measurement="NZD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cart-plus",
    ),
    SensorEntityDescription(
        key="period_coverage_pct",
        name="Billing Period Pack Coverage",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
    ),
]


def _match_rate(rate_periods: Dict[str, Any], keywords: set) -> Optional[float]:
    """Return the first rate whose label contains any of *keywords*."""
    for label, data in rate_periods.items():
        if any(kw in label.lower() for kw in keywords):
            return data.get("rate")
    return None


class PowershopDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetching data from the Powershop GraphQL API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PowershopAPIClient,
        config_entry: ConfigEntry,
    ) -> None:
        self.client = client
        self._config_entry = config_entry
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def async_shutdown(self) -> None:
        await self.client.close()

    async def _async_update_data(self) -> Dict[str, Any]:
        account_number = self._config_entry.data[CONF_ACCOUNT_NUMBER]
        property_id = self._config_entry.data.get(CONF_PROPERTY_ID)

        try:
            data = await self.client.get_rate_data(account_number, property_id)
        except AuthError as err:
            # Refresh token expired/revoked – trigger HA re-auth flow
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Powershop API: {err}") from err

        # If the refresh token was rotated, persist the new one
        if self.client.refresh_token != self._config_entry.data.get(CONF_REFRESH_TOKEN):
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={
                    **self._config_entry.data,
                    CONF_REFRESH_TOKEN: self.client.refresh_token,
                },
            )

        data["last_updated"] = datetime.now()
        return data


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Powershop sensor platform."""
    client = PowershopAPIClient(
        refresh_token=config_entry.data[CONF_REFRESH_TOKEN]
    )
    coordinator = PowershopDataUpdateCoordinator(hass, client, config_entry)

    hass.data[DOMAIN][f"{config_entry.entry_id}_coordinator"] = coordinator

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        PowershopSensor(coordinator, description, config_entry)
        for description in SENSORS
    )


class PowershopSensor(CoordinatorEntity, SensorEntity):
    """A sensor that reads from the Powershop coordinator."""

    def __init__(
        self,
        coordinator: PowershopDataUpdateCoordinator,
        description: SensorEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        account_number = config_entry.data.get(CONF_ACCOUNT_NUMBER, "unknown")
        self._attr_unique_id = f"{DOMAIN}_{account_number}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, account_number)},
            "name": f"Powershop Account {account_number}",
            "manufacturer": "Powershop NZ",
            "model": "Customer Account",
        }

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None

        data = self.coordinator.data
        key = self.entity_description.key

        if key == "balance":
            return data.get("balance")

        rate_periods = data.get("rate_periods", {})

        if key == "off_peak_rate":
            return _match_rate(rate_periods, _OFF_PEAK_KEYWORDS)
        if key == "peak_rate":
            return _match_rate(rate_periods, _PEAK_KEYWORDS)
        if key == "shoulder_rate":
            return _match_rate(rate_periods, _SHOULDER_KEYWORDS)
        if key == "usage_today":
            return data.get("usage_today_kwh")
        if key == "usage_billing_period":
            return data.get("usage_period_kwh")
        if key == "cost_billing_period":
            return data.get("cost_period_nzd")
        if key == "voucher_balance":
            return data.get("voucher_balance_nzd")
        if key == "period_used_cost":
            return data.get("cost_used_nzd")
        if key == "period_estimated_cost":
            return data.get("cost_estimated_nzd")
        if key == "period_still_to_buy":
            return data.get("cost_still_to_buy_nzd")
        if key == "period_coverage_pct":
            return data.get("period_coverage_pct")

        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data
        attrs: Dict[str, Any] = {
            "account_number": data.get("account_number"),
            "last_updated": data.get("last_updated"),
        }

        if self.entity_description.key == "balance":
            attrs["next_billing_date"] = data.get("next_billing_date")
            attrs["overdue_balance"] = data.get("overdue_balance")

        if self.entity_description.key == "cost_billing_period":
            attrs["billing_period_start"] = data.get("period_start")
            attrs["billing_period_end"] = data.get("period_end")

        if self.entity_description.key == "period_estimated_cost":
            attrs["billing_period_start"] = data.get("period_start")
            attrs["billing_period_end"] = data.get("period_end")
            attrs["upcoming_periods"] = data.get("upcoming_periods", [])

        if self.entity_description.key == "voucher_balance":
            attrs["voucher_count"] = data.get("voucher_count")
            attrs["vouchers"] = data.get("voucher_list", [])

        rate_periods = data.get("rate_periods", {})
        if self.entity_description.key in ("off_peak_rate", "peak_rate", "shoulder_rate"):
            attrs["all_rates"] = {
                label: d.get("rate_formatted") for label, d in rate_periods.items()
            }

        return attrs
