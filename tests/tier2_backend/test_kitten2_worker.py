import io
import sys
import textwrap
import wave
from pathlib import Path

import numpy as np
import pytest

from persona_forge import kitten2_worker as kw
from persona_forge.pack_process import PackProcess, PackProcessError


class StubModel:
    sample_rate = 24000
    available_voices = ["Bruno", "Luna"]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def generate(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.full(2400, 0.25, dtype=np.float32)


def make_worker(model: StubModel | None = None) -> tuple[kw.Kitten2Worker, StubModel]:
    stub = model or StubModel()
    seen: dict = {}

    def factory(cache_dir, runtime):
        seen["runtime"] = runtime
        return stub

    worker = kw.Kitten2Worker(
        factory=factory,
        runtime_chooser=lambda: {"backend": "mlx", "device": None, "static_cache": False},
    )
    return worker, stub


def test_choose_runtime_prefers_mlx_on_apple_silicon():
    runtime = kw.choose_runtime("darwin", "arm64", cuda_available=lambda: False)
    assert runtime["backend"] == "mlx"


def test_choose_runtime_uses_static_cache_on_cuda():
    runtime = kw.choose_runtime("win32", "AMD64", cuda_available=lambda: True)
    assert runtime == {"backend": None, "device": "cuda", "static_cache": True}


def test_choose_runtime_refuses_cpu_with_actionable_message():
    with pytest.raises(kw.WorkerError, match="Apple silicon"):
        kw.choose_runtime("linux", "x86_64", cuda_available=lambda: False)


def test_ping_reports_unloaded_then_loaded():
    worker, _ = make_worker()
    assert worker.handle({"op": "ping"}) == {"ok": True, "loaded": False}
    worker.handle({"op": "load", "warmup": False})
    assert worker.handle({"op": "ping"})["loaded"] is True


def test_load_warms_up_unless_disabled():
    worker, stub = make_worker()
    response = worker.handle({"op": "load"})
    assert response["sample_rate"] == 24000
    assert stub.calls == [("Ready.", {"voice": "Bruno"})]


def test_load_without_warmup_defers_the_first_call_to_a_warmup_request():
    worker, stub = make_worker()

    loaded = worker.handle({"op": "load", "warmup": False})

    assert loaded["warmup_pending"] is True and stub.calls == []
    warmed = worker.handle({"op": "warmup"})
    assert stub.calls == [("Ready.", {"voice": "Bruno"})]
    assert warmed["mode"] == "mlx" and warmed["fast_mode_issue"] is None


def test_a_load_that_warms_up_itself_has_nothing_pending():
    worker, _ = make_worker()

    assert worker.handle({"op": "load"})["warmup_pending"] is False


def test_warmup_before_load_fails():
    worker, _ = make_worker()

    with pytest.raises(kw.WorkerError, match="not loaded"):
        worker.handle({"op": "warmup"})


def test_synthesize_before_load_fails():
    worker, _ = make_worker()
    with pytest.raises(kw.WorkerError, match="not loaded"):
        worker.handle({"op": "synthesize", "text": "hi"})


def test_synthesize_preset_returns_wav():
    worker, stub = make_worker()
    worker.handle({"op": "load", "warmup": False})
    response = worker.handle({"op": "synthesize", "text": "Hello", "preset": "Luna", "seed": 7})
    import base64

    with wave.open(io.BytesIO(base64.b64decode(response["audio_b64"]))) as handle:
        assert handle.getframerate() == 24000
        assert handle.getnframes() == 2400
    assert stub.calls[-1] == ("Hello", {"advanced": {"seed": 7}, "voice": "Luna"})


def test_unknown_preset_is_rejected():
    worker, _ = make_worker()
    worker.handle({"op": "load", "warmup": False})
    with pytest.raises(kw.WorkerError, match="unknown preset"):
        worker.handle({"op": "synthesize", "text": "Hello", "preset": "Nobody"})


def test_prepared_clone_uses_reference_and_transcript(tmp_path: Path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(b"RIFF")
    worker, stub = make_worker()
    worker.handle({"op": "load", "warmup": False})
    prepared = worker.handle(
        {
            "op": "prepare",
            "voice_id": "vd_1",
            "reference_path": str(reference),
            "reference_text": "Some words.",
        }
    )
    assert prepared["has_transcript"] is True
    worker.handle({"op": "synthesize", "text": "Hello", "voice_id": "vd_1"})
    assert stub.calls[-1][1] == {"reference": str(reference), "reference_text": "Some words."}


def test_prepare_requires_existing_reference():
    worker, _ = make_worker()
    worker.handle({"op": "load", "warmup": False})
    with pytest.raises(kw.WorkerError, match="reference_path"):
        worker.handle({"op": "prepare", "voice_id": "vd_1", "reference_path": "/nope.wav"})


@pytest.mark.parametrize("text", [None, "", "   "])
def test_prepare_refuses_missing_words_so_synthesis_cannot_start_whisper(tmp_path: Path, text):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(b"RIFF")
    worker, stub = make_worker()
    worker.handle({"op": "load", "warmup": False})
    with pytest.raises(kw.WorkerError, match="transcript"):
        worker.handle({
            "op": "prepare", "voice_id": "v", "reference_path": str(reference),
            "reference_text": text,
        })
    assert stub.calls == []


def test_unload_drops_model_and_prepared_voices(tmp_path: Path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(b"RIFF")
    worker, _ = make_worker()
    worker.handle({"op": "load", "warmup": False})
    worker.handle({
        "op": "prepare", "voice_id": "v", "reference_path": str(reference),
        "reference_text": "Some words.",
    })
    worker.handle({"op": "unload"})
    assert worker.handle({"op": "ping"})["loaded"] is False
    with pytest.raises(kw.WorkerError):
        worker.handle({"op": "synthesize", "text": "hi", "voice_id": "v"})


def test_unknown_op_is_an_error():
    worker, _ = make_worker()
    with pytest.raises(kw.WorkerError, match="unknown op"):
        worker.handle({"op": "explode"})


def test_serve_reports_errors_without_dying():
    worker, _ = make_worker()
    stdin = io.StringIO('{"op":"ping"}\nnot json\n\n{"op":"ping"}\n')
    stdout = io.StringIO()
    kw.serve(worker, stdin, stdout)
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 3
    assert '"ok":false' in lines[1]


def test_worker_drives_through_the_real_transport(tmp_path: Path):
    script = tmp_path / "stub_worker.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys
            import numpy as np
            from persona_forge import kitten2_worker as kw

            class Stub:
                sample_rate = 24000
                available_voices = ["Bruno"]
                def generate(self, text, **kwargs):
                    return np.zeros(480, dtype=np.float32)

            worker = kw.Kitten2Worker(
                factory=lambda cache, runtime: Stub(),
                runtime_chooser=lambda: {"backend": "mlx", "device": None, "static_cache": False},
            )
            real = sys.stdout
            sys.stdout = sys.stderr
            kw.serve(worker, sys.stdin, real)
            """
        )
    )
    with PackProcess([sys.executable, str(script)], request_timeout=30) as process:
        process.request({"op": "load", "warmup": False})
        audio = process.synthesize({"text": "Hello"})
        with wave.open(io.BytesIO(audio)) as handle:
            assert handle.getnframes() == 480
        with pytest.raises(PackProcessError, match="unknown preset"):
            process.synthesize({"text": "Hello", "preset": "Nobody"})


def _cuda_worker(fail_when_compiled: bool):
    built: list[bool] = []

    class Model(StubModel):
        def __init__(self, compiled: bool) -> None:
            super().__init__()
            self.compiled = compiled

        def generate(self, text, **kwargs):
            if self.compiled and fail_when_compiled:
                raise RuntimeError("Failed to find C compiler. Please specify via CC\nmore detail")
            return super().generate(text, **kwargs)

    def factory(cache_dir, runtime):
        built.append(bool(runtime["static_cache"]))
        return Model(bool(runtime["static_cache"]))

    worker = kw.Kitten2Worker(
        factory=factory,
        runtime_chooser=lambda: {"backend": None, "device": "cuda", "static_cache": True},
    )
    return worker, built


def test_cuda_runs_compiled_when_the_toolchain_works():
    worker, built = _cuda_worker(fail_when_compiled=False)

    response = worker.handle({"op": "load"})

    assert response["mode"] == "compiled"
    assert response["fast_mode_issue"] is None
    assert built == [True]


def test_cuda_falls_back_to_eager_with_the_reason_when_compiling_fails():
    worker, built = _cuda_worker(fail_when_compiled=True)

    response = worker.handle({"op": "load"})

    assert response["mode"] == "eager"
    # On Windows and Linux a missing compiler is the build-tools case, with its own guidance.
    expected = "needs_build_tools" if sys.platform == "win32" or sys.platform.startswith("linux") else "fast_mode_failed"
    assert response["fast_mode_issue"]["code"] == expected
    assert "Failed to find C compiler" in response["fast_mode_issue"]["detail"]
    assert built == [True, False]
    assert worker.handle({"op": "synthesize", "text": "hi"})["ok"] is True


def test_a_deferred_warmup_falls_back_to_eager_with_the_reason():
    worker, built = _cuda_worker(fail_when_compiled=True)

    assert worker.handle({"op": "load", "warmup": False})["mode"] == "compiled"
    response = worker.handle({"op": "warmup"})

    assert response["mode"] == "eager"
    assert "Failed to find C compiler" in response["fast_mode_issue"]["detail"]
    assert built == [True, False]


def test_fast_mode_can_be_declined():
    worker, built = _cuda_worker(fail_when_compiled=True)

    response = worker.handle({"op": "load", "fast_mode": False})

    assert response["mode"] == "eager"
    assert response["fast_mode_issue"] is None
    assert built == [False]


def test_mlx_reports_its_own_mode():
    worker, _ = make_worker()

    assert worker.handle({"op": "load", "warmup": False})["mode"] == "mlx"


def test_the_real_windows_missing_compiler_error_becomes_a_build_tools_message():
    raw = "FileNotFoundError: [WinError 2] The system cannot find the file specified"

    issue = kw.explain_compile_failure(raw, "win32")

    assert issue["code"] == "needs_build_tools"
    assert "C++ Build Tools" in issue["message"]
    assert "Re-check" in issue["action"]
    assert issue["help_url"] == kw.BUILD_TOOLS_URL
    assert issue["detail"] == raw
    assert "WinError" not in issue["message"] + issue["action"]


def test_linux_missing_compiler_gets_an_install_hint():
    issue = kw.explain_compile_failure("RuntimeError: Failed to find C compiler", "linux")

    assert issue["code"] == "needs_build_tools"
    assert "build-essential" in issue["action"]
    assert issue["help_url"] is None


def test_missing_triton_points_to_repair_not_to_build_tools():
    issue = kw.explain_compile_failure("ModuleNotFoundError: No module named 'triton'", "win32")

    assert issue["code"] == "triton_missing"
    assert "Repair" in issue["action"]


def test_unknown_compile_failures_keep_the_raw_detail():
    issue = kw.explain_compile_failure("RuntimeError: something new", "darwin")

    assert issue["code"] == "fast_mode_failed"
    assert issue["detail"] == "RuntimeError: something new"


def test_a_windows_compile_failure_reaches_the_load_response():
    class Broken(StubModel):
        def __init__(self, compiled: bool) -> None:
            super().__init__()
            self.compiled = compiled

        def generate(self, text, **kwargs):
            if self.compiled:
                # The fourth argument is what Windows adds ("[WinError 2]"); other systems ignore it.
                raise FileNotFoundError(2, "The system cannot find the file specified", None, 2)
            return super().generate(text, **kwargs)

    worker = kw.Kitten2Worker(
        factory=lambda cache, runtime: Broken(bool(runtime["static_cache"])),
        runtime_chooser=lambda: {"backend": None, "device": "cuda", "static_cache": True},
    )

    response = worker.handle({"op": "load"})

    assert response["mode"] == "eager"
    expected = "needs_build_tools" if sys.platform == "win32" else "fast_mode_failed"
    assert response["fast_mode_issue"]["code"] == expected
