#!/usr/bin/env python3
"""Export IR into stable runtime paths under /ov.

Supported EXPORT_TARGET values:
- base (default): exports the Base checkpoint.
- voice_design: exports the VoiceDesign checkpoint.
- both: exports both Base and VoiceDesign in one run (intended for compose export service).

For details on IR layout and VoiceDesign wiring, see docs/dev/architecture/voice_design.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from persona_forge.model_config import resolve_voice_design_model_repo
from persona_forge.presets import FRAME_RATE_HZ, get_preset, get_voice_design_preset, normalize_size


OV_ROOT = Path(os.environ.get("OV_OUTPUT_ROOT", "/ov"))
EXPORTER = Path("/app/src/export/export_openvino.py")
STATEFUL = Path("/app/scripts/transform_stateful_ir.py")


def _run_export(parent: Path, mode: str) -> Path:
    before = set(parent.iterdir()) if parent.exists() else set()
    command = [
        sys.executable,
        str(EXPORTER),
        "--output-dir",
        str(parent),
        "--compression",
        "int8" if mode == "int4_asym" else "both",
        "--int8-mode",
        mode,
    ]
    if mode == "int4_asym":
        command.extend(
            ("--main-only", "--int8-group-size", "32", "--int8-ratio", "1.0")
        )
    subprocess.run(command, check=True)
    created = [path for path in parent.iterdir() if path not in before and path.is_dir()]
    if len(created) != 1:
        raise RuntimeError(f"expected one new export directory, found: {created}")
    return created[0]


def _move_pair(source_xml: Path, destination_xml: Path) -> None:
    """Move a staged XML/BIN pair into place without duplicating multi-GB weights."""
    destination_xml.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source_xml, destination_xml)
    shutil.move(source_xml.with_suffix(".bin"), destination_xml.with_suffix(".bin"))


def _export_for_preset(preset: dict[str, object]) -> None:
    """Run the full export pipeline for a given preset (Base or VoiceDesign)."""
    capacity = int(preset["stateful_capacity"])
    # Derived from the preset's own IR paths (not size directly) so Base and VoiceDesign
    # never need duplicated directory-naming logic here.
    output = Path(preset["ov_model_dir"]).parent
    staging = output / ".exports"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    int8 = _run_export(staging, "int8_asym")
    int4 = _run_export(staging, "int4_asym") if preset["main_compression"] == "int4" else None
    ir = output / "ir"
    if ir.exists():
        shutil.rmtree(ir)
    ir.mkdir(parents=True)

    for stem in ("main_prefill", "main_decode"):
        source = int4 if int4 is not None else int8
        _move_pair(source / f"{stem}_int8.xml", ir / f"{stem}_int8.xml")
    for stem in ("predictor_prefill", "predictor_decode"):
        _move_pair(int8 / f"{stem}_int8.xml", ir / f"{stem}_int8.xml")
    for stem in ("main_prefill", "main_decode", "predictor_prefill", "predictor_decode"):
        _move_pair(int8 / f"{stem}.xml", ir / f"{stem}.xml")

    metadata = json.loads((int8 / "metadata.json").read_text(encoding="utf-8"))
    metadata["per_core_compression"] = {
        "main": "int4_asym_g32" if int4 is not None else "int8_asym",
        "predictor": "int8_asym",
    }
    (ir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    vocoder = output / "vocoder"
    if vocoder.exists():
        shutil.rmtree(vocoder)
    vocoder.mkdir(parents=True)
    _move_pair(int8 / "vocoder_decoder.xml", vocoder / "vocoder_decoder.xml")
    (vocoder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    stateful = output / f"main_stateful_cap{capacity}.xml"
    subprocess.run(
        [
            sys.executable,
            str(STATEFUL),
            "--input",
            str(ir / "main_decode_int8.xml"),
            "--output",
            str(stateful),
            "--max-seq",
            str(capacity),
            "--state-prefix",
            "main",
            "--compile-smoke",
            "--report-json",
            str(output / f"main_stateful_cap{capacity}.transform.json"),
        ],
        check=True,
    )
    print(
        f"stateful main capacity: {capacity} frames "
        f"(~{preset['max_speech_seconds']:.0f}s at {FRAME_RATE_HZ} Hz) -> {stateful}"
    )
    if preset["predictor_stateful_model"] is not None:
        predictor_stateful = output / "predictor_stateful_cap32.xml"
        subprocess.run(
            [
                sys.executable,
                str(STATEFUL),
                "--input",
                str(ir / "predictor_decode_int8.xml"),
                "--output",
                str(predictor_stateful),
                "--max-seq",
                "32",
                "--state-prefix",
                "predictor",
                "--compile-smoke",
                "--report-json",
                str(output / "predictor_stateful_cap32.transform.json"),
            ],
            check=True,
        )
    shutil.rmtree(staging)
    print(f"export complete: {output}")


def main() -> int:
    target = (os.environ.get("EXPORT_TARGET") or "base").strip().lower()
    if target not in ("base", "voice_design", "both"):
        raise RuntimeError(
            f"Unsupported EXPORT_TARGET={target!r}; choose base, voice_design, or both"
        )

    # Base export (if requested)
    if target in ("base", "both"):
        print("=== Exporting Base checkpoint ===")
        size = normalize_size(os.environ.get("MODEL_SIZE"))
        max_speech_seconds_env = os.environ.get("TTS_MAX_SPEECH_SECONDS")
        base_preset = get_preset(
            size,
            float(max_speech_seconds_env) if max_speech_seconds_env else None,
        )
        _export_for_preset(base_preset)

    # VoiceDesign export (if requested)
    if target in ("voice_design", "both"):
        print("=== Exporting VoiceDesign checkpoint ===")
        max_speech_seconds_env = os.environ.get("VOICE_DESIGN_MAX_SPEECH_SECONDS")
        vd_preset = get_voice_design_preset(
            os.environ.get("VOICE_DESIGN_MODEL_SIZE"),
            float(max_speech_seconds_env) if max_speech_seconds_env else None,
            os.environ.get("VOICE_DESIGN_MAIN_COMPRESSION") or None,
        )
        # export_openvino.py resolves its checkpoint via persona_forge.model_config.resolve_model_repo(),
        # which honors an explicit MODEL_REPO override — set it so the subprocess below (which
        # inherits this environment) loads the VoiceDesign checkpoint instead of a Base one.
        os.environ["MODEL_REPO"] = resolve_voice_design_model_repo()
        _export_for_preset(vd_preset)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
