"""Verified local artifact resolution for the Pocket-TTS backend.

Downloads pinned Hugging Face artifacts (model weights, tokenizer, built-in voice
embeddings) into a persistent, content-addressed artifact directory and verifies
size + SHA-256 before anything is loaded. The design contract (plan
``docs/plans/20260713-pocket_tts_ungated_onnx.md``, section 8):

- No remote code is ever executed; only pinned, hash-verified files are loaded.
- Gated repositories are only requested when a token is available; an
  unauthenticated probe of a gated URL is never made.
- Integrity failures never load; they continue only to separately pinned sources.
- Tokens, URLs, and headers are never included in log lines or error messages.

Pure standard library (urllib) so the module has no third-party dependency and
runs in the model-free test lane.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Protocol, Sequence, Tuple

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# ---------------------------------------------------------------------------
# Pinned artifact identities (verified 2026-08-22, plan section 4.3)
# ---------------------------------------------------------------------------

POCKET_TTS_PACKAGE_VERSION = "2.1.0"

KYUTAI_CLONING_REPO = "kyutai/pocket-tts"
KYUTAI_CLONING_REVISION = "39592ff23c9ef80098bb74895d104c26275fe2c9"
LUNAHHR_UNGATED_REPO = "lunahr/pocket-tts-ungated"
LUNAHHR_UNGATED_REVISION = "d03cd73415a8d46d8eb115c7b524aebb0a729f4a"
KYUTAI_WITHOUT_CLONING_REPO = "kyutai/pocket-tts-without-voice-cloning"
KYUTAI_WITHOUT_CLONING_REVISION = "d29db7978e464fb90cb3359ee0c69a273b9142cc"
VOICE_EMBEDDINGS_REVISION = "e041936c75475d350b405bc870bcf7c22da4e9e6"

MODEL_SIZE_BYTES = 219_029_196
MODEL_CLONING_SHA256 = "473f47d99560bd50eb8b4509d3cacfe7f316ab20bdca86505403a2e6a936a6e9"
MODEL_NONCLONING_SHA256 = "be9c6b4876d3f30740a8225dfcaa2e43dc4aeb753c15272735bee16bbb4abb0a"
TOKENIZER_SIZE_BYTES = 59_339
TOKENIZER_SHA256 = "d461765ae179566678c93091c5fa6f2984c31bbe990bf1aa62d92c64d91bc3f6"

# Built-in voice embeddings: name -> (size bytes, sha256), pinned at
# kyutai/pocket-tts-without-voice-cloning@VOICE_EMBEDDINGS_REVISION.
# This list must stay in sync with persona_forge.app.POCKET_BUILTIN_VOICES
# (the predefined-name subset, i.e. the 26 entries without the hf:// wav voices).
VOICE_EMBEDDING_PINS: Mapping[str, Tuple[int, str]] = {
    "alba": (6_194_424, "69c32db63ca56843d994f81f343f62e0bf2d73f7e4c9bc73e44bb1110b1d8845"),
    "anna": (7_816_440, "5ea82f78db006c9fd34e32ddd5aae82674b5b32646097977436458d00af80dfa"),
    "azelma": (7_963_896, "9f3e69f29075f991fd47774566865ef0e0e637cb5a35992c9919761b5b84b1de"),
    "bill_boerst": (6_735_096, "75610127d44e0b05b442154f80f89f993df235aecc6cad7070f11000d006c188"),
    "caro_davy": (5_260_536, "a5961b63a2e7a5cfd7edc383aa9042fb70fd14a9dee6310cdc633881a7f2449a"),
    "charles": (6_194_424, "299edc20182eeccfbf94e308626f259da4fbf339daa8d5905218f2b1774639b8"),
    "cosette": (6_194_424, "c4fdc15f5a3a20c44dd0064a37e87d15d25562936e8dbad7e07b9832015a545d"),
    "eponine": (6_931_704, "bda3b76a384ff355fe0350736387765946304ae8ca16e59f60ea3296a1c99cc6"),
    "estelle": (8_258_808, "ccebef7f51762c7fc08870f5ecf268e8713551ae2c9f7984ddaec0c1e1c77153"),
    "eve": (6_538_488, "ea9c2faf862a6c9d2cb61910fdf02842ae56940382cc8c1000fdb1b43269692b"),
    "fantine": (6_538_488, "51a8a4355d7f912d4959e4b1918314fda85ad47eba0a33a1d78a4a505d3465f5"),
    "george": (6_243_576, "0c1c6c57c55a98d81254b33728150c7776f40647fe95258d1a6c1a02780b5d02"),
    "giovanni": (4_621_552, "a5ee718157ec1c6fd9c1e66a7733c7e6337d474a74a7da756455d27717885c59"),
    "jane": (7_374_072, "37386227ca8ec5bf1b8e516c13d132ce5ff5437a304fe90129a1c62f41d9a008"),
    "javert": (6_194_424, "0ae88e03ca4e76a0e16cbf321a807428febda9d9e9bc0358c02e7f9c9e2c263b"),
    "jean": (6_194_424, "90be4b8f50bb4d2dbe27e3fb4e31417cf6a57928931f0a60426a1748821a3d12"),
    "juergen": (6_243_576, "e74d67b38339fc01118e3bbe2c90d6d40e601b161dbf7be906421956ba80a532"),
    "lola": (5_948_664, "34972e86b07b17272a8061460054a08119399cace9454979052b9e2d96664e8c"),
    "marius": (6_194_424, "04f84efcb77a0547ba582c058db496f7ff4920891d49d37b9950d128422582a8"),
    "mary": (6_194_424, "a8f2adf260cab966fe0a113d6b549d6efdeaa79de544ae0ff34b5b6a41445a59"),
    "michael": (7_275_768, "8937f724ac4719b9aa51ea0ba1f18f9de0af7a663ad6263558266c1a53c9722d"),
    "paul": (6_980_856, "ed7a019168f94dfe77009f1b0de59387abc6fbb0db954d38ce722ecb77da61aa"),
    "peter_yearsley": (3_736_816, "dd977a6e15591e347c9a23fa7cc09e35a65b462917f5eeb162baff6dc9e3f685"),
    "rafael": (6_194_424, "ac19f099f6cd839875a629c3e2e91e0dfc2c197acf2875db168d0ae244fb58bd"),
    "stuart_bell": (5_260_536, "5a49da7ca5df05d02587ec4a0981c0d318e045f68e24423c4203ce474d9b33dc"),
    "vera": (6_735_096, "4bf50ddd957b5d218b264fdcf18efbbc7384d12da3eca98ca19b9e8dd6976acc"),
}


# ---------------------------------------------------------------------------
# Catalog types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactSource:
    """One place an artifact can be downloaded from, in source-preference order."""

    name: str
    repo_id: str
    revision: str
    gated: bool = False


@dataclass(frozen=True)
class Artifact:
    """A pinned, hash-verified file with one or more download sources."""

    key: str
    filename: str
    role: str
    repo_path: str
    expected_sha256: str
    expected_size: int
    sources: Tuple[ArtifactSource, ...]


@dataclass(frozen=True)
class SourceAttempt:
    """Outcome of trying one source. ``error_kind`` never includes credentials
    or URLs: auth_required | auth_unavailable | http_error | network_error |
    integrity_mismatch | size_exceeded."""

    source_name: str
    error_kind: str


@dataclass(frozen=True)
class ResolutionResult:
    artifact_key: str
    path: Path
    source_name: str
    repo_id: Optional[str]
    revision: Optional[str]
    sha256: str
    size: int
    from_cache: bool


class PocketArtifactError(Exception):
    """All allowed sources failed for an artifact. ``attempts`` carries one
    SourceAttempt per tried (or intentionally skipped) source."""

    def __init__(self, artifact_key: str, attempts: Sequence[SourceAttempt]) -> None:
        self.artifact_key = artifact_key
        self.attempts = list(attempts)
        summary = ", ".join(f"{a.source_name}:{a.error_kind}" for a in self.attempts) or "no sources allowed"
        super().__init__(f"could not resolve artifact {artifact_key!r} ({summary})")

    def kinds(self) -> list[str]:
        return [a.error_kind for a in self.attempts]


class _SourceFailure(Exception):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(kind)


def build_default_catalog() -> Dict[str, Artifact]:
    """The pinned artifact catalog for the Pocket-TTS English backend."""
    model_repo_path = "languages/english/model.safetensors"
    artifacts: Dict[str, Artifact] = {
        "model_cloning_english": Artifact(
            key="model_cloning_english",
            filename="model.safetensors",
            role="voice_cloning_model",
            repo_path=model_repo_path,
            expected_sha256=MODEL_CLONING_SHA256,
            expected_size=MODEL_SIZE_BYTES,
            sources=(
                ArtifactSource("lunahr", LUNAHHR_UNGATED_REPO, LUNAHHR_UNGATED_REVISION),
                ArtifactSource("kyutai", KYUTAI_CLONING_REPO, KYUTAI_CLONING_REVISION, gated=True),
            ),
        ),
        "model_noncloning_english": Artifact(
            key="model_noncloning_english",
            filename="model.safetensors",
            role="built_in_only_model",
            repo_path=model_repo_path,
            expected_sha256=MODEL_NONCLONING_SHA256,
            expected_size=MODEL_SIZE_BYTES,
            sources=(
                ArtifactSource(
                    "kyutai_without_cloning",
                    KYUTAI_WITHOUT_CLONING_REPO,
                    KYUTAI_WITHOUT_CLONING_REVISION,
                ),
            ),
        ),
        "tokenizer_english": Artifact(
            key="tokenizer_english",
            filename="tokenizer.model",
            role="sentencepiece_tokenizer",
            repo_path="languages/english/tokenizer.model",
            expected_sha256=TOKENIZER_SHA256,
            expected_size=TOKENIZER_SIZE_BYTES,
            sources=(
                ArtifactSource(
                    "kyutai_without_cloning",
                    KYUTAI_WITHOUT_CLONING_REPO,
                    KYUTAI_WITHOUT_CLONING_REVISION,
                ),
            ),
        ),
    }
    for name, (size, sha256) in VOICE_EMBEDDING_PINS.items():
        key = f"voice_embed_english_{name}"
        artifacts[key] = Artifact(
            key=key,
            filename=f"{name}.safetensors",
            role="built_in_voice_embedding",
            repo_path=f"languages/english/embeddings/{name}.safetensors",
            expected_sha256=sha256,
            expected_size=size,
            sources=(
                ArtifactSource(
                    "kyutai_without_cloning",
                    KYUTAI_WITHOUT_CLONING_REPO,
                    VOICE_EMBEDDINGS_REVISION,
                ),
            ),
        )
    return artifacts


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class StreamingResponse(Protocol):
    """Open, context-managed HTTP response (urllib's ``http.client.HTTPResponse``
    or an equivalent test double)."""

    status: int
    headers: Mapping[str, str]

    def read(self, n: int = -1) -> bytes: ...

    def __enter__(self) -> "StreamingResponse": ...

    def __exit__(self, *exc_info: object) -> None: ...


# ``fetch`` receives a urllib.request.Request and returns a StreamingResponse.
# Injectable for tests.
FetchFn = Callable[["urllib.request.Request"], StreamingResponse]

_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_CHUNK_SIZE = 1 << 20


class PocketArtifactResolver:
    """Resolves catalog artifacts to verified local files under ``artifact_dir``.

    Final files are content-addressed (``<key>__<sha16>.<ext>``) and installed
    atomically; a concurrent second process/thread re-verifies the cache instead
    of re-downloading.
    """

    def __init__(
        self,
        artifact_dir: str | Path,
        *,
        token: Optional[str] = None,
        fetch: Optional[FetchFn] = None,
        catalog: Optional[Mapping[str, Artifact]] = None,
        base_url: str = "https://huggingface.co",
        timeout: float = 120.0,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._token = token
        self._fetch: FetchFn = fetch or self._default_fetch
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self.catalog: Dict[str, Artifact] = dict(catalog) if catalog is not None else build_default_catalog()
        self._locks_dir = self.artifact_dir / ".locks"
        self._locks_dir.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────────────────

    def resolve(self, key: str, allowed_sources: Optional[Sequence[str]] = None) -> ResolutionResult:
        """Return a verified local path for ``key``.

        ``allowed_sources`` filters which catalog sources may be used; ``None``
        means all of them, an empty sequence means "cache only, no network".
        """
        artifact = self.catalog.get(key)
        if artifact is None:
            raise KeyError(f"unknown artifact key {key!r}")

        final_path = self._final_path(artifact)
        with self._lockfile(key):
            if self._verify_cache(final_path, artifact):
                primary = artifact.sources[0]
                return ResolutionResult(
                    artifact_key=key,
                    path=final_path,
                    source_name="cache",
                    repo_id=primary.repo_id,
                    revision=primary.revision,
                    sha256=artifact.expected_sha256,
                    size=artifact.expected_size,
                    from_cache=True,
                )

            attempts: list[SourceAttempt] = []
            for source in artifact.sources:
                if allowed_sources is not None and source.name not in allowed_sources:
                    continue
                if source.gated and not self._token:
                    attempts.append(SourceAttempt(source.name, "auth_required"))
                    continue
                try:
                    self._download(artifact, source, final_path)
                except _SourceFailure as exc:
                    attempts.append(SourceAttempt(source.name, exc.kind))
                    continue
                return ResolutionResult(
                    artifact_key=key,
                    path=final_path,
                    source_name=source.name,
                    repo_id=source.repo_id,
                    revision=source.revision,
                    sha256=artifact.expected_sha256,
                    size=artifact.expected_size,
                    from_cache=False,
                )

        raise PocketArtifactError(key, attempts)

    # ── internals ─────────────────────────────────────────────────────────────

    def _default_fetch(self, request: "urllib.request.Request") -> StreamingResponse:
        return urllib.request.urlopen(request, timeout=self._timeout)  # type: ignore[return-value]

    def _final_path(self, artifact: Artifact) -> Path:
        suffix = Path(artifact.filename).suffix or ".bin"
        return self.artifact_dir / f"{artifact.key}__{artifact.expected_sha256[:16]}{suffix}"

    @contextlib.contextmanager
    def _lockfile(self, key: str):
        safe = _SAFE_KEY_RE.sub("_", key).strip("._") or "artifact"
        lock_path = self._locks_dir / f"{safe}.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            if sys.platform == "win32":
                # msvcrt.locking requires the locked region to already exist in the
                # file; flock has no such requirement on POSIX.
                if os.fstat(fd).st_size < 1:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _verify_cache(self, final_path: Path, artifact: Artifact) -> bool:
        """Re-verify a cached file; a corrupt entry is quarantined by deletion."""
        if not final_path.is_file():
            return False
        valid = self._hash_matches(final_path, artifact)
        if not valid:
            with contextlib.suppress(OSError):
                final_path.unlink()
        return valid

    @staticmethod
    def _hash_matches(path: Path, artifact: Artifact) -> bool:
        try:
            if path.stat().st_size != artifact.expected_size:
                return False
            digest = hashlib.sha256()
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
            return digest.hexdigest() == artifact.expected_sha256
        except OSError:
            return False

    def _download(self, artifact: Artifact, source: ArtifactSource, final_path: Path) -> None:
        from urllib.parse import quote

        url = f"{self._base_url}/{source.repo_id}/resolve/{source.revision}/{quote(artifact.repo_path, safe='/')}"
        request = urllib.request.Request(url)
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")
        try:
            response = self._fetch(request)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise _SourceFailure("auth_unavailable") from exc
            raise _SourceFailure("http_error") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise _SourceFailure("network_error") from exc

        with response:
            declared = None
            headers = getattr(response, "headers", None)
            if headers is not None:
                declared = headers.get("Content-Length") or headers.get("X-Linked-Size")
            if declared:
                with contextlib.suppress(ValueError):
                    if int(declared) != artifact.expected_size:
                        raise _SourceFailure("size_exceeded")

            digest = hashlib.sha256()
            downloaded = 0
            tmp_fd, tmp_name = tempfile.mkstemp(dir=self.artifact_dir, prefix=f".{artifact.key}.", suffix="")
            try:
                with os.fdopen(tmp_fd, "wb") as tmp:
                    while True:
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > artifact.expected_size:
                            raise _SourceFailure("size_exceeded")
                        digest.update(chunk)
                        tmp.write(chunk)
                if downloaded != artifact.expected_size:
                    raise _SourceFailure("size_exceeded")
                if digest.hexdigest() != artifact.expected_sha256:
                    raise _SourceFailure("integrity_mismatch")
                os.replace(tmp_name, final_path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
                raise
