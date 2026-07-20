from machine import Pin
import bluetooth
import aioble
import uasyncio as asyncio
import utime
import micropython

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------

LED_PIN = 41
BUTTON_PIN = 42

DEBOUNCE_MS = 200

DEVICE_ID = 1
DEVICE_NAME = f"SMART_SWITCH_{DEVICE_ID}"

SERVICE_UUID = bluetooth.UUID("12345678-1234-1234-1234-1234567890ab")
LED_CHAR_UUID = bluetooth.UUID("12345678-1234-1234-1234-1234567890ac")

# --------------------------------------------------------------------

led = Pin(LED_PIN, Pin.OUT)
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

service = aioble.Service(SERVICE_UUID)

led_char = aioble.Characteristic(
    service,
    LED_CHAR_UUID,
    read=True,
    write=True,
    notify=True,
)

aioble.register_services(service)

ble = bluetooth.BLE()
ble.config(gap_name=DEVICE_NAME)

is_on = False
last_pressed_timestamp = 0


def _state_bytes():
    return b"\x01" if is_on else b"\x00"


def set_state(state):
    global is_on

    is_on = bool(state)
    led.value(is_on)

    try:
        led_char.write(_state_bytes())
    except OSError:
        pass


async def notify_state():
    await asyncio.sleep(0)
    try:
        led_char.write(_state_bytes(), send_update=True)
    except OSError:
        pass


def _toggle_from_button(_arg):
    global last_pressed_timestamp

    now = utime.ticks_ms()
    if utime.ticks_diff(now, last_pressed_timestamp) > DEBOUNCE_MS:
        last_pressed_timestamp = now
        set_state(not is_on)
        asyncio.create_task(notify_state())


def button_handler(pin):
    micropython.schedule(_toggle_from_button, None)


button.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_handler,
)


async def peripheral():
    while True:
        print("Advertising...")

        ble.config(gap_name=DEVICE_NAME)

        async with await aioble.advertise(
            250000,
            name=DEVICE_NAME,
            services=[SERVICE_UUID],
        ) as connection:

            print("Connected")

            try:
                while connection.is_connected():
                    try:
                        data = await asyncio.wait_for(led_char.written(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        set_state(data[0] != 0)
                    except Exception:
                        pass
            except Exception:
                pass

            print("Disconnected")


async def main():
    set_state(False)
    await peripheral()


asyncio.run(main())
