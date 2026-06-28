# Changelog

## [0.5.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.2...qwen3-tts-openvino-v0.5.3) (2026-06-28)


### Bug Fixes

* **ci:** use curl instead of gh in GHCR cleanup (gh not installed on runner) ([794df6c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/794df6cd390b5577a34a1b07ec6f0a03c0e9c5e3))

## [0.5.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.1...qwen3-tts-openvino-v0.5.2) (2026-06-28)


### Bug Fixes

* **ci:** tag-aware GHCR cleanup preserves protected image versions ([95ca024](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/95ca024267415ed1688758b9cdce664f9bbfb207))

## [0.5.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.0...qwen3-tts-openvino-v0.5.1) (2026-06-28)


### Bug Fixes

* **export:** respect NNCF INT8 constraints (no group_size/ratio overrides) ([0d7ce4f](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0d7ce4f90b67eb58a063827f87fa14c813806731))

## [0.5.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.4...qwen3-tts-openvino-v0.5.0) (2026-06-28)


### Features

* **runtime:** wire INT8 tuning, parity gates, and TTS_BACKEND selection ([2ecf8e3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2ecf8e3ddc3d28aff99de9aa7a8679c75b253eb8))

## [0.4.4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.3...qwen3-tts-openvino-v0.4.4) (2026-06-28)


### Bug Fixes

* **export:** patch DynamicLayer.lazy_initialization to fix OV aten::cat rank error ([aebce00](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/aebce0047693a92202a5c6b9bcf312db73736ee0))

## [0.4.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.2...qwen3-tts-openvino-v0.4.3) (2026-06-28)


### Bug Fixes

* **ci:** add no-cache dispatch input to recover from broken GHCR build cache ([e68eb16](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e68eb1679a566c4a7a2d5eca706103484d77bb6f))

## [0.4.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.4.1...qwen3-tts-openvino-v0.4.2) (2026-06-28)


### Bug Fixes

* **ci:** broaden ignore-versions to protect all runtime/exporter/buildcache tags ([5340067](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5340067f52f012a87a8498499c593c7ab634526f))
* **export:** use rank-4 empty tensor in DynamicLayer to fix OV aten::cat rejection ([5340067](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5340067f52f012a87a8498499c593c7ab634526f))

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
