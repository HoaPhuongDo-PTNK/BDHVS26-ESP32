"""BLE controller for the ESP32-C6 smart switch."""

from __future__ import annotations

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
import flet as ft

import ble_contract


def select_ble_device(devices, name_prefix=ble_contract.DEVICE_NAME_PREFIX):
    for device in devices:
        if device.name and device.name.startswith(name_prefix):
            return device
    return None


async def main(page: ft.Page) -> None:
    page.title = "ESP32 BLE Controller"
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 460
    page.window.height = 240
    page.window.resizable = False

    device_name_text = ft.Text("Not connected", size=14, italic=True, text_align=ft.TextAlign.CENTER)
    status_text = ft.Text("Idle", size=16, text_align=ft.TextAlign.CENTER)
    toggle_button = ft.FilledButton(
        "Toggle LED", icon=ft.Icons.LIGHTBULB_OUTLINE, disabled=True
    )
    reconnect_button = ft.FilledTonalButton("Reconnect", icon=ft.Icons.SEARCH)

    client: BleakClient | None = None
    led_is_on = False

    def set_status(message: str) -> None:
        status_text.value = message
        page.update()

    def sync_button_state() -> None:
        toggle_button.icon = (
            ft.Icons.LIGHTBULB if led_is_on else ft.Icons.LIGHTBULB_OUTLINE
        )
        page.update()

    def notification_handler(
        _characteristic: BleakGATTCharacteristic | None, data: bytearray
    ) -> None:
        nonlocal led_is_on
        led_is_on = ble_contract.decode_led_state(bytes(data))
        sync_button_state()

    def handle_disconnect(_client: BleakClient) -> None:
        nonlocal client
        client = None
        toggle_button.disabled = True
        device_name_text.value = "Not connected"
        set_status("Disconnected")

    async def connect() -> None:
        nonlocal client, led_is_on
        set_status("Scanning...")
        devices = await BleakScanner.discover(timeout=5.0)
        target = select_ble_device(devices)
        if target is None:
            raise RuntimeError("No SMART_SWITCH device found.")

        set_status(f"Connecting to {target.name}...")
        client = BleakClient(target.address, disconnected_callback=handle_disconnect)
        await client.connect()
        await client.start_notify(ble_contract.LED_CHAR_UUID, notification_handler)
        toggle_button.disabled = False

        initial = await client.read_gatt_char(ble_contract.LED_CHAR_UUID)
        led_is_on = ble_contract.decode_led_state(bytes(initial))
        device_name_text.value = target.name
        set_status(f"Connected to {target.name}")
        sync_button_state()

    async def reconnect(_event=None) -> None:
        nonlocal client
        toggle_button.disabled = True
        page.update()
        if client is not None and client.is_connected:
            await client.disconnect()
        try:
            await connect()
        except Exception as exc:
            set_status(f"Error: {exc}")

    async def toggle_led(_event) -> None:
        nonlocal led_is_on
        if client is None or not client.is_connected:
            return
        led_is_on = not led_is_on
        await client.write_gatt_char(
            ble_contract.LED_CHAR_UUID,
            ble_contract.encode_led_state(led_is_on),
            response=True,
        )
        sync_button_state()

    toggle_button.on_click = toggle_led
    reconnect_button.on_click = reconnect

    page.add(
        ft.Column(
            [device_name_text, status_text, toggle_button, reconnect_button],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )
    )

    try:
        await connect()
    except Exception as exc:
        set_status(f"Error: {exc}")


def launch_app() -> None:
    ft.run(main)


if __name__ == "__main__":
    launch_app()
