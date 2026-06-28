from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

import app_api


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app_api.app.test_client()

    @patch("app_api.requests.get")
    def test_health_is_ready_when_worker_is_ready(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "ok"}
        get.return_value = response

        result = self.client.get("/health")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["status"], "ok")

    @patch("app_api.requests.get", side_effect=requests.RequestException("offline"))
    def test_health_is_unavailable_when_worker_is_unreachable(self, _get: Mock) -> None:
        result = self.client.get("/health")

        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.get_json()["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
