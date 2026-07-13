"""MicroPython firmware for the ESP32-C6 smart switch."""

try:
    import aioble
    import bluetooth
    import time
    from machine import Pin
    import uasyncio as asyncio
    import ble_contract
except ImportError:  # pragma: no cover - desktop test fallback
    aioble = None
    bluetooth = None
    time = None
    Pin = None
    asyncio = None
    ble_contract = None


DEVICE_ID = "1"
GPIO_PIN_SWITCH = 8
GPIO_PIN_LED = 9
DEVICE_NAME = "{}{}".format(ble_contract.DEVICE_NAME_PREFIX, DEVICE_ID) if ble_contract else "SMART_SWITCH_1"

_LED_SERVICE_UUID = (
    bluetooth.UUID(ble_contract.LED_SERVICE_UUID) if bluetooth and ble_contract else None
)
_LED_CHAR_UUID = (
    bluetooth.UUID(ble_contract.LED_CHAR_UUID) if bluetooth and ble_contract else None
)

DEBOUNCE_MS = 200


def _ticks_diff(now_ms, start_ms):
    if time is not None and hasattr(time, "ticks_diff"):
        return time.ticks_diff(now_ms, start_ms)
    return now_ms - start_ms


class PushSwitchDebouncer:
    """Return one toggle event per stable push button press."""

    def __init__(self, debounce_ms=DEBOUNCE_MS):
        self.debounce_ms = debounce_ms
        self._pressed_since_ms = None
        self._waiting_for_release = False

    def update(self, pressed, now_ms):
        if self._waiting_for_release:
            if not pressed:
                self._pressed_since_ms = None
                self._waiting_for_release = False
            return False

        if pressed:
            if self._pressed_since_ms is None:
                self._pressed_since_ms = now_ms
                return False
            if _ticks_diff(now_ms, self._pressed_since_ms) >= self.debounce_ms:
                self._waiting_for_release = True
                self._pressed_since_ms = None
                return True
        else:
            self._pressed_since_ms = None

        return False


class SmartSwitchApp:
    def __init__(self):
        if aioble is None or bluetooth is None or Pin is None or asyncio is None:
            raise RuntimeError("This firmware must run on MicroPython for ESP32.")

        self.led_is_on = False
        self.led_pin = Pin(GPIO_PIN_LED, Pin.OUT)
        self.switch_pin = Pin(GPIO_PIN_SWITCH, Pin.IN, Pin.PULL_UP)
        self.debouncer = PushSwitchDebouncer(DEBOUNCE_MS)

        self.led_service = aioble.Service(_LED_SERVICE_UUID)
        self.led_char = aioble.Characteristic(
            self.led_service,
            _LED_CHAR_UUID,
            read=True,
            write=True,
            notify=True,
            capture=True,
        )
        aioble.register_services(self.led_service)
        self.set_led(False)

    def set_led(self, is_on):
        self.led_is_on = bool(is_on)
        if self.led_is_on:
            self.led_pin.on()
        else:
            self.led_pin.off()

    def toggle_led(self):
        self.set_led(not self.led_is_on)

    def read_switch_pressed(self):
        return self.switch_pin.value() == 0

    def poll_switch(self):
        now_ms = time.ticks_ms()
        return self.debouncer.update(self.read_switch_pressed(), now_ms)

    def apply_remote_state(self):
        data = self.led_char.read()
        if data:
            self.set_led(ble_contract.decode_led_state(data))

    def notify_state(self, connection):
        self.led_char.notify(connection, ble_contract.encode_led_state(self.led_is_on))


async def run():
    app = SmartSwitchApp()

    while True:
        connection = await aioble.advertise(
            50000,
            name=DEVICE_NAME,
            services=[_LED_SERVICE_UUID],
        )

        print("Connected")

        try:
            while connection.is_connected():
                if app.led_char.updated():
                    app.apply_remote_state()
                    app.notify_state(connection)

                if app.poll_switch():
                    app.toggle_led()
                    app.notify_state(connection)

                await asyncio.sleep_ms(10)
        except Exception as exc:
            print("Error:", exc)

        print("Disconnected")


if __name__ == "__main__":
    if asyncio is None:
        raise RuntimeError("This firmware must run on MicroPython for ESP32.")
    asyncio.run(run())
