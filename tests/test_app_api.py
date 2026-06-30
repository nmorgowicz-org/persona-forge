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


class StreamingProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app_api.app.test_client()

    @patch("app_api.requests.post")
    def test_streams_worker_pcm_and_forwards_contract_headers(self, post: Mock) -> None:
        upstream = Mock()
        upstream.status_code = 200
        upstream.headers = {
            "content-type": "application/octet-stream",
            "X-Audio-Format": "f32le",
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Channels": "1",
            "X-Stream-Error-Semantics": "connection-close",
        }
        upstream.iter_content.return_value = iter((b"first", b"second"))
        post.return_value = upstream

        result = self.client.post("/generate/stream", json={"text": "hello"})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, b"firstsecond")
        self.assertEqual(result.headers["X-Audio-Format"], "f32le")
        self.assertEqual(result.headers["X-Audio-Sample-Rate"], "24000")
        post.assert_called_once_with(
            "http://127.0.0.1:8319/infer_stream",
            json={"text": "hello"},
            stream=True,
            timeout=300,
        )
        upstream.close.assert_called_once()

    def test_rejects_missing_text_before_contacting_worker(self) -> None:
        result = self.client.post("/generate/stream", json={"language": "English"})

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.get_json()["error"], "text is required")


class OpenAiSpeechTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app_api.app.test_client()

    @patch("app_api.requests.post")
    def test_maps_input_to_worker_infer_and_returns_audio(self, post: Mock) -> None:
        worker = Mock()
        worker.status_code = 200
        worker.content = b"ID3audio-bytes"
        worker.headers = {"content-type": "audio/mpeg"}
        post.return_value = worker

        result = self.client.post(
            "/v1/audio/speech",
            json={
                "model": "qwen3-tts",
                "input": "hello there",
                "voice": "alloy",
                "response_format": "mp3",
            },
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, b"ID3audio-bytes")
        self.assertEqual(result.headers["Content-Type"], "audio/mpeg")
        post.assert_called_once_with(
            "http://127.0.0.1:8319/infer",
            json={"text": "hello there", "language": "English", "response_format": "mp3"},
            timeout=300,
        )

    def test_rejects_missing_input_with_openai_error_envelope(self) -> None:
        result = self.client.post("/v1/audio/speech", json={"model": "qwen3-tts"})

        self.assertEqual(result.status_code, 400)
        body = result.get_json()
        self.assertEqual(body["error"]["message"], "'input' is required")
        self.assertEqual(body["error"]["type"], "invalid_request_error")

    @patch("app_api.requests.post", side_effect=requests.RequestException("offline"))
    def test_worker_unreachable_returns_502_api_error(self, _post: Mock) -> None:
        result = self.client.post("/v1/audio/speech", json={"input": "hi"})

        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.get_json()["error"]["type"], "api_error")


if __name__ == "__main__":
    unittest.main()
