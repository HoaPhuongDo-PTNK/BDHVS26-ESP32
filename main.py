"""One-click flasher for the ESP32-C6 smart-switch firmware."""

from __future__ import annotations

import base64
import platform
import re
import subprocess
import time
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import flet as ft
import serial
from serial.tools import list_ports


PROJECT_ROOT = Path(__file__).resolve().parent
ESP32_SOURCE_ROOT = PROJECT_ROOT / "esp32"
ESP32_ENTRYPOINT = PROJECT_ROOT / "esp32.py"
SHARED_CONTRACT = PROJECT_ROOT / "ble_contract.py"
FIRMWARE_IMAGE_NAME = "ESP32_GENERIC_C6-20260406-v1.28.0.bin"
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

    shared_contract = repo_root / SHARED_CONTRACT.name
    if shared_contract.is_file():
        payload.append(
            FlashPayloadFile(
                source_path=shared_contract, remote_path=SHARED_CONTRACT.name
            )
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
        if item.remote_path == SHARED_CONTRACT.name:
            return (1, item.remote_path)
        if item.remote_path == "manifest.py":
            return (2, item.remote_path)
        return (3, item.remote_path)

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
    """Flash the downloaded MicroPython firmware image to the ESP32-C6."""

    if on_progress is not None:
        on_progress(f"Flashing {firmware_image.name}...")

    command = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        "esp32c6",
        "--port",
        port_name,
        "--baud",
        str(SERIAL_BAUDRATE),
        "--before",
        "default-reset",
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
        "esp32c6",
        "--port",
        port_name,
        "--baud",
        str(SERIAL_BAUDRATE),
        "--before",
        "default-reset",
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


def flash_device(
    port_name: str,
    firmware_image: Path,
    payload: Sequence[FlashPayloadFile],
    on_progress: Callable[[str], None] | None = None,
) -> None:
    erase_flash(port_name, on_progress=on_progress)
    flash_firmware_image(port_name, firmware_image, on_progress=on_progress)
    install_board_packages(port_name, on_progress=on_progress)
    upload_payload(port_name, payload, on_progress=on_progress)


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


async def main(page: ft.Page) -> None:
    page.title = "ESP32-C6 Flasher"
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 460
    page.window.height = 240
    page.window.resizable = False

    status_text = ft.Text("Ready", size=16, text_align=ft.TextAlign.CENTER)
    flash_button = ft.FilledButton("Flash firmware", icon=ft.Icons.FLASH_ON)

    def set_status(message: str) -> None:
        status_text.value = message
        page.update()

    async def handle_flash(_event: ft.ControlEvent) -> None:
        flash_button.disabled = True
        set_status("Scanning serial ports...")

        try:
            port_name = select_serial_port(discover_serial_ports())
            if port_name is None:
                raise FlashError(
                    "No ESP32-C6 serial port found. Plug the board in and try again."
                )

            firmware_image = select_firmware_image(PROJECT_ROOT)
            payload = collect_flash_payload(PROJECT_ROOT)
            if not payload:
                raise FlashError("No firmware files were found to flash.")

            flash_device(
                port_name,
                firmware_image,
                payload,
                on_progress=set_status,
            )
            set_status(
                f"Done. Flashed firmware and {len(payload)} files to {port_name}."
            )
        except (FlashError, serial.SerialException, OSError) as exc:
            set_status(f"Error: {exc}")
        finally:
            flash_button.disabled = False
            page.update()

    flash_button.on_click = handle_flash

    page.add(
        ft.Column(
            [
                status_text,
                flash_button,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
        )
    )


def launch_app() -> None:
    ft.run(target=main)


if __name__ == "__main__":
    launch_app()
