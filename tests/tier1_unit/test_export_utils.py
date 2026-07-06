"""Test export utility helpers without loading models or OpenVINO runtime."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from export_openvino import (
    _compress,
    _export_provenance,
    _resolve_vocoder_decoder,
    _resolved_model_revision,
    _set_eager_attention,
    parse_args,
)


class TestResolveVocoderDecoder:
    def test_resolves_from_tokenizer_model(self):
        decoder = object()
        tokenizer = SimpleNamespace(model=SimpleNamespace(decoder=decoder))
        assert _resolve_vocoder_decoder(tokenizer) is decoder

    def test_rejects_unexpected_tokenizer_contract(self):
        with pytest.raises(RuntimeError, match="speech_tokenizer.model.decoder"):
            _resolve_vocoder_decoder(SimpleNamespace())


class TestCLIParse:
    def test_vocoder_only_mode(self):
        with mock.patch(
            "sys.argv",
            ["export_openvino.py", "--output-dir", "/tmp/ov", "--vocoder-only"],
        ):
            args = parse_args()
        assert args.vocoder_only is True
        assert args.skip_vocoder is False

    def test_main_only_mode(self):
        with mock.patch(
            "sys.argv",
            ["export_openvino.py", "--output-dir", "/tmp/ov", "--main-only"],
        ):
            args = parse_args()
        assert args.main_only is True
        assert args.vocoder_only is False
        assert args.skip_vocoder is False

    def test_rejects_unsupported_int8_mode(self):
        with mock.patch(
            "sys.argv",
            [
                "export_openvino.py",
                "--output-dir",
                "/tmp/ov",
                "--int8-mode",
                "mix8",
            ],
        ), pytest.raises(SystemExit):
            parse_args()

    def test_rejects_unsupported_calibration(self):
        with mock.patch(
            "sys.argv",
            [
                "export_openvino.py",
                "--output-dir",
                "/tmp/ov",
                "--compression",
                "int8",
                "--calibration",
                "/tmp/calib",
            ],
        ), pytest.raises(SystemExit):
            parse_args()


class TestSetEagerAttention:
    def test_sets_each_nested_attention_config_once(self):
        eager = SimpleNamespace(_attn_implementation="sdpa")
        untouched = SimpleNamespace()
        children = [
            SimpleNamespace(config=eager),
            SimpleNamespace(config=eager),
            SimpleNamespace(config=untouched),
        ]
        module = SimpleNamespace(modules=lambda: iter(children))

        assert _set_eager_attention(module) == 1
        assert eager._attn_implementation == "eager"
        assert not hasattr(untouched, "_attn_implementation")


class TestExportProvenance:
    def test_uses_explicit_env_values(self):
        commit = "a" * 40
        digest = f"sha256:{'b' * 64}"
        result = _export_provenance(
            {"SOURCE_COMMIT": commit, "EXPORTER_IMAGE_DIGEST": digest}
        )
        assert result == (commit, digest)

    def test_defaults_when_missing(self):
        commit, digest = _export_provenance({})
        assert digest == "unknown"
        assert isinstance(commit, str) and commit


class TestResolvedModelRevision:
    def test_resolves_immutable_model_revision_from_loaded_config(self):
        resolved = "a" * 40
        wrapped = SimpleNamespace(
            model=SimpleNamespace(config=SimpleNamespace(_commit_hash=resolved))
        )
        assert _resolved_model_revision(wrapped, "main") == resolved

    def test_falls_back_to_requested_revision(self):
        wrapped = SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace()))
        assert _resolved_model_revision(wrapped, "v1.2") == "v1.2"
        assert _resolved_model_revision(wrapped, None) == "main"


class TestCompress:
    def test_int8_asym_does_not_pass_int4_args(self):
        modes = SimpleNamespace(INT8_SYM="int8_sym", INT8_ASYM="int8_asym", INT4_ASYM="int4")
        nncf = SimpleNamespace(CompressWeightsMode=modes, compress_weights=mock.Mock())

        _compress("model", nncf, mode="int8_asym", group_size=64, ratio=0.5)

        nncf.compress_weights.assert_called_once_with("model", mode="int8_asym")

    def test_int8_sym_and_asym_modes_not_confused(self):
        modes = SimpleNamespace(INT8_SYM="symmetric", INT8_ASYM="asymmetric", INT4_ASYM="int4")
        nncf = SimpleNamespace(CompressWeightsMode=modes, compress_weights=mock.Mock())

        _compress("model", nncf, mode="int8_sym")
        _compress("model", nncf, mode="int8_asym")

        assert nncf.compress_weights.call_args_list == [
            mock.call("model", mode="symmetric"),
            mock.call("model", mode="asymmetric"),
        ]
