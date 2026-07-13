# ESP32-C6 Smart Switch

Files:

- `main.py`: desktop flasher. It flashes `ESP32_GENERIC_C6-20260406-v1.28.0.bin`, then uploads `esp32.py`, `ble_contract.py`, and `esp32/manifest.py` plus any files under `esp32/`.
- `controller.py`: desktop BLE controller. It connects with `bleak`, reads the switch state, and toggles it.
- `esp32.py`: MicroPython firmware for the board.
- `ble_contract.py`: shared BLE UUIDs and LED state encoding.
- `requirements.txt`: host-side Python dependencies.

Flashing:

1. Plug in the ESP32-C6.
2. Open `main.py`.
3. Press `Flash firmware`. The app erases the board flash, writes `ESP32_GENERIC_C6-20260406-v1.28.0.bin`, then uses `mpremote mip install aioble`.

Venue setup:

- Flash one board at a time.
- If several boards are present, unplug the others before flashing.
- Keep each board on a unique USB serial path when possible.
- Use a unique `DEVICE_ID` in `esp32.py` when multiple boards share a venue.
- On Linux, expect `/dev/ttyUSB*` or `/dev/ttyACM*`.
- On macOS, expect `/dev/cu.usbmodem*`.
- On Windows, expect `COM*`.

Notes:

- The controller app uses the same BLE contract as the firmware.
- `main.py` and `controller.py` both launch with `ft.run(target=main)`.
