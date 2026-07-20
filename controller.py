from __future__ import annotations

import uuid

import flet as ft
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

# --------------------------------------------------------------------
# BLE constants (must match the ESP32 firmware)
# --------------------------------------------------------------------

SERVICE_UUID = uuid.UUID("12345678-1234-1234-1234-1234567890ab")
LED_CHAR_UUID = uuid.UUID("12345678-1234-1234-1234-1234567890ac")


def encode_led_state(state: bool) -> bytes:
    return b"\x01" if state else b"\x00"


def decode_led_state(data: bytes) -> bool:
    return bool(data and data[0])


async def find_device():
    devices = await BleakScanner.discover(
        timeout=5.0,
        service_uuids=[str(SERVICE_UUID)],
    )

    if not devices:
        return None

    return devices[0]


def matching_ble_devices(devices, name_prefix=ble_contract.DEVICE_NAME_PREFIX):
    return [
        device
        for device in devices
        if device.name and device.name.startswith(name_prefix)
    ]


async def main(page: ft.Page) -> None:
    page.title = "ESP32 BLE Controller"
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 460
    page.window.height = 280
    page.window.resizable = False

    device_name_text = ft.Text("Not connected", size=14, italic=True, text_align=ft.TextAlign.CENTER)
    status_text = ft.Text("Idle", size=16, text_align=ft.TextAlign.CENTER)
    device_dropdown = ft.Dropdown(label="BLE Device", width=420)
    toggle_button = ft.FilledButton(
        "Toggle LED",
        icon=ft.Icons.LIGHTBULB_OUTLINE,
        disabled=True,
    )

    reconnect_button = ft.FilledTonalButton(
        "Reconnect",
        icon=ft.Icons.SEARCH,
    )
    scan_button = ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Scan BLE devices")
    reconnect_button = ft.FilledTonalButton("Reconnect", icon=ft.Icons.SEARCH)

    client: BleakClient | None = None
    led_is_on = False
    discovered_targets = {}

    def set_status(text: str):
        status_text.value = text
        page.update()

    def sync_button():
        toggle_button.icon = (
            ft.Icons.LIGHTBULB
            if led_is_on
            else ft.Icons.LIGHTBULB_OUTLINE
        )
        page.update()

    def format_device_option(device) -> ft.dropdown.Option:
        name = device.name or "Unknown"
        rssi = getattr(device, "rssi", None)
        rssi_text = f"{rssi} dBm" if rssi is not None else "n/a"
        text = f"{name} | {device.address} | RSSI: {rssi_text}"
        return ft.dropdown.Option(key=device.address, text=text)

    async def refresh_device_options() -> list:
        set_status("Scanning...")
        devices = await BleakScanner.discover(timeout=5.0)
        targets = matching_ble_devices(devices)

        discovered_targets.clear()
        for target in targets:
            discovered_targets[target.address] = target

        previous_selection = device_dropdown.value
        device_dropdown.options = [format_device_option(target) for target in targets]

        if previous_selection in discovered_targets:
            device_dropdown.value = previous_selection
        elif len(targets) == 1:
            device_dropdown.value = targets[0].address
        else:
            device_dropdown.value = None

        if targets:
            set_status(
                f"Found {len(targets)} device(s) matching {ble_contract.DEVICE_NAME_PREFIX!r}"
            )
        else:
            set_status(f"No devices found matching {ble_contract.DEVICE_NAME_PREFIX!r}")

        page.update()
        return targets

    def notification_handler(
        _characteristic: BleakGATTCharacteristic | None,
        data: bytearray,
    ):
        nonlocal led_is_on
        led_is_on = decode_led_state(bytes(data))
        sync_button()

    def disconnected(_client):
        nonlocal client
        client = None
        toggle_button.disabled = True
        device_name_text.value = "Not connected"
        set_status("Disconnected")

    async def connect():
        nonlocal client, led_is_on
        targets = await refresh_device_options()
        if not targets:
            raise RuntimeError("No SMART_SWITCH device found.")

        selected_address = device_dropdown.value
        if selected_address:
            target = discovered_targets.get(selected_address)
            if target is None:
                raise RuntimeError("Selected device is no longer available. Scan again.")
        elif len(targets) == 1:
            target = targets[0]
            device_dropdown.value = target.address
        else:
            raise RuntimeError("Multiple devices found. Select one from the dropdown.")

        display_name = target.name or target.address
        set_status(f"Connecting to {display_name}...")
        client = BleakClient(target.address, disconnected_callback=handle_disconnect)
        await client.connect()

        await client.start_notify(
            LED_CHAR_UUID,
            notification_handler,
        )

        initial = await client.read_gatt_char(LED_CHAR_UUID)
        led_is_on = decode_led_state(bytes(initial))

        toggle_button.disabled = False
        device_name_text.value = target.name or target.address

        sync_button()
        set_status(f"Connected to {target.name or target.address}")

    async def reconnect(_):
        nonlocal client

        toggle_button.disabled = True
        page.update()

        if client is not None and client.is_connected:
            await client.disconnect()

        try:
            await connect()
        except Exception as exc:
            set_status(f"Error: {exc}")

    async def scan_devices(_event=None) -> None:
        try:
            await refresh_device_options()
        except Exception as exc:
            set_status(f"Error: {exc}")

    async def toggle_led(_event) -> None:
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
    scan_button.on_click = scan_devices

    page.add(
        ft.Column(
            [
                device_name_text,
                ft.Row(
                    [device_dropdown, scan_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                status_text,
                toggle_button,
                reconnect_button,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )
    )

    try:
        await connect()
    except Exception as exc:
        set_status(f"Error: {exc}")


def launch_app():
    ft.run(main)


if __name__ == "__main__":
    launch_app()