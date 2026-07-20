from __future__ import annotations

import asyncio

import flet as ft
from bleak import BleakClient, BleakScanner

# --------------------------------------------------------------------
# BLE contract (must match the ESP32 firmware in esp32.py)
# --------------------------------------------------------------------

SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab"
LED_CHAR_UUID = "12345678-1234-1234-1234-1234567890ac"


def encode_led_state(state: bool) -> bytes:
    return b"\x01" if state else b"\x00"


def decode_led_state(data: bytes) -> bool:
    return bool(data and data[0])


async def discover_device_address(timeout: float = 5.0) -> str | None:
    """Ask the OS BLE stack for any device advertising our service UUID.

    No device name, address, or manual selection is involved: the only
    shared knowledge between the firmware and this client is the service
    UUID, exactly like an OS-paired peripheral (e.g. Logitech G Hub).
    """

    devices = await BleakScanner.discover(
        timeout=timeout,
        service_uuids=[SERVICE_UUID],
    )
    if not devices:
        return None
    return devices[0].address


async def main(page: ft.Page) -> None:
    page.title = "ESP32 BLE Controller"
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 460
    page.window.height = 280
    page.window.resizable = False

    status_text = ft.Text("Initializing...", size=16, text_align=ft.TextAlign.CENTER)
    toggle_button = ft.FilledButton(
        "Toggle LED",
        icon=ft.Icons.LIGHTBULB_OUTLINE,
        disabled=True,
    )
    reconnect_button = ft.FilledTonalButton(
        "Reconnect",
        icon=ft.Icons.SEARCH,
    )

    client: BleakClient | None = None
    led_is_on = False

    def set_status(text: str):
        status_text.value = text
        page.update()

    def sync_button():
        toggle_button.icon = (
            ft.Icons.LIGHTBULB if led_is_on else ft.Icons.LIGHTBULB_OUTLINE
        )
        toggle_button.disabled = client is None or not client.is_connected
        page.update()

    def notification_handler(
        _characteristic,
        data: bytearray,
    ):
        nonlocal led_is_on
        led_is_on = decode_led_state(bytes(data))
        sync_button()

    def disconnected_handler(_client):
        nonlocal client
        client = None
        sync_button()
        set_status("Disconnected - reconnecting...")

    async def ensure_connected():
        nonlocal client

        while True:
            if client is not None and client.is_connected:
                await asyncio.sleep(1)
                continue

            set_status("Searching for device...")
            address = await discover_device_address()

            if address is None:
                set_status("No device found. Retrying...")
                await asyncio.sleep(3)
                continue

            try:
                set_status(f"Connecting to {address}...")
                client = BleakClient(
                    address,
                    disconnected_callback=disconnected_handler,
                )
                await client.connect()

                await client.start_notify(LED_CHAR_UUID, notification_handler)

                initial = await client.read_gatt_char(LED_CHAR_UUID)
                led_is_on = decode_led_state(bytes(initial))

                sync_button()
                set_status(f"Connected: {address}")
            except Exception as exc:
                client = None
                sync_button()
                set_status(f"Connection failed: {exc}. Retrying...")
                await asyncio.sleep(3)

    async def reconnect(_event):
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def toggle_led(_event):
        nonlocal led_is_on

        if client is None or not client.is_connected:
            return

        led_is_on = not led_is_on

        await client.write_gatt_char(
            LED_CHAR_UUID,
            encode_led_state(led_is_on),
            response=True,
        )

        sync_button()

    toggle_button.on_click = toggle_led
    reconnect_button.on_click = reconnect

    page.add(
        ft.Column(
            [
                status_text,
                toggle_button,
                reconnect_button,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )
    )

    asyncio.create_task(ensure_connected())


def launch_app() -> None:
    ft.run(main)


if __name__ == "__main__":
    launch_app()
