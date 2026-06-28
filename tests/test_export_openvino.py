import unittest
from types import SimpleNamespace

from export_openvino import _resolve_vocoder_decoder


class ExportOpenVINOTests(unittest.TestCase):
    def test_resolves_decoder_from_tokenizer_model(self):
        decoder = object()
        tokenizer = SimpleNamespace(model=SimpleNamespace(decoder=decoder))

        self.assertIs(_resolve_vocoder_decoder(tokenizer), decoder)

    def test_rejects_unexpected_tokenizer_contract(self):
        with self.assertRaisesRegex(RuntimeError, "speech_tokenizer.model.decoder"):
            _resolve_vocoder_decoder(SimpleNamespace())


if __name__ == "__main__":
    unittest.main()
