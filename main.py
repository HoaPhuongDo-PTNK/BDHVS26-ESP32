"""One-click flasher for the ESP32-C6 smart-switch firmware.
    Replace the FIRMWARE_IMAGE_NAME with corresponding MCP firmware
    Correct the esp32 variant in flash_firmware_image() & erase_flash()"""

from __future__ import annotations

import base64
import platform
import re
import subprocess
import time
import sys
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import flet as ft
import serial
from serial.tools import list_ports


PROJECT_ROOT = Path(__file__).resolve().parent
ESP32_SOURCE_ROOT = PROJECT_ROOT / "esp32"
ESP32_ENTRYPOINT = PROJECT_ROOT / "esp32.py"
FIRMWARE_IMAGE_NAME = "ESP32_GENERIC_S3-20260406-v1.28.0.bin"
DEVICE_ENTRYPOINT = "main.py"
SERIAL_BAUDRATE = 460800
UPLOAD_CHUNK_SIZE = 768
BOARD_PACKAGES = ("aioble",)

WINDOWS_PORT = re.compile(r"^COM\d+$", re.IGNORECASE)
LINUX_PORTS = (
    re.compile(r"^/dev/ttyUSB\d+$"),
    re.compile(r"^/dev/ttyACM\d+$"),
)
MAC_PORTS = (
    re.compile(r"^/dev/cu\.usbmodem.*$", re.IGNORECASE),
    re.compile(r"^/dev/cu\.usbserial.*$", re.IGNORECASE),
    re.compile(r"^/dev/tty\.usbmodem.*$", re.IGNORECASE),
    re.compile(r"^/dev/tty\.usbserial.*$", re.IGNORECASE),
)


@dataclass(frozen=True)
class FlashPayloadFile:
    source_path: Path
    remote_path: str


class FlashError(RuntimeError):
    """Raised when the one-click flash flow cannot complete."""


def select_serial_port(
    port_names: Sequence[str], system_name: str | None = None
) -> str | None:
    """Return the first port that matches the current platform's serial style."""

    system = (system_name or platform.system()).lower()

    if system.startswith("win"):
        ordered_patterns: Sequence[re.Pattern[str]] = (WINDOWS_PORT, *LINUX_PORTS, *MAC_PORTS)
    elif system == "darwin":
        ordered_patterns = (*MAC_PORTS, *LINUX_PORTS, WINDOWS_PORT)
    else:
        ordered_patterns = (*LINUX_PORTS, *MAC_PORTS, WINDOWS_PORT)

    seen: set[str] = set()
    candidates = []
    for port_name in port_names:
        if port_name not in seen:
            seen.add(port_name)
            candidates.append(port_name)

    for pattern in ordered_patterns:
        for port_name in candidates:
            if pattern.match(port_name):
                return port_name
    return None


def discover_serial_ports() -> list[str]:
    """Return the serial device names visible to the host."""

    return [port.device for port in list_ports.comports()]


def discover_firmware_images(root: Path | None = None) -> list[Path]:
    """Return sorted list of firmware images (.bin / .uf2) in the given root."""
    search_root = root or PROJECT_ROOT
    return sorted(list(search_root.glob("*.bin")) + list(search_root.glob("*.uf2")))


def select_firmware_image(repo_root: Path) -> Path:
    """Return the downloaded firmware image used for the board flash."""

    image = repo_root / FIRMWARE_IMAGE_NAME
    if image.is_file():
        return image

    matches = sorted(repo_root.glob("*.bin"))
    if len(matches) == 1:
        return matches[0]

    raise FlashError(f"Missing firmware image: {FIRMWARE_IMAGE_NAME}")


