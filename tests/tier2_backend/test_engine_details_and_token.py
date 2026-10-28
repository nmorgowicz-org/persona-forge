"""Engine card Details, bounded redacted logs, the Hugging Face token store and the first-run nudge."""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from persona_forge import (
    engine_details,
    engine_packs,
    hardware_fit,
    hf_access,
    kokoro_pack,
    pack_logs,
    pocket_lite_pack,
)
from persona_forge.kitten2_pack import StepFailed, run_command

DUMMY = "hf_DUMMYtokenForTests1234567890"
REPO_URL = "https://huggingface.co/kyutai/pocket-tts"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path / "packs"))
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(hf_access, "login_token", lambda: None)
    hf_access._forget_cache()
    pack_logs.forget("pocket-lite")
    pack_logs.forget("kokoro")
    pocket_lite_pack.reset_job()
    yield
    hf_access._forget_cache()
    pocket_lite_pack.reset_job()


# -- token store ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_the_token_file_is_owner_only():
    hf_access.save(DUMMY)

    mode = stat.S_IMODE(os.stat(hf_access.token_path()).st_mode)
    assert mode == 0o600
    assert hf_access.stored_token() == DUMMY


def test_save_replaces_and_clear_removes_the_token():
    hf_access.save("hf_first_token_1")
    hf_access.save(DUMMY)
    assert hf_access.stored_token() == DUMMY

    assert hf_access.clear() is True
    assert hf_access.stored_token() is None
    assert hf_access.clear() is False
    assert not hf_access.token_path().exists()


@pytest.mark.parametrize("bad", [None, 12, "", "   ", "has space inside", "short", "x" * 600, "tok\nen_value1"])
def test_invalid_tokens_are_rejected_without_echoing_them(bad):
    with pytest.raises(hf_access.InvalidToken) as caught:
        hf_access.save(bad)

    assert not hf_access.token_path().exists()
    if isinstance(bad, str) and bad.strip():
        assert bad.strip() not in str(caught.value)


def test_resolution_prefers_the_stored_token_then_the_environment(monkeypatch):
    assert hf_access.resolve() == (None, None)
    monkeypatch.setenv("HF_TOKEN", "hf_from_environment_1")
    assert hf_access.resolve() == ("hf_from_environment_1", "environment")

    hf_access.save(DUMMY)
    assert hf_access.resolve() == (DUMMY, "stored")

    hf_access.clear()
    assert hf_access.resolve() == ("hf_from_environment_1", "environment")


def test_status_never_contains_a_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_from_environment_1")
    hf_access.save(DUMMY)

    status = hf_access.status()

    assert status == {"set": True, "source": "stored", "can_clear": True}
    assert DUMMY not in json.dumps(status) and "hf_from_environment_1" not in json.dumps(status)


# -- token routes: never in a response -----------------------------------------------------


def test_token_routes_never_return_the_token(client):
    saved = client.put("/engines/hf-token", json={"token": DUMMY})
    status = client.get("/engines/hf-token")
    cards = client.get("/engines")
    cleared = client.delete("/engines/hf-token")

    assert saved.status_code == 200 and saved.get_json() == {"set": True, "source": "stored", "can_clear": True}
    assert status.get_json()["set"] is True
    assert status.headers["Cache-Control"] == "no-store"
    assert cleared.get_json()["set"] is False and cleared.get_json()["removed"] is True
    for response in (saved, status, cards, cleared):
        assert DUMMY.encode() not in response.data


def test_a_rejected_token_is_not_echoed_in_the_error(client):
    response = client.put("/engines/hf-token", json={"token": "bad token with spaces"})

    assert response.status_code == 400
    assert b"bad token with spaces" not in response.data
    assert not hf_access.token_path().exists()


def test_engine_cards_show_the_gate_and_whether_a_token_is_set(client):
    client.put("/engines/hf-token", json={"token": DUMMY})

    cards = {card["id"]: card for card in client.get("/engines").get_json()["engines"]}

    gate = cards["pocket-lite"]["hf_gate"]
    assert gate["repo"] == "kyutai/pocket-tts" and gate["url"] == REPO_URL
    assert gate["token"]["set"] is True
    assert "hf_gate" not in cards["kokoro"]
    assert DUMMY not in json.dumps(cards)


