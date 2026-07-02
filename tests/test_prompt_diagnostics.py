import json
from types import SimpleNamespace

import numpy as np

from qwen3_tts.prompt_diagnostics import (
    dump_reference_prompt,
    dump_talker_parameter_manifest,
    reference_codes,
)


def test_reference_codes_supports_prompt_list_and_dict():
    codes = np.array([[1, 2, 3]], dtype=np.int64)

    assert reference_codes([SimpleNamespace(ref_code=codes)]) is codes
    assert reference_codes({"ref_code": [codes]}) is codes


def test_dump_reference_prompt_writes_reproducible_artifacts(tmp_path):
    codes = np.array([[1, 2, 2150]], dtype=np.int64)

    manifest_path = dump_reference_prompt([SimpleNamespace(ref_code=codes)], tmp_path)

    np.testing.assert_array_equal(np.load(tmp_path / "ref_code.npy"), codes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact"] == "ref_code.npy"
    assert manifest["dtype"] == "int64"
    assert manifest["shape"] == [1, 3]
    assert len(manifest["sha256"]) == 64
    assert set(manifest["versions"]) == {"qwen-tts", "torch", "transformers"}


def test_dump_talker_parameter_manifest_selects_conditioning_parameters(tmp_path):
    import torch

    talker = torch.nn.Module()
    talker.text_projection = torch.nn.Linear(2, 2, bias=False)
    talker.transformer = torch.nn.Linear(2, 2, bias=False)

    path = dump_talker_parameter_manifest(talker, tmp_path)

    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert set(manifest) == {"text_projection.weight"}
    assert len(manifest["text_projection.weight"]["sha256"]) == 64