def collect_flash_payload(repo_root: Path) -> list[FlashPayloadFile]:
    """Collect the board sources that should be flashed onto the ESP32."""

    payload: list[FlashPayloadFile] = []

    entrypoint = repo_root / ESP32_ENTRYPOINT.name
    if entrypoint.is_file():
        payload.append(
            FlashPayloadFile(source_path=entrypoint, remote_path=DEVICE_ENTRYPOINT)
        )

    source_root = repo_root / ESP32_SOURCE_ROOT.name
    if source_root.is_dir():
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if any(part.startswith(".") for part in path.relative_to(source_root).parts):
                continue
            payload.append(
                FlashPayloadFile(
                    source_path=path,
                    remote_path=path.relative_to(source_root).as_posix(),
                )
            )

    def sort_key(item: FlashPayloadFile) -> tuple[int, str]:
        if item.remote_path == DEVICE_ENTRYPOINT:
            return (0, item.remote_path)
        if item.remote_path == "manifest.py":
            return (1, item.remote_path)
        return (2, item.remote_path)

    return sorted(payload, key=sort_key)


def _read_until(serial_port: serial.Serial, suffix: bytes, timeout_s: float = 5.0) -> bytes:
    deadline = time.monotonic() + timeout_s
    buffer = bytearray()
    while time.monotonic() < deadline:
        chunk = serial_port.read(1)
        if chunk:
            buffer.extend(chunk)
            if buffer.endswith(suffix):
                return bytes(buffer)
    raise FlashError(f"Timed out waiting for device response: {suffix!r}")


def _interrupt_running_program(serial_port: serial.Serial) -> None:
    serial_port.write(b"\r\x03\x03")
    serial_port.flush()
    time.sleep(0.2)


def _enter_raw_repl(serial_port: serial.Serial) -> None:
    _interrupt_running_program(serial_port)
    serial_port.write(b"\r\x01")
    serial_port.flush()
    _read_until(serial_port, b">")


def _make_directory_script(remote_path: str) -> str:
    parent = Path(remote_path).parent.as_posix()
    if parent in {"", "."}:
        return ""
    return (
        "try:\n"
        "    import uos as os\n"
        "except ImportError:\n"
        "    import os\n"
        f"parts = {parent!r}.split('/')\n"
        "current = ''\n"
        "for part in parts:\n"
        "    if not part:\n"
        "        continue\n"
        "    current = part if not current else current + '/' + part\n"
        "    try:\n"
        "        os.mkdir(current)\n"
        "    except OSError:\n"
        "        pass\n"
    )


def _make_write_script(remote_path: str, chunk: bytes, append: bool) -> str:
    encoded = base64.b64encode(chunk).decode("ascii")
    mode = "ab" if append else "wb"
    return (
        "import ubinascii\n"
        f"with open({remote_path!r}, {mode!r}) as _file:\n"
        f"    _file.write(ubinascii.a2b_base64({encoded!r}))\n"
    )


def _run_script(serial_port: serial.Serial, script: str) -> str:
    if not script:
        return ""
    serial_port.write(script.encode("utf-8") + b"\x04")
    serial_port.flush()
    response = _read_until(serial_port, b"\x04\x04>")
    response_text = response.decode("utf-8", errors="replace")
    if "Traceback" in response_text:
        raise FlashError(response_text.strip())
    return response_text


def _chunk_bytes(data: bytes, chunk_size: int) -> Iterable[bytes]:
    for start in range(0, len(data), chunk_size):
        yield data[start : start + chunk_size]


