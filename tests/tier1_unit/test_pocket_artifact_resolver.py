"""Test PocketArtifactResolver — verified artifact download, cache, and failure modes.

Pure stdlib + injected fetch: no network, no torch, runs in the model-free lane.
"""

from __future__ import annotations

import hashlib
import threading
import time
import urllib.error
from typing import Mapping

import pytest

from persona_forge.pocket_artifact_resolver import (
    LUNAHHR_UNGATED_REVISION,
    MODEL_CLONING_SHA256,
    MODEL_NONCLONING_SHA256,
    MODEL_SIZE_BYTES,
    TOKENIZER_SHA256,
    TOKENIZER_SIZE_BYTES,
    VOICE_EMBEDDING_PINS,
    Artifact,
    ArtifactSource,
    PocketArtifactError,
    PocketArtifactResolver,
    build_default_catalog,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PAYLOAD_A = b"alpha-bytes-0123456789"
PAYLOAD_B = b"beta-bytes-0123456789"
PAYLOAD_C = b"gamma-bytes-0123456789"


class FakeResponse:
    def __init__(self, body: bytes, headers: Mapping[str, str] | None = None) -> None:
        self._body = body
        self.status = 200
        self.headers: Mapping[str, str] = headers or {}
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            out, self._pos = self._body[self._pos :], len(self._body)
        else:
            out = self._body[self._pos : self._pos + n]
            self._pos = min(len(self._body), self._pos + n)
        return out

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class TestCatalog:
    def make_catalog(self) -> dict:
        return {
            # Single un-gated source: failure-mode tests must not mix in an
            # auth_required skip from a gated fallback.
            "model": Artifact(
                key="model",
                filename="model.safetensors",
                role="test_model",
                repo_path="languages/english/model.safetensors",
                expected_sha256=sha256(PAYLOAD_A),
                expected_size=len(PAYLOAD_A),
                sources=(ArtifactSource("alpha", "repo/alpha", "rev-a"),),
            ),
            "model2": Artifact(
                key="model2",
                filename="model2.safetensors",
                role="test_model",
                repo_path="m2.safetensors",
                expected_sha256=sha256(PAYLOAD_B),
                expected_size=len(PAYLOAD_B),
                sources=(
                    ArtifactSource("alpha", "repo/alpha", "rev-a"),
                    ArtifactSource("gamma", "repo/gamma", "rev-c"),
                ),
            ),
            "only_gated": Artifact(
                key="only_gated",
                filename="g.safetensors",
                role="test_model",
                repo_path="g.safetensors",
                expected_sha256=sha256(PAYLOAD_C),
                expected_size=len(PAYLOAD_C),
                sources=(ArtifactSource("beta", "repo/beta", "rev-b", gated=True),),
            ),
        }

    def make_fetch(self, routes: dict, downloads: list):
        """Build a fetch fn: routes maps URL substring -> bytes | Exception | status int."""

        def fetch(request) -> FakeResponse:
            url = request.full_url
            downloads.append(url)
            auth = request.get_header("Authorization")
            if auth:
                downloads.append(f"AUTH:{auth}")
            for key, value in routes.items():
                if key in url:
                    if isinstance(value, Exception):
                        raise value
                    if isinstance(value, int):
                        raise urllib.error.HTTPError(url, value, "error", None, None)  # type: ignore[arg-type]
                    return FakeResponse(value)
            raise AssertionError(f"unexpected URL {url}")

        return fetch


class TestResolution(TestCatalog):
    def test_download_and_verify(self, tmp_path):
        downloads: list = []
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch({"repo/alpha": PAYLOAD_A}, downloads), catalog=self.make_catalog()
        )
        result = resolver.resolve("model")
        assert result.from_cache is False
        assert result.source_name == "alpha"
        assert result.sha256 == sha256(PAYLOAD_A)
        assert result.path.is_file()
        assert result.path.read_bytes() == PAYLOAD_A
        assert len(downloads) == 1

    def test_cache_hit_no_network(self, tmp_path):
        downloads: list = []
        fetch = self.make_fetch({"repo/alpha": PAYLOAD_A}, downloads)
        resolver = PocketArtifactResolver(tmp_path, fetch=fetch, catalog=self.make_catalog())
        first = resolver.resolve("model")
        assert first.from_cache is False

        downloads.clear()
        second_resolver = PocketArtifactResolver(tmp_path, fetch=fetch, catalog=self.make_catalog())
        second = second_resolver.resolve("model")
        assert second.from_cache is True
        assert second.path == first.path
        assert second.source_name == "cache"
        assert downloads == []

    def test_corrupt_cache_is_redownloaded(self, tmp_path):
        downloads: list = []
        fetch = self.make_fetch({"repo/alpha": PAYLOAD_A}, downloads)
        resolver = PocketArtifactResolver(tmp_path, fetch=fetch, catalog=self.make_catalog())
        first = resolver.resolve("model")

        first.path.write_bytes(b"corrupted!")
        downloads.clear()

        result = resolver.resolve("model")
        assert result.from_cache is False
        assert len(downloads) == 1
        assert result.path.read_bytes() == PAYLOAD_A

    def test_checksum_mismatch_is_rejected(self, tmp_path):
        downloads: list = []
        wrong = PAYLOAD_A[:-1] + b"Z"  # same length, different content
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch({"repo/alpha": wrong}, downloads), catalog=self.make_catalog()
        )
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("model")
        assert excinfo.value.kinds() == ["integrity_mismatch"]
        # Nothing is installed and no temp files are left behind.
        leftovers = [p for p in tmp_path.iterdir() if p.name != ".locks"]
        assert leftovers == []

    def test_size_exceeded_on_stream(self, tmp_path):
        downloads: list = []
        too_big = PAYLOAD_A + b"EXTRA-BYTES-1234567890"
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch({"repo/alpha": too_big}, downloads), catalog=self.make_catalog()
        )
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("model")
        assert excinfo.value.kinds() == ["size_exceeded"]
        assert not list(tmp_path.glob("*.safetensors"))

    def test_declared_content_length_mismatch(self, tmp_path):
        downloads: list = []

        def fetch(request) -> FakeResponse:
            downloads.append(request.full_url)
            return FakeResponse(PAYLOAD_A, headers={"Content-Length": str(len(PAYLOAD_A) + 5)})

        resolver = PocketArtifactResolver(tmp_path, fetch=fetch, catalog=self.make_catalog())
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("model")
        assert excinfo.value.kinds() == ["size_exceeded"]

    def test_network_error_falls_back_to_next_source(self, tmp_path):
        downloads: list = []
        routes = {
            "repo/alpha": urllib.error.URLError("network down"),
            "repo/gamma": PAYLOAD_B,
        }
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch(routes, downloads), catalog=self.make_catalog()
        )
        result = resolver.resolve("model2")
        assert result.source_name == "gamma"
        assert result.from_cache is False

    def test_http_error_falls_back_to_next_source(self, tmp_path):
        downloads: list = []
        routes = {"repo/alpha": 500, "repo/gamma": PAYLOAD_B}
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch(routes, downloads), catalog=self.make_catalog()
        )
        result = resolver.resolve("model2")
        assert result.source_name == "gamma"

    def test_primary_failure_reports_all_causes_in_order(self, tmp_path):
        catalog = self.make_catalog()
        catalog["mixed"] = Artifact(
            key="mixed",
            filename="mixed.safetensors",
            role="test_model",
            repo_path="mixed.safetensors",
            expected_sha256=sha256(PAYLOAD_A),
            expected_size=len(PAYLOAD_A),
            sources=(
                ArtifactSource("alpha", "repo/alpha", "rev-a"),
                ArtifactSource("beta", "repo/beta", "rev-b", gated=True),
            ),
        )
        downloads: list = []
        routes = {"repo/alpha": b"alpha-wrong-0123456789", "repo/beta": PAYLOAD_C}
        resolver = PocketArtifactResolver(tmp_path, fetch=self.make_fetch(routes, downloads), catalog=catalog)
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("mixed")
        assert excinfo.value.kinds() == ["integrity_mismatch", "auth_required"]
        assert len(downloads) == 1 and "repo/alpha" in downloads[0]  # gated source never probed

    def test_gated_source_skipped_without_token(self, tmp_path):
        downloads: list = []
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch({"repo/beta": PAYLOAD_C}, downloads), catalog=self.make_catalog()
        )
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("only_gated")
        assert excinfo.value.kinds() == ["auth_required"]
        assert downloads == []  # gated URL was never probed

    def test_gated_source_403_with_token_is_auth_unavailable(self, tmp_path):
        downloads: list = []
        resolver = PocketArtifactResolver(
            tmp_path,
            token="hf_secret_token",
            fetch=self.make_fetch({"repo/beta": 403}, downloads),
            catalog=self.make_catalog(),
        )
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("only_gated")
        assert excinfo.value.kinds() == ["auth_unavailable"]
        assert any(d.startswith("AUTH:Bearer hf_secret_token") for d in downloads)

    def test_allowed_sources_filter(self, tmp_path):
        downloads: list = []
        resolver = PocketArtifactResolver(
            tmp_path,
            token="hf_secret_token",
            fetch=self.make_fetch({"repo/beta": PAYLOAD_C}, downloads),
            catalog=self.make_catalog(),
        )
        result = resolver.resolve("only_gated", allowed_sources=("beta",))
        assert result.source_name == "beta"

        downloads.clear()
        # Cache only (empty tuple): succeeds from cache without touching the network.
        cache_result = resolver.resolve("only_gated", allowed_sources=())
        assert cache_result.from_cache is True
        assert downloads == []

    def test_cache_only_with_empty_cache_fails(self, tmp_path):
        downloads: list = []
        resolver = PocketArtifactResolver(
            tmp_path, fetch=self.make_fetch({"repo/alpha": PAYLOAD_A}, downloads), catalog=self.make_catalog()
        )
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("model", allowed_sources=())
        assert excinfo.value.attempts == []
        assert "no sources allowed" in str(excinfo.value)
        assert downloads == []

    def test_error_message_redacts_secrets(self, tmp_path):
        downloads: list = []
        resolver = PocketArtifactResolver(
            tmp_path,
            token="hf_supersecretvalue",
            fetch=self.make_fetch({"repo/beta": 403}, downloads),
            catalog=self.make_catalog(),
        )
        with pytest.raises(PocketArtifactError) as excinfo:
            resolver.resolve("only_gated")
        message = str(excinfo.value)
        assert "hf_supersecretvalue" not in message
        assert "Authorization" not in message
        assert "Bearer" not in message


