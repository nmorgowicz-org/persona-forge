import unittest
from types import SimpleNamespace
from unittest import mock

from export_openvino import (
    _export_provenance,
    _resolve_vocoder_decoder,
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

    def test_validates_export_provenance(self):
        commit = "a" * 40
        digest = f"sha256:{'b' * 64}"

        self.assertEqual(
            _export_provenance(
                {"SOURCE_COMMIT": commit, "EXPORTER_IMAGE_DIGEST": digest}
            ),
            (commit, digest),
        )

    def test_rejects_missing_export_provenance(self):
        with self.assertRaisesRegex(SystemExit, "SOURCE_COMMIT"):
            _export_provenance({})


if __name__ == "__main__":
    unittest.main()
