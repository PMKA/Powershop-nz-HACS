# Powershop HACS Integration for Home Assistant

A Home Assistant custom component that allows you to monitor your Powershop New Zealand electricity rates.

## Features

- Monitor current electricity rates (c/kWh)
- View time-of-use rate periods (Off Peak, Peak, Shoulder)
- Automatic authentication with Powershop NZ
- Regular updates every 15 minutes
- Extract detailed rate information from HTML tooltips

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL
6. Select "Integration" as the category
7. Click "Add"
8. Find "Powershop" in the list and install it
9. Restart Home Assistant

### Manual Installation

1. Download the `powershop_hacs` folder
2. Copy it to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to Configuration > Integrations
2. Click "Add Integration"
3. Search for "Powershop"
4. Enter your Powershop account credentials:
   - Email address
   - Password
5. Click "Submit"

The integration will automatically detect your customer ID and set up sensors.

## Sensors

- `sensor.off_peak_rate`: Off-peak rate (typically 12am-7am)
- `sensor.peak_rate`: Peak rate (typically morning/evening) 
- `sensor.shoulder_rate`: Shoulder rate (typically midday)

## Attributes

Each sensor includes focused attributes for its specific rate period:
- `customer_id`: Your Powershop customer ID
- `last_updated`: When the data was last refreshed
- `period_name`: The full name of the rate period (e.g., "Off Peak")
- `time_range`: The time period when this rate applies (e.g., "12am - 7am")
- `rate_value`: The rate value in cents per kWh
- `rate_formatted`: Human-readable formatted rate (e.g., "19.08 c/kWh")

### Time-of-Use Information
When available, the integration extracts detailed rate periods including:
- Off Peak (typically 12am-7am): Lowest rates
- Peak (typically 7am-11am, 5pm-9pm): Highest rates  
- Shoulder (typically 11am-5pm): Mid-range rates

Each period includes the time range and specific rate in c/kWh.

## Troubleshooting

### Authentication Issues
- Verify your email and password are correct
- Check that your account is active
- Ensure you can log in to the Powershop website

### Rate Data Not Updating
- Check the Home Assistant logs for errors
- The integration updates every 15 minutes
- Rate changes may take time to appear on the Powershop website
- Ensure you can see rate information when logged into Powershop website

### Account Lockout Protection
- The integration includes rate limiting to prevent account lockouts
- If authentication fails 3 times, it will stop trying
- Wait 5 seconds minimum between authentication attempts
- Use "Reset Password" on Powershop website if account gets locked

## Security

- Your credentials are stored securely in Home Assistant
- The integration uses HTTPS for all communications
- Session cookies are managed automatically

## Support

For issues or feature requests, please use the GitHub repository's issue tracker.

## Disclaimer

This integration is not officially affiliated with Powershop. Use at your own risk.