class TestConcurrency(TestCatalog):
    def test_concurrent_resolvers_download_once(self, tmp_path):
        downloads: list = []
        lock = threading.Lock()

        def fetch(request) -> FakeResponse:
            with lock:
                downloads.append(request.full_url)
            time.sleep(0.05)  # widen the race window
            return FakeResponse(PAYLOAD_A)

        resolver_a = PocketArtifactResolver(tmp_path, fetch=fetch, catalog=self.make_catalog())
        resolver_b = PocketArtifactResolver(tmp_path, fetch=fetch, catalog=self.make_catalog())
        results = {}

        def worker(name, resolver):
            results[name] = resolver.resolve("model")

        threads = [
            threading.Thread(target=worker, args=("a", resolver_a)),
            threading.Thread(target=worker, args=("b", resolver_b)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(downloads) == 1
        assert results["a"].path == results["b"].path
        assert {results["a"].from_cache, results["b"].from_cache} == {True, False}


class TestDefaultCatalog:
    def test_artifact_counts(self):
        catalog = build_default_catalog()
        # 3 core artifacts + 26 pinned built-in voices.
        assert len(catalog) == 29
        assert set(VOICE_EMBEDDING_PINS) == {
            k[len("voice_embed_english_") :] for k in catalog if k.startswith("voice_embed_english_")
        }

    def test_pinned_model_identities(self):
        catalog = build_default_catalog()
        cloning = catalog["model_cloning_english"]
        assert cloning.expected_sha256 == MODEL_CLONING_SHA256
        assert cloning.expected_size == MODEL_SIZE_BYTES
        assert [s.name for s in cloning.sources] == ["lunahr", "kyutai"]
        assert cloning.sources[1].gated is True
        assert cloning.sources[0].revision == LUNAHHR_UNGATED_REVISION

        noncloning = catalog["model_noncloning_english"]
        assert noncloning.expected_sha256 == MODEL_NONCLONING_SHA256
        assert noncloning.expected_size == MODEL_SIZE_BYTES
        assert [s.name for s in noncloning.sources] == ["kyutai_without_cloning"]
        assert all(not s.gated for s in noncloning.sources)

        tokenizer = catalog["tokenizer_english"]
        assert tokenizer.expected_sha256 == TOKENIZER_SHA256
        assert tokenizer.expected_size == TOKENIZER_SIZE_BYTES

    def test_voice_pins_are_well_formed(self):
        for name, (size, digest) in VOICE_EMBEDDING_PINS.items():
            assert size > 0
            assert len(digest) == 64
            artifact = build_default_catalog()[f"voice_embed_english_{name}"]
            assert artifact.repo_path == f"languages/english/embeddings/{name}.safetensors"
            assert artifact.expected_size == size
            assert artifact.expected_sha256 == digest
