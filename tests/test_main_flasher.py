import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from main import collect_flash_payload, select_serial_port


class SelectSerialPortTests(unittest.TestCase):
    def test_prefers_platform_appropriate_ports(self):
        ports = [
            "/dev/random",
            "/dev/ttyUSB0",
            "/dev/cu.usbmodem01",
            "COM4",
        ]

        self.assertEqual(select_serial_port(ports, "Linux"), "/dev/ttyUSB0")
        self.assertEqual(select_serial_port(ports, "Darwin"), "/dev/cu.usbmodem01")
        self.assertEqual(select_serial_port(ports, "Windows"), "COM4")


class CollectFlashPayloadTests(unittest.TestCase):
    def test_maps_repo_sources_to_board_paths(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "esp32").mkdir()
            (root / "esp32" / "lib").mkdir()
            (root / "esp32.py").write_text("print('hello')\n", encoding="utf-8")
            (root / "ble_contract.py").write_text("contract\n", encoding="utf-8")
            (root / "esp32" / "manifest.py").write_text("manifest\n", encoding="utf-8")
            (root / "esp32" / "lib" / "helper.py").write_text(
                "helper\n", encoding="utf-8"
            )

            payload = collect_flash_payload(root)

            self.assertEqual(
                [item.remote_path for item in payload],
                ["main.py", "ble_contract.py", "manifest.py", "lib/helper.py"],
            )


class FlashSequenceTests(unittest.TestCase):
    def test_flash_sequence_erases_then_writes_then_installs_packages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            firmware = root / main.FIRMWARE_IMAGE_NAME
            firmware.write_bytes(b"firmware")

            commands = []

            def fake_run(command, capture_output, text):
                commands.append(command)
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch.object(main.subprocess, "run", side_effect=fake_run):
                with patch.object(main, "upload_payload") as upload_mock:
                    upload_mock.return_value = None
                    (root / "esp32.py").write_text("print('hello')\n", encoding="utf-8")
                    main.flash_device(
                        "COM4",
                        firmware,
                        [main.FlashPayloadFile(root / "esp32.py", "main.py")],
                    )

            self.assertIn("erase-flash", commands[0])
            self.assertIn("write-flash", commands[1])
            self.assertEqual(commands[2][2], "mpremote")
            self.assertEqual(commands[2][5], "mip")
            self.assertEqual(commands[2][6], "install")
            self.assertIn("aioble", commands[2])


if __name__ == "__main__":
    unittest.main()