def flash_firmware_image(
    port_name: str,
    firmware_image: Path,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Flash the downloaded MicroPython firmware image to the ESP32-C6.

    The board must already be in BOOT/download mode (handled by the caller).
    """

    if on_progress is not None:
        on_progress(f"Flashing {firmware_image.name}...")

    command = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        "esp32s3"   ,
        "--port",
        port_name,
        "--baud",
        str(SERIAL_BAUDRATE),
        "--before",
        "no_reset",
        "--after",
        "hard-reset",
        "write-flash",
        "0x0",
        str(firmware_image),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FlashError(
            (result.stdout + result.stderr).strip() or "Firmware flash failed."
        )


def erase_flash(
    port_name: str, on_progress: Callable[[str], None] | None = None
) -> None:
    if on_progress is not None:
        on_progress("Erasing flash...")

    command = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        "esp32s3",
        "--port",
        port_name,
        "--baud",
        str(SERIAL_BAUDRATE),
        "--before",
        "no_reset",
        "--after",
        "no-reset",
        "erase-flash",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FlashError(
            (result.stdout + result.stderr).strip() or "Flash erase failed."
        )


def install_board_packages(
    port_name: str, on_progress: Callable[[str], None] | None = None
) -> None:
    if on_progress is not None:
        on_progress("Installing board packages...")

    command = [
        sys.executable,
        "-m",
        "mpremote",
        "connect",
        port_name,
        "mip",
        "install",
        *BOARD_PACKAGES,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FlashError(
            (result.stdout + result.stderr).strip() or "Package installation failed."
        )


def upload_payload(
    port_name: str,
    payload: Sequence[FlashPayloadFile],
    on_progress: Callable[[str], None] | None = None,
) -> None:
    if not payload:
        raise FlashError("No ESP32 files were found to upload.")

    with serial.Serial(
        port_name,
        baudrate=SERIAL_BAUDRATE,
        timeout=1,
        write_timeout=1,
    ) as serial_port:
        _enter_raw_repl(serial_port)

        for index, item in enumerate(payload, start=1):
            if on_progress is not None:
                on_progress(f"Uploading {item.remote_path} ({index}/{len(payload)})")
            _run_script(serial_port, _make_directory_script(item.remote_path))
            data = item.source_path.read_bytes()
            if not data:
                _run_script(serial_port, _make_write_script(item.remote_path, b"", False))
                continue

            first_chunk = True
            for chunk in _chunk_bytes(data, UPLOAD_CHUNK_SIZE):
                _run_script(
                    serial_port,
                    _make_write_script(item.remote_path, chunk, append=not first_chunk),
                )
                first_chunk = False

        if on_progress is not None:
            on_progress("Resetting board...")
        _run_script(serial_port, "import machine\nmachine.reset()\n")


VERIFY_BAUDRATE = 115200


def verify_micropython(port_name: str) -> bool:
    """Check whether the board on *port_name* is running MicroPython."""
    try:
        with serial.Serial(
            port_name, baudrate=VERIFY_BAUDRATE, timeout=3, write_timeout=3
        ) as port:
            _interrupt_running_program(port)
            time.sleep(0.5)
            port.write(b"\r")
            port.flush()
            _read_until(port, b">>> ", timeout_s=3.0)
            return True
    except (FlashError, serial.SerialException, OSError):
        return False


async def main(page: ft.Page) -> None:
    page.title = "ESP32 Flasher"
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 640
    page.window.height = 500
    page.window.resizable = False

    status_text = ft.Text("Ready", size=14, text_align=ft.TextAlign.CENTER)
    instruction_text = ft.Text(
        "Select a serial port. Flash the firmware first, or if the board is "
        "already running MicroPython, click Upload Payload directly.",
        size=13,
        text_align=ft.TextAlign.CENTER,
    )
    step_text = ft.Text("Ready", size=16, weight=ft.FontWeight.BOLD)

    def populate_port_dropdown() -> None:
        ports = discover_serial_ports()
        port_dropdown.options = [ft.dropdown.Option(p) for p in ports]
        if not port_dropdown.value and ports:
            preferred = select_serial_port(ports)
            if preferred:
                port_dropdown.value = preferred

    def populate_firmware_dropdown() -> None:
        images = discover_firmware_images()
        firmware_dropdown.options = [ft.dropdown.Option(i.name) for i in images]
        if not firmware_dropdown.value and images:
            firmware_dropdown.value = images[0].name

    port_dropdown = ft.Dropdown(label="Serial Port", width=480)
    port_refresh = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Scan serial ports",
        on_click=lambda _: (
            populate_port_dropdown(),
            page.update(),
        ),
    )

    firmware_dropdown = ft.Dropdown(label="Firmware Image", width=480)
    firmware_refresh = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Scan firmware images",
        on_click=lambda _: (
            populate_firmware_dropdown(),
            page.update(),
        ),
    )

    populate_port_dropdown()
    populate_firmware_dropdown()

    flash_button = ft.FilledButton("Flash Firmware", icon=ft.Icons.FLASH_ON)
    upload_button = ft.FilledButton(
        "Upload MicroPython Payload", icon=ft.Icons.UPLOAD_FILE
    )
    verify_button = ft.OutlinedButton("Verify", icon=ft.Icons.CHECK_CIRCLE)

    def set_status(message: str) -> None:
        status_text.value = message
        page.update()

    def set_instruction(message: str) -> None:
        instruction_text.value = message
        page.update()

    def set_step(message: str) -> None:
        step_text.value = message
        page.update()

    async def handle_verify(_event: ft.ControlEvent) -> None:
        port = port_dropdown.value
        if not port:
            set_status("Select a serial port first.")
            return
        set_status(f"Verifying MicroPython on {port}...")
        page.update()
        try:
            if await asyncio.to_thread(verify_micropython, port):
                set_status(f"MicroPython is running on {port}.")
            else:
                set_status(f"No MicroPython response from {port}.")
        except Exception as exc:
            set_status(f"Verification error: {exc}")

    async def handle_flash_firmware(_event: ft.ControlEvent) -> None:
        port = port_dropdown.value
        firmware_name = firmware_dropdown.value

        if not port:
            set_status("Select a serial port first.")
            return
        if not firmware_name:
            set_status("Select a firmware image first.")
            return

        flash_button.disabled = True
        verify_button.disabled = True
        set_step("Step 1: Flash Firmware")

        set_instruction(
            "Put the board into BOOT / download mode:\n"
            "  1. Hold the BOOT button\n"
            "  2. Press and release the RESET button\n"
            "  3. Release the BOOT button\n\n"
            "Then click Flash Firmware above."
        )
        page.update()

        try:
            firmware_image = PROJECT_ROOT / firmware_name

            erase_flash(port, on_progress=set_status)
            flash_firmware_image(port, firmware_image, on_progress=set_status)

            set_status("Firmware flashed! Board rebooting into MicroPython...")
            page.update()

            set_step("Step 2: Upload MicroPython Payload")
            set_instruction(
                "Board is now running MicroPython.\n"
                "Click Upload MicroPython Payload to install packages\n"
                "and upload the firmware files."
            )
            upload_button.disabled = False
            page.update()
        except (FlashError, serial.SerialException, OSError) as exc:
            set_status(f"Error: {exc}")
            set_instruction(
                "Flash failed. Make sure the board is in BOOT mode.\n"
                "Check the serial connection and try again."
            )
        finally:
            flash_button.disabled = False
            verify_button.disabled = False
            page.update()

    async def handle_upload_payload(_event: ft.ControlEvent) -> None:
        port = port_dropdown.value
        if not port:
            return

        upload_button.disabled = True
        flash_button.disabled = True
        set_status("Starting MicroPython upload...")
        page.update()

        try:
            payload = collect_flash_payload(PROJECT_ROOT)
            if not payload:
                raise FlashError("No firmware files were found to upload.")

            install_board_packages(port, on_progress=set_status)
            upload_payload(port, payload, on_progress=set_status)

            set_status("Verifying MicroPython...")
            page.update()
            await asyncio.sleep(0.3)
            if await asyncio.to_thread(verify_micropython, port):
                set_status(f"Done. Verified MicroPython on {port}.")
            else:
                set_status("Upload complete but MicroPython verification failed.")

            set_instruction(
                "All done! The board is running MicroPython\n"
                "with the smart-switch firmware."
            )
            set_step("Complete")
        except (FlashError, serial.SerialException, OSError) as exc:
            set_status(f"Error: {exc}")
            set_instruction(
                "Upload failed. Verify MicroPython is running\n"
                "on the board and try again."
            )
        finally:
            upload_button.disabled = False
            flash_button.disabled = False
            page.update()

    flash_button.on_click = handle_flash_firmware
    upload_button.on_click = handle_upload_payload
    verify_button.on_click = handle_verify

    page.add(
        ft.Column(
            [
                ft.Row(
                    [port_dropdown, port_refresh],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [firmware_dropdown, firmware_refresh],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=4),
                step_text,
                instruction_text,
                ft.Row(
                    [flash_button, upload_button, verify_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                ),
                status_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )
    )


def launch_app() -> None:
    ft.run(main)


if __name__ == "__main__":
    launch_app()
