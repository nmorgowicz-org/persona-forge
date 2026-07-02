# Changelog

## [0.21.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.20.0...qwen3-tts-openvino-v0.21.0) (2026-07-02)


### Features

* **backend:** seeded VoiceDesign, per-voice cloning cache, runtime control panel ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **frontend:** complete VoiceDesign web UI ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **tests:** add Playwright E2E suite, screenshot harness, and dedicated UI CI workflow ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))


### Bug Fixes

* **deps:** rename requirements manifests for Dependabot graph compatibility ([9db3930](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/9db39308fd012e52e41cbf4cae73632d71184c0d))
* **tests:** repair CI test failures from stale fakes and pytest-only test module ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))
* **tests:** silence werkzeug per-request access log in the E2E fake server ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))


### Documentation

* **agent-reference:** document delete/seed/runtime-config APIs, reorganize agent reference docs ([1d56671](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/1d56671f39aa3cb4135af59bfc417576408e17c4))

## [0.20.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.19.0...qwen3-tts-openvino-v0.20.0) (2026-07-02)


### Features

* add TTS_MAX_SPEECH_SECONDS for configurable stateful capacity ceiling ([47b2706](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/47b2706321d9fff7705b71f361aab90268c03508))

## [0.19.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.18.0...qwen3-tts-openvino-v0.19.0) (2026-07-02)


### Features

* **runtime:** add EOS conditioning fix, step-level diagnostics, and free-run handoff ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** add TTS_MAX_NEW_TOKENS cap, TTS_NON_STREAMING override, and prompt diagnostics ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))


### Bug Fixes

* drop cache_position from create_causal_mask for transformers 5.x ([b8901c9](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b8901c9646a9554e86df793911d5efdf0b4c0ccc))
* fix Dockerfile indentation for input_embeds patch ([3bf171f](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/3bf171f1508f84c50ecf0c53b3aa70e180f65f0b))
* patch codec_head.forward instead of replacing codec_head module ([9cc9863](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/9cc98630a9ce5dc52502ef9585cdfed30117ffcb))
* patch qwen-tts input_embeds -&gt; inputs_embeds for transformers 5.x ([8159e7d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8159e7d85821793ef9ea475670a4b79cc1e33dd0))
* **runtime:** fix transformers 5.x weight over-initialization randomizing talker embeddings and heads ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))
* **runtime:** restore Mimi causal mask for correct reference codec tokens under transformers 5.x ([2092df3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/2092df3d9a3b87adb26cb503cb7b106cb9435a6d))


### Miscellaneous Chores

* add codec_head logits diagnostic for decode-step debugging ([6df7709](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/6df7709c12e00e27ccb2e639fcd4cfbcd0be9c08))

## [0.18.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.4...qwen3-tts-openvino-v0.18.0) (2026-07-01)


### Features

* **runtime:** add decode-step heartbeat in OVStatefulCore ([5ea00db](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5ea00dbde2592d27a6d3682b9b776a1810855c0d))


### Bug Fixes

* **runtime:** force correct decode position_ids in OV cores ([5ea00db](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5ea00dbde2592d27a6d3682b9b776a1810855c0d))

## [0.17.4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.3...qwen3-tts-openvino-v0.17.4) (2026-07-01)


### Bug Fixes

* **runtime:** suppress transformers 5.x deprecation warnings ([aea333a](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/aea333a7842c5af3884442a08050cdfce155d668))

## [0.17.3](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.2...qwen3-tts-openvino-v0.17.3) (2026-07-01)


### Bug Fixes

* **runtime:** glibc malloc tuning for LOW_RAM_MODE; drop LD_PRELOAD ([85f2014](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/85f201445d28c8faceae9f7595d532fa99c85736))

## [0.17.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.1...qwen3-tts-openvino-v0.17.2) (2026-07-01)


### Bug Fixes

* **deps:** restore 'default' RoPE type removed in transformers 5.x ([d5f3ad5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d5f3ad5ff036d6bf6ef9e5898fea7930b8db5335))
* **runtime:** drop jemalloc from LOW_RAM_MODE; keep idle unload ([d5f3ad5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d5f3ad5ff036d6bf6ef9e5898fea7930b8db5335))

## [0.17.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.17.0...qwen3-tts-openvino-v0.17.1) (2026-07-01)


