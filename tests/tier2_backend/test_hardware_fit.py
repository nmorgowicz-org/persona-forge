from persona_forge import hardware_fit


def facts(**kw):
    base = {"platform": "linux", "machine": "x86_64", "cores": 8, "cuda_capability": None, "cuda_major": None}
    return {**base, **kw}


def test_kitten_needs_apple_silicon_or_nvidia():
    assert hardware_fit.fit_for("kitten2", facts(platform="darwin", machine="arm64"))["level"] == "recommended"
    assert hardware_fit.fit_for("kitten2", facts(platform="darwin", machine="x86_64"))["level"] == "unsupported"
    cpu_only = hardware_fit.fit_for("kitten2", facts())
    assert cpu_only["level"] == "unsupported" and "NVIDIA" in cpu_only["text"]
    gpu = hardware_fit.fit_for("kitten2", facts(cuda_capability=(12, 0), cuda_major=13))
    assert gpu["level"] == "recommended"


def test_cpu_engines_and_untested_os_is_unknown():
    assert hardware_fit.fit_for("kokoro", facts())["level"] == "ok"
    windows = hardware_fit.fit_for("phonon-31m", facts(platform="win32"))
    assert windows["level"] == "unknown" and "Not tested" in windows["text"]
    assert hardware_fit.fit_for("nope", facts())["level"] == "unknown"


def test_summarise_runs_splits_cold_from_warm():
    out = hardware_fit.summarise_runs([(3.0, 4.0), (1.0, 4.0), (2.0, 4.0), (0.8, 4.0)], 1.5)
    assert out["cold_seconds"] == 3.0 and out["rtf_median"] == 0.25 and out["rtf_worst"] == 0.5
    assert out["warm_runs"] == 3 and out["load_average"] == 1.5


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "b.json"
    hardware_fit.save_result("kokoro", {"rtf_median": 0.3}, p)
    hardware_fit.save_result("phonon-31m", {"rtf_median": 0.1}, p)
    assert hardware_fit.load(p)["kokoro"]["rtf_median"] == 0.3 and len(hardware_fit.load(p)) == 2
    p.write_text("[")
    assert hardware_fit.load(p) == {}
