from pathlib import Path

import pytest

from persona_forge import accelerator_manifest as am
from persona_forge import engine_packs, kitten2_pack as kp


@pytest.fixture(autouse=True)
def _fresh_job():
    kp.reset_job()
    yield
    kp.reset_job()


def cuda_target(major=13):
    return kp.Target("cuda", am.select_cuda_pin((12, 0), major))


class Recorder:
    def __init__(self, fail_on: str | None = None):
        self.commands: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, command, env=None):
        self.commands.append([str(part) for part in command])
        joined = " ".join(self.commands[-1])
        if self.fail_on and self.fail_on in joined:
            raise kp.StepFailed("boom: " + self.fail_on)
        # Pretend the venv now exists so later steps and the manifest see an interpreter.
        if "venv" in self.commands[-1] and ("venv" == self.commands[-1][1] or "-m" in self.commands[-1]):
            target = Path(self.commands[-1][2] if "venv" == self.commands[-1][1] else self.commands[-1][-1])
            python = target / ("Scripts/python.exe" if kp.sys.platform == "win32" else "bin/python")
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("")


def run_install(tmp_path, *, target, runner=None, prefetch=None, uv="/usr/bin/uv", platform="linux"):
    runner = runner or Recorder()
    calls = []
    kp.install(
        tmp_path,
        detect=lambda: target,
        runner=runner,
        prefetch=prefetch or (lambda python, directory: calls.append((python, directory))),
        uv=uv,
        platform=platform,
    )
    return runner, calls


def test_detect_apple_silicon_uses_mlx():
    assert kp.detect_target("darwin", "arm64").kind == "mlx"


def test_detect_refuses_intel_mac():
    with pytest.raises(kp.UnsupportedMachine, match="Apple silicon"):
        kp.detect_target("darwin", "x86_64")


def test_detect_refuses_a_machine_without_an_nvidia_gpu():
    with pytest.raises(kp.UnsupportedMachine, match="NVIDIA"):
        kp.detect_target("linux", "x86_64", cuda_facts=lambda: (None, None))


def test_detect_picks_the_cuda13_build_for_a_new_driver():
    target = kp.detect_target("win32", "AMD64", cuda_facts=lambda: ((12, 0), 13))
    assert target.pin is not None and target.pin.extra == "cuda13"


def test_detect_picks_cuda12_for_an_older_driver():
    target = kp.detect_target("linux", "x86_64", cuda_facts=lambda: ((8, 6), 12))
    assert target.pin is not None and target.pin.extra == "cuda12"


def test_windows_gets_triton_and_linux_does_not():
    target = cuda_target()
    assert kp.TRITON_WINDOWS in kp.package_requirements(target, "win32")
    assert kp.TRITON_WINDOWS not in kp.package_requirements(target, "linux")


def test_mac_requirements_use_the_mlx_extra_and_no_torch_index():
    target = kp.Target("mlx")
    assert kp.package_requirements(target) == [f"kittenml[mlx]=={kp.KITTENML_VERSION}"]
    assert kp.torch_requirements(target) == ([], None)


def test_manifest_is_valid_and_marked_provisioned():
    manifest = engine_packs.parse_manifest(kp.build_manifest(cuda_target(), "win32"))

    assert manifest.provisioner == "kitten2"
    assert manifest.artifacts == ()
    assert manifest.runtime == "python-cuda"
    assert any(item.startswith("torch==") for item in manifest.requirements)


def test_a_manifest_without_artifacts_needs_a_provisioner():
    payload = kp.build_manifest(kp.Target("mlx"))
    payload.pop("provisioner")
    with pytest.raises(engine_packs.PackManifestError):
        engine_packs.parse_manifest(payload)


def test_cuda_install_runs_every_step_in_order(tmp_path):
    runner, prefetched = run_install(tmp_path, target=cuda_target(), platform="win32")

    job = kp.job_status()
    assert job["state"] == "done", job
    flat = [" ".join(command) for command in runner.commands]
    assert "venv" in flat[0] and "--python 3.12" in flat[0]
    torch_step = next(item for item in flat if "torch==" in item)
    assert "--index-url https://download.pytorch.org/whl/cu130" in torch_step
    package_step = next(item for item in flat if f"kittenml=={kp.KITTENML_VERSION}" in item)
    assert "--index-url" not in package_step and kp.TRITON_WINDOWS in package_step
    assert flat[-1].endswith("-c import kittenml")
    assert len(prefetched) == 1


def test_a_finished_install_reports_verified(tmp_path):
    run_install(tmp_path, target=kp.Target("mlx"), platform="darwin")

    status = engine_packs.inspect_pack(kp.pack_dir(tmp_path))
    assert status.status == "verified"
    assert kp.job_status()["state"] == "done"


def test_a_half_provisioned_pack_is_not_installed(tmp_path):
    runner = Recorder(fail_on="import kittenml")
    run_install(tmp_path, target=kp.Target("mlx"), runner=runner, platform="darwin")

    job = kp.job_status()
    assert job["state"] == "error"
    assert "Checking the install failed" in job["error"]
    assert engine_packs.inspect_pack(kp.pack_dir(tmp_path)).status == "not-installed"


def test_verify_never_creates_a_stamp_for_an_empty_provisioned_pack(tmp_path):
    directory = kp.pack_dir(tmp_path)
    kp._write_manifest(directory, kp.Target("mlx"), "darwin")

    status = engine_packs.inspect_pack(directory, verify=True)

    assert status.status == "not-installed"
    assert not (directory / engine_packs.VERIFIED_FILENAME).exists()


def test_a_failed_step_is_reported_with_its_label(tmp_path):
    runner = Recorder(fail_on="torch==")
    run_install(tmp_path, target=cuda_target(), runner=runner)

    job = kp.job_status()
    assert job["state"] == "error"
    assert job["error"].startswith("Installing the GPU runtime (large download) failed: boom")


def test_an_unsupported_machine_fails_fast_with_its_message(tmp_path):
    def refuse():
        raise kp.UnsupportedMachine("needs an NVIDIA GPU")

    runner = Recorder()
    kp.install(tmp_path, detect=refuse, runner=runner, prefetch=lambda *_: None, uv="uv")

    assert kp.job_status()["error"] == "needs an NVIDIA GPU"
    assert runner.commands == []


def test_retrying_skips_an_existing_environment(tmp_path):
    run_install(tmp_path, target=kp.Target("mlx"), platform="darwin")
    runner, _ = run_install(tmp_path, target=kp.Target("mlx"), platform="darwin")

    assert not any("venv" in command[1:2] for command in runner.commands)


def test_without_uv_it_falls_back_to_venv_and_pip(tmp_path):
    runner, _ = run_install(tmp_path, target=kp.Target("mlx"), uv="", platform="darwin")

    flat = [" ".join(command) for command in runner.commands]
    assert "-m venv" in flat[0]
    assert any("-m pip install" in item for item in flat)


def test_only_one_install_runs_at_a_time(tmp_path):
    import threading

    gate = threading.Event()
    started = threading.Event()

    def slow_prefetch(python, directory):
        started.set()
        gate.wait(5)

    assert kp.start_install(
        tmp_path,
        detect=lambda: kp.Target("mlx"),
        runner=Recorder(),
        prefetch=slow_prefetch,
        uv="uv",
        platform="darwin",
    )
    assert started.wait(5)
    assert kp.start_install(tmp_path) is False
    gate.set()
