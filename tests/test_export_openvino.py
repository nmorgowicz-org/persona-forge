import unittest
from types import SimpleNamespace
from unittest import mock

from export_openvino import _resolve_vocoder_decoder, parse_args


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


if __name__ == "__main__":
    unittest.main()
