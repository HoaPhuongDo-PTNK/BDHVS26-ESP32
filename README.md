# ESP32-C6 Smart Switch

Files:

- `main.py`: desktop flasher. It flashes `ESP32_GENERIC_S3-20260406-v1.28.0.bin`, then uploads `esp32.py` and `esp32/manifest.py` plus any files under `esp32/`.
- `controller.py`: desktop BLE controller. It uses `bleak` to discover the device by its service UUID, reads the switch state, and toggles it.
- `esp32.py`: MicroPython firmware for the board. It uses `aioble` to advertise the service and expose the LED characteristic.
- `requirements.txt`: host-side Python dependencies.

The BLE contract (service and characteristic UUIDs) lives directly in `esp32.py` and `controller.py` so each side is self-contained.

Flashing:

1. Plug in the ESP32-C6.
2. Open `main.py`.
3. Press `Flash firmware`. The app erases the board flash, writes `ESP32_GENERIC_S3-20260406-v1.28.0.bin`, then uses `mpremote mip install aioble`.

Uploading without flashing:

- If the board is already running MicroPython, select its serial port and press
  `Upload MicroPython Payload` directly. This installs `aioble` and copies
  `esp32.py` to the board as `main.py` (plus `esp32/manifest.py` and any files
  under `esp32/`) without erasing or re-flashing the firmware.

Venue setup:

- Flash one board at a time.
- If several boards are present, unplug the others before flashing.
- Keep each board on a unique USB serial path when possible.
- Use a unique `DEVICE_ID` in `esp32.py` when multiple boards share a venue.
- On Linux, expect `/dev/ttyUSB*` or `/dev/ttyACM*`.
- On macOS, expect `/dev/cu.usbmodem*`.
- On Windows, expect `COM*`.

Notes:

- The controller app discovers the device purely by its service UUID; no device name, address, or manual selection is needed. The OS BLE stack handles the connection (like Logitech G Hub).
- `main.py` and `controller.py` both launch with `ft.run(target=main)`.
