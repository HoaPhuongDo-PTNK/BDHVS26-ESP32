from machine import Pin
import bluetooth
import aioble
import uasyncio as asyncio
import utime

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

is_on = False
last_pressed_timestamp = 0


def update_state(state):
    global is_on

    is_on = bool(state)
    led.value(is_on)

    led_char.write(
        b"\x01" if is_on else b"\x00",
        send_update=True,
    )


def button_handler(pin):
    global last_pressed_timestamp

    now = utime.ticks_ms()

    if utime.ticks_diff(now, last_pressed_timestamp) > DEBOUNCE_MS:
        last_pressed_timestamp = now
        update_state(not is_on)


button.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_handler,
)


async def peripheral():
    while True:
        print("Advertising...")

        async with await aioble.advertise(
            250000,
            name=DEVICE_NAME,
            services=[SERVICE_UUID],
        ) as connection:

            print("Connected")

            try:
                while connection.is_connected():
                    data = await led_char.written()
                    update_state(data[0] != 0)

            except Exception:
                pass

            print("Disconnected")


async def main():
    update_state(False)
    await peripheral()


asyncio.run(main())