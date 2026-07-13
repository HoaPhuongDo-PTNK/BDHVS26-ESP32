import unittest

from esp32 import PushSwitchDebouncer


class PushSwitchDebouncerTests(unittest.TestCase):
    def test_triggers_once_after_a_stable_press(self):
        debouncer = PushSwitchDebouncer(debounce_ms=50)

        self.assertFalse(debouncer.update(pressed=False, now_ms=0))
        self.assertFalse(debouncer.update(pressed=True, now_ms=10))
        self.assertFalse(debouncer.update(pressed=True, now_ms=40))
        self.assertTrue(debouncer.update(pressed=True, now_ms=60))

    def test_does_not_retrigger_until_the_switch_is_released(self):
        debouncer = PushSwitchDebouncer(debounce_ms=50)

        self.assertFalse(debouncer.update(pressed=True, now_ms=0))
        self.assertTrue(debouncer.update(pressed=True, now_ms=50))
        self.assertFalse(debouncer.update(pressed=True, now_ms=100))
        self.assertFalse(debouncer.update(pressed=False, now_ms=120))
        self.assertFalse(debouncer.update(pressed=True, now_ms=130))
        self.assertTrue(debouncer.update(pressed=True, now_ms=190))


if __name__ == "__main__":
    unittest.main()