### Bug Fixes

* **deps:** restore 'default' RoPE type removed in transformers 5.x ([10c8a0c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/10c8a0c33f63a8394c7f74c69192e5c590a90445))

## [0.17.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.16.1...qwen3-tts-openvino-v0.17.0) (2026-07-01)


### Features

* **runtime:** log generation start, elapsed time, audio duration, and RTF ([8a65186](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8a6518691249cfccce0891ef70125400234d783b))


### Bug Fixes

* **deps:** patch qwen-tts pad_token_id access for transformers 5.x ([8a65186](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8a6518691249cfccce0891ef70125400234d783b))
* **deps:** patch qwen-tts pad_token_id access for transformers 5.x ([aa33890](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/aa33890aef859c7324bb821d42823576901fb9b0))

## [0.16.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.16.0...qwen3-tts-openvino-v0.16.1) (2026-07-01)


### Bug Fixes

* **deps:** add sox Python package to runtime deps ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** patch qwen-tts check_model_inputs for transformers 5.x API ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** remove check_model_inputs decorator instead of replacing it ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** remove qwen-tts from runtime.txt to resolve pip conflict ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))
* **deps:** upgrade transformers to 5.12.1 to fix CVE-2026-1839 ([8262bbd](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/8262bbdd220cf784301dbd461fe05596e80d3814))

## [0.16.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.15.1...qwen3-tts-openvino-v0.16.0) (2026-07-01)


### Features

* **infra:** LOW_RAM_MODE with jemalloc allocator and entrypoint ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** expose OV_INFERENCE_THREADS; wire torch.set_num_threads to it ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** idle model unload with configurable cooldown and RAM telemetry ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **runtime:** OpenVINO compiled kernel cache via OV_CACHE_DIR ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Bug Fixes

* **compose:** default MODEL_SIZE to 1.7B to match recommendation ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Documentation

* **compose:** explain :local tag vs production QWEN3_TTS_IMAGE usage ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* **config:** group and expand .env.example with all user-facing vars ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* document idle unload, OV cache, and LOW_RAM_MODE ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* simplify README/HOW_TO_RUN; add RAM-tiered setup guidance ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))
* update AGENTS.md for single-image v0.15.1 ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))


### Miscellaneous Chores

* remove stale bench_results/ JSON files ([33fb4ea](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/33fb4ea661d5ace201c07443829cfdfcdf797750))

## [0.15.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.15.0...qwen3-tts-openvino-v0.15.1) (2026-07-01)


### Bug Fixes

* **ci:** publish one complete container image ([b7defd7](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b7defd7be16c6817713c162b88181fb3b77611b2))

## [0.15.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.14.0...qwen3-tts-openvino-v0.15.0) (2026-07-01)


### Features

* **runtime:** release PyTorch codec after startup to cut ~0.4 GiB RSS ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Bug Fixes

* **runtime:** unbreak pytorch rollback, harden formats, doc memory root cause ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Code Refactoring

* **config:** add MODEL_SIZE presets + apply_preset_env (validated) ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **service:** simplify runtime and local export ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **wip:** scaffold src/qwen3_tts package + write simplify-v2 HANDOFF ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))


### Documentation

* record codec-release A/B, reject INT8 vocoder, slim HANDOFF ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* refresh README + HOW_TO_RUN with 1.7B recommendation, footprint, codec flag ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** correct memory root cause with measured data; rollback confirmed ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record generation-peak A/B (0.6B vs 1.7B nearly identical) ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record listening preference ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))
* **results:** record simplify-v2 validation ([d56456c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d56456c9888119eb07f6484a66aaccb31cef163c))

## [0.14.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.13.0...qwen3-tts-openvino-v0.14.0) (2026-06-30)


### Features

* **api:** add OpenAI-compatible /v1/audio/speech endpoint ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **runtime:** identical-seed batch vs streaming latency comparison ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))


### Bug Fixes

* **serve:** drop gunicorn --preload from single-worker model server ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))


### Documentation

