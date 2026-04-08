<p align="center">
  <img src="logo.png" alt="Powershop NZ" height="120">
</p>

# Powershop New Zealand — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/PMKA/Powershop-nz-HACS.svg)](https://github.com/PMKA/Powershop-nz-HACS/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/PMKA/Powershop-nz-HACS.svg)](https://github.com/PMKA/Powershop-nz-HACS/commits/main)

A Home Assistant custom component for **Powershop New Zealand** customers. Monitor your account balance and time-of-use electricity rates, updated every 15 minutes.

## Features

- **Account Balance** — current balance in NZD
- **Time-of-Use Rates** — off-peak, peak, and shoulder rates in c/kWh
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

This integration is **not officially affiliated** with Powershop. Use at your own risk, i just wanted my powershop data in HA :)
