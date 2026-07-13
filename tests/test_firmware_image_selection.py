import tempfile
import unittest
from pathlib import Path

from main import select_firmware_image


class FirmwareImageSelectionTests(unittest.TestCase):
    def test_prefers_the_downloaded_esp32_c6_firmware(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            firmware = root / "ESP32_GENERIC_C6-20260406-v1.28.0.bin"
            firmware.write_bytes(b"firmware")

            self.assertEqual(select_firmware_image(root), firmware)


if __name__ == "__main__":
    unittest.main()