* **handoff:** record Task 4/5 progress and OpenAI endpoint ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **plans:** hermes TTS integration analysis and OpenAI-endpoint plan ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **plans:** record server-side voice decision and ref_audio reality ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* record streaming listening verdict (identical, no seam) ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record completed transport and rollback tests ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record Task 3 per-core overlap go/no-go and preload fix ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **results:** record v0.13.0 baked-image streaming validation ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))
* **run:** document no-preload memory fix and revised 1.7B footprint ([c5d082e](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/c5d082e790f1f3976a21f39915234d3ca8f4d7da))

## [0.13.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.12.0...qwen3-tts-openvino-v0.13.0) (2026-06-30)


### Features

* **runtime:** stream OpenVINO vocoder PCM during generation ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))


### Bug Fixes

* **runtime:** honor BF16 serving load settings in app_worker ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))


### Tests

* **runtime:** validate streaming code capture and transport parity ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))


### Documentation

* **runtime:** record streaming results and operator runbook ([d67a505](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d67a505ccaa51a85717e59bec4fdb43c56c5ecd9))

## [0.12.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.11.1...qwen3-tts-openvino-v0.12.0) (2026-06-29)


### Features

* **export:** infer stateful IR layout and record artifact provenance ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **health:** report active stateful cores and cache capacities ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))
* **runtime:** add stateful KV cache support for the 0.6B main and predictor cores ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))


### Tests

* **runtime:** cover stateful predictor generation-step defaults ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))


### Documentation

* **results:** record 0.6B stateful footprint and quality gates ([7a7b091](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/7a7b091d020ba2bf5ec79f99c8e86e4bc7a41af0))

## [0.11.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.11.0...qwen3-tts-openvino-v0.11.1) (2026-06-29)


### Documentation

* mark M9 closed and shipped in v0.11.0; refresh handoff next steps ([d2dc334](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d2dc334fa974d109e2a588816d799aff7d481cf4))

## [0.11.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.10.0...qwen3-tts-openvino-v0.11.0) (2026-06-29)


### Features

* **m9:** add exact ru_maxrss per-phase attribution to find the generation transient$'\n\n'feat(m9): localize lifetime peak to PyTorch model-load transient$'\n\n'feat(m9): bf16 serving load to eliminate the fp32 load-transient boot spike ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** add pytorch-vs-stateful parity mode to test_stateful_main_parity ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** add static stateful main cache spike with parity test ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** FP32-vs-PyTorch parity (0.6B) and per-mode max_abs tolerance ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** reduce 1.7B generation memory with stateful main cache and early PyTorch weight release ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** wire OPENVINO_MAIN_STATEFUL_MODEL and OPENVINO_RELEASE_TORCH in app_worker ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Bug Fixes

* **ci:** install NumPy for dump-audio unit tests ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** clean up _OVStatefulCore delegation and accept generation_steps ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** fail-closed startup when OPENVINO_RELEASE_TORCH=1 ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **release:** preserve every commit override entry ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Performance Improvements

* **m9:** release PyTorch weights before main-graph compile ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Documentation

* **m9:** correct lifetime-peak root cause and refocus next steps on measuring it ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** listening check passed; update M9 gates status ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** record bf16 serving result (lifetime peak 11.6 to 8.3 GiB)$'\n\n'docs(m9): record bf16 quality-equivalent verdict; bf16 serving adopted$'\n\n'feat(serving): capacity-768 stateful main, silence trim, capacity-tuning docs ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))
* **m9:** record M9 gate results (capacity, latency, concurrency, rollback) ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))


### Miscellaneous Chores

* **m9:** drop committed raw RSS profile and reject raw profiles in repo guard ([08415a5](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08415a58c87460db01cf06f7d30b9069feec33cd))

## [0.10.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.9.1...qwen3-tts-openvino-v0.10.0) (2026-06-29)


### Features

* **runtime:** release PyTorch core weights post-install (M7 memory) ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **export:** add INT4 precision-tagged artifact directories and document M7-M9 findings ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **bench:** add measured 1.7B speed gate (M1.7B-A), with INT4 reaching 1.35x ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))

### Documentation

* **m7:** document OPENVINO_RELEASE_TORCH and OpenVINO-only validation ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **m5:** record 1.7B INT4 results and the stateful-cache design ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))
* **handoff:** add a self-contained next-agent brief ([679799d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/679799d8e2b6166fb5bb1261a83337e18b917abd))

## [0.9.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.9.0...qwen3-tts-openvino-v0.9.1) (2026-06-29)


