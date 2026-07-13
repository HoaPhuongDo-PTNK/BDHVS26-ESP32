"""Shared BLE contract for the ESP32 switch and desktop controller."""

DEVICE_NAME_PREFIX = "SMART_SWITCH_"
LED_SERVICE_UUID = "a0000001-0000-1000-8000-00805f9b34fb"
LED_CHAR_UUID = "a0000002-0000-1000-8000-00805f9b34fb"


def encode_led_state(is_on):
    return bytes([1 if is_on else 0])


def decode_led_state(payload):
    return bool(payload and payload[0] & 1)