# -- the token reaches only the download child ---------------------------------------------


class Recorder:
    def __init__(self, fail_on=None, message="boom"):
        self.envs = []
        self.commands = []
        self.fail_on = fail_on
        self.message = message

    def __call__(self, command, env=None):
        self.commands.append(" ".join(command))
        self.envs.append(env or {})
        if self.fail_on and self.fail_on in self.commands[-1]:
            raise StepFailed(self.message)


def test_a_stored_token_goes_to_the_download_child_only(tmp_path):
    hf_access.save(DUMMY)
    runner = Recorder()

    pocket_lite_pack.install(tmp_path / "packs", runner=runner)

    assert runner.envs[0]["HF_TOKEN"] == DUMMY
    assert "HF_TOKEN" not in runner.envs[1]  # the offline check never gets it
    assert "HF_TOKEN" not in os.environ  # not leaked into this process either
    manifest = (pocket_lite_pack.pack_dir(tmp_path / "packs") / "manifest.json").read_text()
    assert DUMMY not in manifest


def test_the_environment_token_still_works_without_a_stored_one(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_from_environment_1")
    runner = Recorder()

    pocket_lite_pack.install(tmp_path / "packs", runner=runner)

    assert runner.envs[0]["HF_TOKEN"] == "hf_from_environment_1"


# -- install failure classification (section 2.4) -----------------------------------------


def _fail(tmp_path, message, token):
    pocket_lite_pack.reset_job()
    pocket_lite_pack.install(
        tmp_path / "packs", runner=Recorder(fail_on="has_voice_cloning", message=message), token=token
    )
    return pocket_lite_pack.job_status()


def test_missing_token_unaccepted_terms_rejected_token_and_network_are_told_apart(tmp_path):
    gated = "AssertionError: no cloning weights"

    missing = _fail(tmp_path, gated, "")
    unaccepted = _fail(tmp_path, "403 Client Error: Access to model kyutai/pocket-tts is restricted", DUMMY)
    rejected = _fail(tmp_path, "401 Client Error: Invalid credentials in Authorization header", DUMMY)
    network = _fail(tmp_path, "Max retries exceeded: Name or service not known", DUMMY)

    assert [j["error_code"] for j in (missing, unaccepted, rejected, network)] == [
        "needs_token",
        "terms_not_accepted",
        "token_rejected",
        "network",
    ]
    assert missing["error_link"] == REPO_URL and unaccepted["error_link"] == REPO_URL
    assert rejected["error_link"] == hf_access.HF_TOKENS_URL
    assert network["error_link"] is None
    assert "internet connection" in network["error"]
    for job in (missing, unaccepted, rejected, network):
        assert "Repair" in job["error"]
        assert DUMMY not in job["error"]


def test_the_preflight_status_tells_a_bad_token_from_unaccepted_terms(tmp_path):
    rejected = _fail(tmp_path, "PF_HF_GATE 401: Hugging Face refused access to kyutai/pocket-tts", DUMMY)
    unaccepted = _fail(tmp_path, "PF_HF_GATE 403: Hugging Face refused access to kyutai/pocket-tts", DUMMY)
    missing = _fail(tmp_path, "PF_HF_GATE 401: Hugging Face refused access to kyutai/pocket-tts", "")

    assert [j["error_code"] for j in (rejected, unaccepted, missing)] == [
        "token_rejected",
        "terms_not_accepted",
        "needs_token",
    ]


def _run_prefetch_with_stub(tmp_path, status):
    """Run the real prefetch script against a stand-in ``huggingface_hub`` that answers ``status``."""
    import subprocess

    stub = tmp_path / "stub" / "huggingface_hub"
    stub.mkdir(parents=True)
    (stub / "errors.py").write_text(
        "class GatedRepoError(Exception):\n"
        "    def __init__(self, status):\n"
        "        self.response = type('R', (), {'status_code': status})()\n"
    )
    (stub / "__init__.py").write_text(
        "from .errors import GatedRepoError\n"
        "class HfApi:\n"
        f"    def auth_check(self, repo, token=None):\n"
        f"        raise GatedRepoError({status})\n"
    )
    return subprocess.run(
        [sys.executable, "-c", pocket_lite_pack._PREFETCH_SCRIPT, str(tmp_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(tmp_path / "stub"), "HF_TOKEN": DUMMY},
    )


@pytest.mark.parametrize("status", [401, 403])
def test_the_prefetch_preflight_reports_the_status_hugging_face_answered(tmp_path, status):
    result = _run_prefetch_with_stub(tmp_path, status)

    assert result.returncode == 3
    assert f"PF_HF_GATE {status}" in result.stderr
    assert DUMMY not in result.stderr + result.stdout


def test_without_a_token_a_401_means_a_token_is_needed():
    failure = hf_access.classify(
        "401 Client Error. Cannot access gated repo", token_present=False, label="X", repo="a/b", repo_url="https://x"
    )

    assert failure is not None and failure.code == "needs_token"


def test_unrelated_failures_are_left_to_the_generic_message(tmp_path):
    job = _fail(tmp_path, "disk full while writing 14013 bytes", DUMMY)

    assert job["error_code"] is None and "disk full" in job["error"]


# -- redaction and bounding ----------------------------------------------------------------


def test_redact_removes_known_and_token_shaped_secrets(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "plainenvsecret99")
    hf_access.save("storedsecret123")
    text = (
        f"curl -H 'Authorization: Bearer {DUMMY}' url?token=abcd1234&x=1 HF_TOKEN=plainenvsecret99 "
        "stored storedsecret123 api_org_ABCDEFGHIJ extra-secret-9"
    )

    clean = pack_logs.redact(text, ["extra-secret-9"])

    for secret in (DUMMY, "abcd1234", "plainenvsecret99", "storedsecret123", "api_org_ABCDEFGHIJ", "extra-secret-9"):
        assert secret not in clean
    assert "x=1" in clean and pack_logs.REDACTED in clean


def test_a_ring_log_keeps_only_the_last_lines_and_caps_line_length():
    log = pack_logs.RingLog(max_lines=5)

    for index in range(12):
        log.append(f"line {index}")
    log.append("y" * 5000)
    snap = log.snapshot()

    assert len(snap["lines"]) == 5 and snap["dropped"] == 8
    assert snap["lines"][0] == "line 8"
    assert len(snap["lines"][-1]) <= pack_logs.MAX_LINE_CHARS + 2


def test_the_install_log_is_bounded_redacted_and_persisted_owner_only(tmp_path):
    def noisy_runner(command, env=None):
        sink = pack_logs.current_sink()
        assert sink is not None
        for index in range(pack_logs.MAX_LINES + 50):
            sink.line(f"progress {index} token {DUMMY}")
        raise StepFailed(f"no cloning weights while using {DUMMY}")

    pocket_lite_pack.install(tmp_path / "packs", runner=noisy_runner, token=DUMMY)

    directory = pocket_lite_pack.pack_dir(tmp_path / "packs")
    logged = pack_logs.read("pocket-lite", directory)["install"]
    assert len(logged["lines"]) == pack_logs.MAX_LINES
    assert logged["dropped"] > 0
    assert DUMMY not in "\n".join(logged["lines"])
    assert any(line.startswith("-- FAILED:") for line in logged["lines"])
    file_text = (directory / pack_logs.INSTALL_LOG_FILENAME).read_text()
    assert DUMMY not in file_text and file_text.count("\n") <= pack_logs.MAX_LINES + 2
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(directory / pack_logs.INSTALL_LOG_FILENAME).st_mode) == 0o600


def test_the_install_log_survives_a_restart_through_its_file(tmp_path):
    def failing(command, env=None):
        raise StepFailed("something broke")

    pocket_lite_pack.install(tmp_path / "packs", runner=failing, token="")
    pack_logs.forget("pocket-lite")  # a new server process has no in-memory log

    logged = pack_logs.read("pocket-lite", pocket_lite_pack.pack_dir(tmp_path / "packs"))["install"]

    assert logged["source"] == "file" and any("something broke" in line for line in logged["lines"])


def test_run_command_streams_output_into_the_log_and_redacts_the_failure_tail():
    script = (
        "import sys; print('out line one'); "
        f"print('Authorization: Bearer {DUMMY}', file=sys.stderr); sys.exit(3)"
    )
    with pack_logs.capture_install("kokoro", None) as sink:
        with pytest.raises(StepFailed) as caught:
            run_command([sys.executable, "-c", script])
        lines = sink.log.snapshot()["lines"]

    assert DUMMY not in str(caught.value)
    assert "out line one" in "\n".join(lines) and DUMMY not in "\n".join(lines)


def test_worker_stderr_is_redacted_and_logged(tmp_path):
    from persona_forge.pack_process import PackProcess

    worker = tmp_path / "worker.py"
    worker.write_text(
        "import sys, json\n"
        f"print('Bearer {DUMMY} leaked', file=sys.stderr, flush=True)\n"
        "for line in sys.stdin:\n"
        "    print(json.dumps({'ok': True}), flush=True)\n"
    )
    process = PackProcess([sys.executable, str(worker)], log=pack_logs.worker_sink("kokoro"))
    process.start()
    try:
        process.ping()
        import time

        for _ in range(50):
            if pack_logs.ring("kokoro", "worker").snapshot()["lines"]:
                break
            time.sleep(0.05)
        tail = process.stderr_tail
    finally:
        process.close()

    logged = pack_logs.ring("kokoro", "worker").snapshot()["lines"]
    assert logged and DUMMY not in "\n".join(logged) and DUMMY not in tail


# -- details payload -----------------------------------------------------------------------


def _make_kokoro_pack(root):
    directory = kokoro_pack.pack_dir(root)
    (directory / "models").mkdir(parents=True)
    (directory / "models" / kokoro_pack.MODEL_FILE[0]).write_bytes(b"x" * 100)
    (directory / "manifest.json").write_text(json.dumps(kokoro_pack.build_manifest()))
    site = directory / "venv" / "lib" / "python3.12" / "site-packages" / "kokoro_onnx-0.6.1.dist-info"
    site.mkdir(parents=True)
    hub = directory / "hf" / "hub" / "models--org--thing"
    (hub / "refs").mkdir(parents=True)
    (hub / "refs" / "main").write_text("abc123revision")
    (hub / "blobs").mkdir()
    (hub / "blobs" / "b1").write_bytes(b"y" * 2048)
    engine_packs._write_verification_stamp(
        directory, engine_packs.load_manifest(directory).manifest_sha256
    )
    (directory / ".install_check.json").write_text(
        json.dumps({"outcome": "ok", "rtf": 0.1, "device": "cpu", "mode": "cpu", "note": None, "error": None})
    )
    return directory


def test_details_lists_pins_installed_versions_weights_runtime_and_disk(client, tmp_path):
    _make_kokoro_pack(tmp_path / "packs")
    pack_logs.ring("kokoro", "worker").append(f"loaded model with token {DUMMY}")

    response = client.get("/engines/kokoro/details")

    assert response.status_code == 200
    details = response.get_json()["details"]
    assert details["engine"]["pack_version"] == "1" and details["engine"]["manifest_sha256"]
    assert details["packages"] == [
        {"name": "kokoro-onnx", "pinned": "0.6.1", "installed": "0.6.1", "where": "pack environment"}
    ]
    names = {weight["name"]: weight for weight in details["weights"]}
    assert names[kokoro_pack.MODEL_FILE[0]]["sha256"] == kokoro_pack.MODEL_FILE[2]
    assert names[kokoro_pack.MODEL_FILE[0]]["present"] is True
    assert names[kokoro_pack.VOICES_FILE[0]]["present"] is False
    assert names["org/thing"]["revision"] == "abc123revision" and names["org/thing"]["size_bytes"] == 2048
    assert details["runtime"]["variant"] == "onnxruntime-cpu" and details["runtime"]["device"] == "cpu"
    assert details["install_check"]["outcome"] == "ok"
    assert details["idle_unload"]["manifest_seconds"] == kokoro_pack.IDLE_UNLOAD_AFTER_S
    assert details["idle_unload"]["seconds"] is not None
    assert details["disk_bytes"] >= 100 + 2048
    assert details["installed"] is True
    assert details["logs"]["worker"]["lines"] and DUMMY not in response.get_data(as_text=True)


def test_details_for_an_engine_that_failed_to_install_carry_the_log(client, tmp_path):
    def failing(command, env=None):
        raise StepFailed("no cloning weights")

    pocket_lite_pack.install(tmp_path / "packs", runner=failing, token="")

    details = client.get("/engines/pocket-lite/details").get_json()["details"]

    assert details["installed"] is False
    assert details["install_job"]["error_code"] == "needs_token"
    assert any("FAILED" in line for line in details["logs"]["install"]["lines"])
    assert details["hf_gate"]["token"]["set"] is False
    logs = client.get("/engines/pocket-lite/logs").get_json()["logs"]
    assert logs["install"]["lines"] == details["logs"]["install"]["lines"]


def test_details_are_for_pack_engines_only(client):
    assert client.get("/engines/pocket-tts/details").status_code == 404
    assert client.get("/engines/nope/details").status_code == 404
    assert client.get("/engines/pocket-tts/logs").status_code == 404


def test_details_without_an_install_report_nothing_installed(client):
    details = client.get("/engines/kokoro/details").get_json()["details"]

    assert details["installed"] is False and details["disk_bytes"] is None
    assert details["packages"] == [] and details["weights"] == []


def test_installed_version_reads_the_pack_environment_not_the_app(tmp_path):
    site = tmp_path / "venv" / "lib" / "python3.13" / "site-packages" / "My_Pkg-2.5.dist-info"
    site.mkdir(parents=True)

    assert engine_details.installed_version(tmp_path, "my-pkg") == "2.5"
    assert engine_details.installed_version(tmp_path, "other") is None


# -- first-run nudge -----------------------------------------------------------------------

GPU = {"platform": "linux", "machine": "x86_64", "cores": 16, "cuda_capability": (12, 0), "cuda_major": 13}
MAC = {"platform": "darwin", "machine": "arm64", "cores": 10, "cuda_capability": None, "cuda_major": None}
CPU = {"platform": "linux", "machine": "x86_64", "cores": 8, "cuda_capability": None, "cuda_major": None}
ODD = {"platform": "freebsd", "machine": "x86_64", "cores": 4, "cuda_capability": None, "cuda_major": None}


def test_the_nudge_claims_only_what_hardware_fit_reports():
    gpu = hardware_fit.first_run_nudge(GPU, pack_installed=False)
    mac = hardware_fit.first_run_nudge(MAC, pack_installed=False)
    cpu = hardware_fit.first_run_nudge(CPU, pack_installed=False)
    assert gpu is not None and mac is not None and cpu is not None

    assert gpu["kind"] == "gpu" and "NVIDIA GPU" in gpu["text"] and gpu["engines"] == ["kitten2"]
    assert mac["kind"] == "apple" and "Apple silicon" in mac["text"]
    assert cpu["kind"] == "cpu" and "Phonon" in cpu["text"] and "without one" in cpu["text"]
    for nudge in (gpu, mac, cpu):
        assert "higher-quality" not in nudge["text"] and "fast" not in nudge["text"].lower()
        assert nudge["basis"]  # the hardware_fit sentence it rests on


def test_no_nudge_once_a_pack_is_installed_or_when_fit_is_unknown():
    assert hardware_fit.first_run_nudge(GPU, pack_installed=True) is None
    assert hardware_fit.first_run_nudge(ODD, pack_installed=False) is None


def test_engines_route_returns_the_nudge_only_with_no_pack_installed(client, tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_fit, "machine_facts", lambda: CPU)

    empty = client.get("/engines").get_json()
    assert empty["nudge"]["kind"] == "cpu"

    _make_kokoro_pack(tmp_path / "packs")
    assert client.get("/engines").get_json()["nudge"] is None


def test_the_nudge_dismissal_is_an_allowed_persisted_preference(client):
    saved = client.post("/ui/preferences", json={"values": {"engines.nudgeDismissed": True}})

    assert saved.status_code == 200
    assert client.get("/ui/preferences").get_json()["values"]["engines.nudgeDismissed"] is True
    bad = client.post("/ui/preferences", json={"values": {"engines.nudgeDismissed": "yes"}})
    assert bad.status_code == 400
