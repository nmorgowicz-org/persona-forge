"""Download the selected model into the mounted Hugging Face cache."""

from __future__ import annotations

import os

from persona_forge.model_config import configure_hf_token, resolve_model_repo


def main() -> None:
    configure_hf_token()
    from huggingface_hub import snapshot_download

    model_repo = resolve_model_repo()
    revision = os.getenv("MODEL_REVISION") or None
    cache_path = snapshot_download(repo_id=model_repo, revision=revision)
    print(f"Model ready: {model_repo} at {cache_path}")


if __name__ == "__main__":
    main()
