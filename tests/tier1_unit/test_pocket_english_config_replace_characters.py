"""The rendered English config must carry replace_characters and load under the pinned schema."""

import yaml

from persona_forge.pocket_english_config import render_english_config


def test_rendered_config_replaces_curly_apostrophes():
    text = render_english_config(weights_path="/tmp/m.safetensors", tokenizer_path="/tmp/t.model")
    cfg = yaml.safe_load(text)
    assert cfg["replace_characters"] == {"\u2019": "'", "\u2018": "'"}


def test_rendered_config_validates_against_installed_pocket_tts_schema():
    from pocket_tts.utils.config import Config

    text = render_english_config(weights_path="/tmp/m.safetensors", tokenizer_path="/tmp/t.model")
    cfg = Config(**yaml.safe_load(text))
    assert cfg.replace_characters["\u2019"] == "'"
