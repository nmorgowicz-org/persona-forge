# qwen3-tts-openvino

Containerized Qwen3-TTS voice cloning with an Intel OpenVINO backend for efficient CPU
inference.

## Status

The repository currently contains the working PyTorch service baseline and the implementation
plan for the OpenVINO backend. The HTTP contract remains compatible throughout the migration.

## Images

CI publishes two private Linux AMD64 images from each source revision:

- `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>`
- `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>`

The runtime image contains no model weights, generated OpenVINO IR, reference audio, or
secrets. The exporter image adds the conversion and quantization dependencies. Model download,
conversion, validation, and hardware benchmarking run on `dockermisc1` after the images build.

## Development

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_repo.py
```

See [the OpenVINO implementation plan](docs/OPENVINO_IMPLEMENTATION.md) for architecture,
milestones, validation gates, and deployment details.
