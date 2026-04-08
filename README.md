<p align="center">
  <img src="logo.png" alt="Powershop NZ" height="120">
</p>

# Powershop New Zealand — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/PMKA/Powershop-nz-HACS.svg)](https://github.com/PMKA/Powershop-nz-HACS/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/PMKA/Powershop-nz-HACS.svg)](https://github.com/PMKA/Powershop-nz-HACS/commits/main)

A Home Assistant custom component for **Powershop New Zealand** customers. Monitor your account balance, electricity rates, usage, and Power Pack coverage — updated every 15 minutes.

## Features

- **Account Balance** — current balance in NZD
- **Time-of-Use Rates** — off-peak, peak, and shoulder rates in c/kWh
- **Usage Monitoring** — today's kWh and billing period kWh
- **Billing Gauges** — mirrors the Powershop app: used cost, estimated total, pack coverage %, and still-to-buy shortfall for the current period
- **Power Pack Tracking** — total redeemable pack balance and full pack list; upcoming 5 billing periods show estimated cost vs packs already purchased
- **Passwordless Auth** — uses Powershop's email OTP login (no password stored)
- **Automatic Token Refresh** — stays authenticated silently in the background
- **Regular Updates** — 15-minute refresh interval

## Requirements

- A Powershop NZ account at [app.powershop.nz](https://app.powershop.nz)
- Home Assistant 2024.1 or later
- HACS (for managed installation)

## Installation

### Via HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click the three dots (⋮) in the top right corner → **Custom repositories**
4. Add `https://github.com/PMKA/Powershop-nz-HACS` and select **Integration**
5. Click **Add**, then find **Powershop NZ** in the list and install it
6. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/powershop/` folder into your HA config's `custom_components/` directory
3. Restart Home Assistant

## Configuration

Authentication uses a one-time password (OTP) sent to your email — no password required:

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Powershop**
3. Enter your Powershop account email address and click **Submit**
4. Check your email for the one-time code and enter it, then click **Submit**

The integration will automatically discover your account number and property ID. Your session is maintained with a long-lived refresh token stored securely in Home Assistant.

### Re-authentication

If your session expires, Home Assistant will prompt you to re-authenticate. Simply repeat the OTP process above.

## Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.powershop_balance` | Current account balance | NZD |
| `sensor.powershop_off_peak_rate` | Off-peak electricity rate | c/kWh |
| `sensor.powershop_peak_rate` | Peak electricity rate | c/kWh |
| `sensor.powershop_shoulder_rate` | Shoulder electricity rate | c/kWh |
| `sensor.powershop_usage_today` | kWh consumed today (last 24 h) | kWh |
| `sensor.powershop_usage_billing_period` | kWh consumed this billing period | kWh |
| `sensor.powershop_cost_billing_period` | Estimated total cost this billing period (= EST) | NZD |
| `sensor.powershop_period_used_cost` | Confirmed actual spend this billing period (= USED) | NZD |
| `sensor.powershop_period_estimated_cost` | Full projected cost this billing period (= EST) | NZD |
| `sensor.powershop_period_still_to_buy` | Pack shortfall — how much more you need to purchase (= STILL TO BUY) | NZD |
| `sensor.powershop_period_coverage_pct` | % of estimated bill covered by current packs | % |
| `sensor.powershop_voucher_balance` | Total redeemable Power Pack balance | NZD |

### Sensor Attributes

**`sensor.powershop_period_estimated_cost`** includes an `upcoming_periods` attribute — a list of the next 5 billing periods, each containing:

```yaml
- period_start: "2026-05-06"
  period_end: "2026-06-05"
  cost_estimated_nzd: 390.78     # projected cost based on your usage pattern
  voucher_bought_nzd: 0.00       # packs pre-purchased for that specific month
  cost_still_to_buy_nzd: 390.78  # shortfall
  coverage_pct: 0.0
```

**`sensor.powershop_voucher_balance`** includes a `vouchers` attribute listing every active pack with its name, available-from date, remaining balance, and original value.

## Troubleshooting

### Didn't receive the OTP email
- Check your spam/junk folder
- Ensure you're using the email address registered with your Powershop account
- Try again — OTP codes expire after a few minutes

### Sensors show "unavailable"
- Check **Settings → System → Logs** for errors prefixed with `powershop`
- The integration will automatically trigger re-authentication if the session has expired

### Rate data not updating
- Rates are fetched every 15 minutes; changes on Powershop's end may take a cycle to appear
- Confirm your account is active at [app.powershop.nz](https://app.powershop.nz)

## 📝 Changelog

### v2.3.0 (2026-04-09)
- Added `Used This Billing Period` sensor — actual confirmed spend (USED in app)
- Added `Estimated Cost This Billing Period` sensor — full projected monthly cost (EST in app)
- Added `Still To Buy This Billing Period` sensor — pack shortfall warning
- Added `Billing Period Pack Coverage` sensor — % of estimated bill covered by packs
- `period_estimated_cost` sensor exposes `upcoming_periods` attribute with 5-month forward forecast (estimated cost + pre-purchased packs per period)
- Updated Power Pack query to use `availableBeforeDate`/`availableFromDate` filters matching the website's per-period breakdown
- Daily measurements now use a dedicated date-range query that includes `readingQuality` (ACTUAL vs ESTIMATED)

### v2.2.0
- Added usage sensors (today kWh, billing period kWh, billing period cost)
- Added Power Pack / voucher balance sensor

### v2.0.0 (2026-04-08)
- Full rewrite for the new Powershop app (`app.powershop.nz`)
- Replaced HTML scraping with Firebase OTP authentication + GraphQL API
- Added account balance sensor
- Passwordless login — no password ever stored
- Automatic session refresh with long-lived tokens
- Re-authentication support via HA config flow

### v1.0.0 (2025-11-10)
- Initial release
- Rate monitoring via the legacy `secure.powershop.co.nz` site

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

##  Disclaimer

This integration is **not officially affiliated** with Powershop. Use at your own risk, I just wanted to have my rate data available in HA, reached out to Powershop to ask for API access but was nothing available so built my own.
