import unittest
from types import SimpleNamespace

from controller import select_ble_device


class ControllerHelperTests(unittest.TestCase):
    def test_prefers_the_first_matching_device_name(self):
        devices = [
            SimpleNamespace(name="OTHER_DEVICE", address="00:00:00:00:00:01"),
            SimpleNamespace(name="SMART_SWITCH_1", address="00:00:00:00:00:02"),
            SimpleNamespace(name="SMART_SWITCH_2", address="00:00:00:00:00:03"),
        ]

        device = select_ble_device(devices)

        self.assertEqual(device.address, "00:00:00:00:00:02")


if __name__ == "__main__":
    unittest.main()
