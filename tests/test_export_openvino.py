import unittest
from types import SimpleNamespace
from unittest import mock

from export_openvino import (
    _compress,
    _export_provenance,
    _resolve_vocoder_decoder,
    _resolved_model_revision,
    _set_eager_attention,
    parse_args,
)


class ExportOpenVINOTests(unittest.TestCase):
    def test_resolves_decoder_from_tokenizer_model(self):
        decoder = object()
        tokenizer = SimpleNamespace(model=SimpleNamespace(decoder=decoder))

        self.assertIs(_resolve_vocoder_decoder(tokenizer), decoder)

    def test_rejects_unexpected_tokenizer_contract(self):
        with self.assertRaisesRegex(RuntimeError, "speech_tokenizer.model.decoder"):
            _resolve_vocoder_decoder(SimpleNamespace())

    def test_vocoder_only_cli_mode(self):
        with mock.patch(
            "sys.argv",
            ["export_openvino.py", "--output-dir", "/tmp/ov", "--vocoder-only"],
        ):
            args = parse_args()

        self.assertTrue(args.vocoder_only)
        self.assertFalse(args.skip_vocoder)

    def test_rejects_unsupported_mix8_mode(self):
        with mock.patch(
            "sys.argv",
            [
                "export_openvino.py",
                "--output-dir",
                "/tmp/ov",
                "--int8-mode",
                "mix8",
            ],
        ), self.assertRaises(SystemExit):
            parse_args()

    def test_rejects_unsupported_int8_calibration_before_export(self):
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
        ), self.assertRaises(SystemExit):
            parse_args()

    def test_sets_each_nested_attention_config_once(self):
        eager = SimpleNamespace(_attn_implementation="sdpa")
        untouched = SimpleNamespace()
        children = [
            SimpleNamespace(config=eager),
            SimpleNamespace(config=eager),
            SimpleNamespace(config=untouched),
        ]
        module = SimpleNamespace(modules=lambda: iter(children))

        self.assertEqual(_set_eager_attention(module), 1)
        self.assertEqual(eager._attn_implementation, "eager")
        self.assertFalse(hasattr(untouched, "_attn_implementation"))

    def test_export_provenance_uses_explicit_env_values(self):
        commit = "a" * 40
        digest = f"sha256:{'b' * 64}"

        self.assertEqual(
            _export_provenance(
                {"SOURCE_COMMIT": commit, "EXPORTER_IMAGE_DIGEST": digest}
            ),
            (commit, digest),
        )

    def test_export_provenance_defaults_when_missing(self):
        # Missing provenance must NOT abort an export. Digest falls back to "unknown";
        # the commit is best-effort (auto-detected git SHA or "unknown").
        commit, digest = _export_provenance({})

        self.assertEqual(digest, "unknown")
        self.assertIsInstance(commit, str)
        self.assertTrue(commit)

    def test_resolves_immutable_model_revision_from_loaded_config(self):
        resolved = "a" * 40
        wrapped = SimpleNamespace(
            model=SimpleNamespace(config=SimpleNamespace(_commit_hash=resolved))
        )

        self.assertEqual(_resolved_model_revision(wrapped, "main"), resolved)

    def test_falls_back_to_requested_revision_when_no_commit_hash(self):
        wrapped = SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace()))

        self.assertEqual(_resolved_model_revision(wrapped, "v1.2"), "v1.2")
        self.assertEqual(_resolved_model_revision(wrapped, None), "main")

    def test_int8_compression_does_not_pass_int4_tuning_arguments(self):
        modes = SimpleNamespace(INT8_SYM="int8_sym", INT8_ASYM="int8_asym", INT4_ASYM="int4")
        nncf = SimpleNamespace(CompressWeightsMode=modes, compress_weights=mock.Mock())

        _compress("model", nncf, mode="int8_asym", group_size=64, ratio=0.5)

        nncf.compress_weights.assert_called_once_with("model", mode="int8_asym")

    def test_int8_sym_and_asym_modes_are_not_confused(self):
        modes = SimpleNamespace(INT8_SYM="symmetric", INT8_ASYM="asymmetric", INT4_ASYM="int4")
        nncf = SimpleNamespace(CompressWeightsMode=modes, compress_weights=mock.Mock())

        _compress("model", nncf, mode="int8_sym")
        _compress("model", nncf, mode="int8_asym")

        self.assertEqual(
            nncf.compress_weights.call_args_list,
            [
                mock.call("model", mode="symmetric"),
                mock.call("model", mode="asymmetric"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
