import unittest
from unittest.mock import patch

import controller
import main


class MainEntrypointTests(unittest.TestCase):
    def test_launch_app_uses_flet_run(self):
        with patch.object(main.ft, "run") as run_mock:
            main.launch_app()
            run_mock.assert_called_once_with(main.main)


class ControllerEntrypointTests(unittest.TestCase):
    def test_launch_app_uses_flet_run(self):
        with patch.object(controller.ft, "run") as run_mock:
            controller.launch_app()
            run_mock.assert_called_once_with(controller.main)


if __name__ == "__main__":
    unittest.main()
