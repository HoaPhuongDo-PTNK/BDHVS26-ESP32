import unittest

import ble_contract


class BLEContractTests(unittest.TestCase):
    def test_state_encoding_is_single_byte(self):
        self.assertEqual(ble_contract.encode_led_state(False), b"\x00")
        self.assertEqual(ble_contract.encode_led_state(True), b"\x01")

    def test_state_decoding_treats_low_bit_as_state(self):
        self.assertFalse(ble_contract.decode_led_state(b"\x00"))
        self.assertTrue(ble_contract.decode_led_state(b"\x01"))
        self.assertTrue(ble_contract.decode_led_state(b"\x03"))


if __name__ == "__main__":
    unittest.main()