### Bug Fixes

* **export:** reject unsupported INT8 calibration ([08e1c58](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/08e1c58c0413596fa10d75ffb6a435ede4021662))

## [0.9.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.8.0...qwen3-tts-openvino-v0.9.0) (2026-06-29)


### Features

* **export:** data-aware INT8 calibration (scale_estimation) scaffold ([8739289](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/87392896d8db155ea541ad8cc70251926c4e429b))


### Bug Fixes

* **runtime:** resolve vocoder IR filename; add per-core precision + audio dump ([8739289](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/87392896d8db155ea541ad8cc70251926c4e429b))
* **vocoder:** actually wire the OpenVINO vocoder + add backend provenance ([8739289](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/87392896d8db155ea541ad8cc70251926c4e429b))

## [0.8.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.7.1...qwen3-tts-openvino-v0.8.0) (2026-06-29)


### Features

* **runtime:** add run_bench.sh for simpler harness invocation ([0e3d13c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))
* **runtime:** improve test_ov_generation.py reporting and output path safety ([0e3d13c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))


### Bug Fixes

* **runtime:** include ov_vocoder_runtime.py in runtime image ([0e3d13c](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/0e3d13c180c5e308fd84302823f028fc6f6bc8ad))

## [0.7.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.7.0...qwen3-tts-openvino-v0.7.1) (2026-06-28)


### Bug Fixes

* **runtime:** exclude internal 'vocoder' key from OpenVINO CPU compile_model config ([5d56038](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5d56038c8d35f219e3ced4672392e71628b784fa))

## [0.7.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.6.2...qwen3-tts-openvino-v0.7.0) (2026-06-28)


### Features

* **m4:** buffer-backed K/V cache with OPENVINO_BUFFER_KV guard and bench env helper ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **m4:** wire OpenVINO vocoder IR into the runtime with PyTorch fallback ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))


### Bug Fixes

* **runtime:** correct _single_chunk left-context warmup and return types; add fallback warnings ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** correct vocoder IR 2D/3D shape unpack in _run_ir ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **runtime:** correct vocoder multi-chunk waveform slicing and tensor copy ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))
* **test:** harden code normalization, seed greedy runs, gc for mode=all, add entropy metric ([a78be3d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/a78be3d7a4b137a4588f6af47ad48c028c56a146))

## [0.6.2](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.6.1...qwen3-tts-openvino-v0.6.2) (2026-06-28)


### Bug Fixes

* **harness:** correct frame/codebook axes in M4 code comparison ([d7136c4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/d7136c4c4ef99f5cbe762ecad6879db0ede9ccc5))

## [0.6.1](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.6.0...qwen3-tts-openvino-v0.6.1) (2026-06-28)


### Bug Fixes

* **ci:** make Dockerfile COPY-line check robust to additional files ([5717ddb](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* **docker:** include ov_runtime_config, ov_talker_runtime, bench_common, test_ov_generation in build ([5717ddb](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))
* **scripts:** default M4 reference WAV to persistent project-owned path on dockermisc1 ([5717ddb](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/5717ddb37d5f80398e11ff879a3ed6a882bb3734))

## [0.6.0](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.4...qwen3-tts-openvino-v0.6.0) (2026-06-28)


### Features

* **export:** relax provenance fields to best-effort non-blocking defaults ([e9d9943](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **runtime:** add M4 OpenVINO talker runtime with explicit K/V cache, persistent InferRequests ([e9d9943](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))
* **test:** add generation-level parity harness (code agreement, waveform SNR, latency/RTF) ([e9d9943](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/e9d9943fcdaed612d6997633be2b6f017b1dabc4))

## [0.5.4](https://github.com/nmorgowicz-org/qwen3-tts-openvino/compare/qwen3-tts-openvino-v0.5.3...qwen3-tts-openvino-v0.5.4) (2026-06-28)


### Bug Fixes

* **ci:** authenticate and reduce Docker Hub pulls in image validation ([b320f0d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **ci:** retain reliable GHCR cleanup with 15 versions ([b320f0d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))
* **export:** correct INT8 mode selection and make transformer parity fail closed ([b320f0d](https://github.com/nmorgowicz-org/qwen3-tts-openvino/commit/b320f0d72ad1391874f053a7a8d759a3905c6725))

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
