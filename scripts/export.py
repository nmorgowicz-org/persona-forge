#!/usr/bin/env python3
"""Export the selected MODEL_SIZE into stable runtime paths under /ov."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from qwen3_tts.presets import normalize_size


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
        "both",
        "--int8-mode",
        mode,
    ]
    if mode == "int4_asym":
        command.extend(("--int8-group-size", "32", "--int8-ratio", "1.0"))
    subprocess.run(command, check=True)
    created = [path for path in parent.iterdir() if path not in before and path.is_dir()]
    if len(created) != 1:
        raise RuntimeError(f"expected one new export directory, found: {created}")
    return created[0]


def _copy_pair(source_xml: Path, destination_xml: Path) -> None:
    destination_xml.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_xml, destination_xml)
    shutil.copy2(source_xml.with_suffix(".bin"), destination_xml.with_suffix(".bin"))


def main() -> int:
    size = normalize_size(os.environ.get("MODEL_SIZE"))
    output = OV_ROOT / size
    staging = output / ".exports"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    int8 = _run_export(staging, "int8_asym")
    int4 = _run_export(staging, "int4_asym") if size == "1.7B" else None
    ir = output / "ir"
    if ir.exists():
        shutil.rmtree(ir)
    ir.mkdir(parents=True)

    for stem in ("main_prefill", "main_decode"):
        source = int4 if int4 is not None else int8
        _copy_pair(source / f"{stem}_int8.xml", ir / f"{stem}_int8.xml")
    for stem in ("predictor_prefill", "predictor_decode"):
        _copy_pair(int8 / f"{stem}_int8.xml", ir / f"{stem}_int8.xml")
    for stem in ("main_prefill", "main_decode", "predictor_prefill", "predictor_decode"):
        _copy_pair(int8 / f"{stem}.xml", ir / f"{stem}.xml")

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
    _copy_pair(int8 / "vocoder_decoder.xml", vocoder / "vocoder_decoder.xml")
    (vocoder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    stateful = output / "main_stateful_cap1024.xml"
    subprocess.run(
        [
            sys.executable,
            str(STATEFUL),
            "--input",
            str(ir / "main_decode_int8.xml"),
            "--output",
            str(stateful),
            "--max-seq",
            "1024",
            "--state-prefix",
            "main",
            "--compile-smoke",
            "--report-json",
            str(output / "main_stateful_cap1024.transform.json"),
        ],
        check=True,
    )
    if size == "0.6B":
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
