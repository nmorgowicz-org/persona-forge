# Changelog

## [0.4.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.0...qwen3-tts-openvino-v0.4.1) (2026-06-28)


### Bug Fixes

* **export:** pre-build 4D causal mask to prevent static kv_length in decode IR ([#16](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/16)) ([10b2260](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/10b2260a6a7371ee20aca9926124d45622fb8eda))

## [0.4.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.3.1...qwen3-tts-openvino-v0.4.0) (2026-06-28)


### Features

* **export:** add Milestone 2 transformer core parity gate for main and predictor cores ([fc527f5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/fc527f5263bb553f462755bcab999fbf3300a200))
* **export:** complete Milestone 1.5 vocoder decoder export, parity gate, and benchmark ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))


### Bug Fixes

* **export:** require SOURCE_COMMIT and EXPORTER_IMAGE_DIGEST provenance env vars ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** resolve loaded vocoder decoder access path ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** supply traceable causal and sliding-window attention masks ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** trace with eager attention on nested configs ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))
* **export:** use fixed 325-frame vocoder input contract ([538f29b](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/538f29b57bc331c2a45ab8ceb9aff33408d27625))

## [0.3.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.3.0...qwen3-tts-openvino-v0.3.1) (2026-06-28)


### Bug Fixes

* **ci:** publish images only from Release Please tags ([bec5163](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/bec516367a4a31a778a6ffcb744d7c50e028f69d))
* **export:** include the OpenVINO export CLI in the exporter image ([bec5163](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/bec516367a4a31a778a6ffcb744d7c50e028f69d))

## [0.3.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.2.0...qwen3-tts-openvino-v0.3.0) (2026-06-28)


### Features

* **export:** add vocoder decoder export as Milestone 1.5 ([2bff1da](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2bff1da1ed88aeb9543b280714e4a55eeb6298eb))
* **export:** Milestone 1.5 vocoder decoder export + fix CI exporter smoke test ([#10](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/10)) ([d2b9649](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d2b964936264d8c9c2698b20d030257a67abf358))

## [0.2.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.1.0...qwen3-tts-openvino-v0.2.0) (2026-06-28)


### Features

* bootstrap configurable OpenVINO TTS service ([#1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/1)) ([8eaea24](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8eaea2491cc7a339671f020903115068eecdd121))


### Bug Fixes

* **ci:** add .release-please-manifest.json required by release-please v17 ([#2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/issues/2)) ([97c3bee](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/97c3bee81b99f284c369008a6ee2c930a39ad078))
* **ci:** remove unsupported pull-request-header and align version to 0.2.0 ([bf3578e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/bf3578ef7929477249a1c80e65d90e36c4548664))
