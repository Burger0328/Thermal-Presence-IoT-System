# ESP32 thermal sensor firmware

The firmware reads an AMG8833 8x8 thermal array, estimates presence from the
peak-to-ambient temperature difference, and publishes readings over MQTT.

## Setup

1. Install PlatformIO.
2. Copy `.env.example` to `.env` and enter your network and MQTT settings.
3. Connect an AMG8833 to the ESP32-S3 over I2C.
4. Build and upload the `adafruit_feather_esp32s3` environment.

The device listens for `get_one`, `start_continuous`, and `stop` on
`<MQTT_TOPIC>/command`. It publishes JSON readings to `<MQTT_TOPIC>/readings`.

Never commit `.env`; it contains network credentials.
