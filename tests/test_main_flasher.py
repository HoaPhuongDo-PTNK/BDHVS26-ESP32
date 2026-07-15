import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from main import (
    collect_flash_payload,
    discover_firmware_images,
    select_serial_port,
    verify_micropython,
)


class VerifyMicroPythonTests(unittest.TestCase):
    def _make_mock_serial(self):
        mock = MagicMock()
        mock.__enter__.return_value = mock
        return mock

    def test_returns_true_when_repl_prompt_is_detected(self):
        mock_serial = self._make_mock_serial()
        mock_serial.read.side_effect = [b">", b">", b">", b" "]

        with patch.object(main.serial, "Serial", return_value=mock_serial):
            result = verify_micropython("/dev/ttyUSB0")

        self.assertTrue(result)
        mock_serial.write.assert_any_call(b"\r\x03\x03")
        mock_serial.write.assert_any_call(b"\r")

    def test_returns_false_when_serial_raises(self):
        with patch.object(main.serial, "Serial", side_effect=OSError("No device")):
            result = verify_micropython("/dev/ttyUSB0")

        self.assertFalse(result)

    def test_returns_false_on_timeout(self):
        mock_serial = self._make_mock_serial()
        mock_serial.read.return_value = b""

        with patch.object(main.serial, "Serial", return_value=mock_serial):
            result = verify_micropython("/dev/ttyUSB0")

        self.assertFalse(result)


class DiscoverFirmwareImagesTests(unittest.TestCase):
    def test_returns_sorted_bin_and_uf2_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "z_firmware.bin").write_bytes(b"z")
            (root / "a_firmware.uf2").write_bytes(b"a")
            (root / "not_a_firmware.txt").write_text("text")

            images = discover_firmware_images(root)

            self.assertEqual(
                [i.name for i in images],
                ["a_firmware.uf2", "z_firmware.bin"],
            )

    def test_returns_empty_list_when_no_firmware_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.assertEqual(discover_firmware_images(root), [])


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

            (root / "esp32.py").write_text("print('hello')\n", encoding="utf-8")
            payload = [main.FlashPayloadFile(root / "esp32.py", "main.py")]

            with patch.object(main.subprocess, "run", side_effect=fake_run):
                with patch.object(main, "upload_payload") as upload_mock:
                    main.erase_flash("COM4")
                    main.flash_firmware_image("COM4", firmware)
                    main.install_board_packages("COM4")
                    main.upload_payload("COM4", payload)

            self.assertIn("erase-flash", commands[0])
            self.assertIn("write-flash", commands[1])
            self.assertEqual(commands[2][2], "mpremote")
            self.assertEqual(commands[2][5], "mip")
            self.assertEqual(commands[2][6], "install")
            self.assertIn("aioble", commands[2])


if __name__ == "__main__":
    unittest.main()
