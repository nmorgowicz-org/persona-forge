from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

import serve


class SupervisorTests(unittest.TestCase):
    def test_rejects_negative_shutdown_timeout_before_starting_children(self) -> None:
        with patch.dict(os.environ, {"SHUTDOWN_TIMEOUT_SECONDS": "-1"}):
            with self.assertRaisesRegex(ValueError, "must be non-negative"):
                serve.main()

    def test_child_failure_stops_the_other_service(self) -> None:
        failing = serve.Service("failing", [sys.executable, "-c", "raise SystemExit(7)"])
        sleeping = serve.Service(
            "sleeping",
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )

        with (
            patch.object(serve, "SERVICES", (failing, sleeping)),
            patch.dict(os.environ, {"SHUTDOWN_TIMEOUT_SECONDS": "2"}),
        ):
            self.assertEqual(serve.main(), 7)

        self.assertIsNotNone(sleeping.process)
        self.assertIsNotNone(sleeping.process.poll())


if __name__ == "__main__":
    unittest.main()
