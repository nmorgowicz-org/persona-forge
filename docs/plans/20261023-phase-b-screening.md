# Phase B — technical screening results (2026-10-23)

Companion to [20261023-kokoro_phonon_kittentts2.md](20261023-kokoro_phonon_kittentts2.md). This is
the **screening pass** from §6.2, not the measurement pass: 1 warmup + 3 trials per case, one
representative voice per engine plus one accent/alternative. It answers "does it run, does it clone,
what does it cost?" and decides what goes to Phase C. Ranking stays in Phase E.

Raw per-run JSON lives in [bench/](bench/). Audio stayed on the test machines, outside Git.

## Targets and method

| Target | Spec | Load during run |
| --- | --- | --- |
| `docker-agent` (Linux, Docker) | Intel i7-1360P, 6 vCPU, 16 GiB, cgroup `--cpus=4`, Python 3.13 | **14–23** load average (unrelated workloads: firecrawl/Erlang and a long-running CPU burner). Host is ~3× oversubscribed. |
| `macos-m5max` (native) | Apple M5 Max, 64 GiB, macOS 27.0.1, Python 3.13/3.12 | 3–6 load average (desktop apps) |
| `windows-5090` (native) | AMD Ryzen host, RTX 5090 32 GiB, driver 617.42, Python 3.12/3.13, torch 2.11.0+cu128 | quiet |

Corpus: frozen 2026-10-23, SHA-256 `cd24e22a18dd33160858b446d7d465b9df06ec357b9d410ea2ccbf681d8d76a8`
(short, assistant reply, structured text, ~600-char narration, one French and one German sentence).
All engines were installed into throwaway venvs; nothing was added to the app's environment.

Every engine ran in its own venv with its own cache. docker-agent runs used an ephemeral
`python:3.13-slim` container with `--cpus=4`, `OMP_NUM_THREADS=4`, and models mounted from the host.

## Results

### macOS M5 Max (CPU, native)

| Engine | Load | Peak RSS | TTFB (long) | RTF median | Presets | Languages | Local cloning |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Phonon 31m (`ptts` 0.4.1) | 0.59 s | 378 MiB | **0.010 s** | **0.018–0.024** | catalog (~100) | en | **No** (`supports_voice_cloning = False`) |
| Kitten nano 15M (`kittentts` 0.1.3) | 0.81 s | 694 MiB | n/a (batch) | 0.022–0.027 | 8 | en | No |
| Kokoro 82M (`kokoro-onnx` 0.6.1) | 0.30 s | 1,530 MiB | 2.81 s | 0.108–0.123 | 54 | en, fr, es, it, pt-BR, hi, ja, zh | No |
| KokoClone (Kokoro-ONNX + Kanade) | 1.93 s | n/a | n/a (batch) | 0.147–0.229 | Kokoro's 54 + reference voice | same 8 | **Yes, zero-shot 3–10 s** |

Per-case medians (seconds of compute for the listed audio):

| Engine | short (2.1 s) | assistant (9.0 s) | structured (11.7 s) | long (24.7 s) |
| --- | ---: | ---: | ---: | ---: |
| Phonon | 0.060 | 0.175 | 0.219 | 0.460 |
| Kitten nano | 0.059 | 0.210 | 0.188 | 0.574 |
| Kokoro | 0.257 | 0.986 | 1.293 | 2.736 |
| KokoClone | 0.508 | 1.496 | — | — |

KokoClone's first call (12.6 s) is initialization; steady state is the table above. Its cloning
reference was an 8 s Phonon clip; output is 24 kHz.

### docker-agent (Intel i7-1360P, 4-CPU cgroup, **host load 14–23**)

| Engine | Load | Peak RSS | TTFB (long) | RTF median |
| --- | ---: | ---: | ---: | ---: |
| Phonon 31m | 0.84 s | 425 MiB | **0.056 s** | **0.22–0.25** |
| Kitten nano 15M | 3.84 s | 547 MiB | n/a | 0.81–1.01 |
| Kokoro 82M | 2.39 s | 1,375 MiB | 49.9 s | 1.95–2.98 |

Per-case medians:

| Engine | short | assistant | structured | long |
| --- | ---: | ---: | ---: | ---: |
| Phonon | 0.55 s | 2.04 s | 2.84 s | 6.32 s |
| Kitten nano | 1.98 s | 8.97 s | 7.19 s | 19.69 s |
| Kokoro | 6.21 s | 20.50 s | 24.11 s | 48.20 s |

These absolute numbers are **not** the i7's capability — they are what the host delivers while
oversubscribed by unrelated services. The ordering is still decisive: Phonon is ~4× faster than
Kitten nano and ~9× faster than Kokoro in the same window, and it is the only engine that stays
comfortably under real time (RTF 0.22 vs 0.9 vs 2.2).

### Windows RTX 5090 (native)

| Engine | Load | VRAM peak | TTFB | RTF median |
| --- | ---: | ---: | ---: | ---: |
| Kokoro 82M (native torch) | 3.12 s | 1,083 MiB | 0.11–0.32 s | **0.013–0.047** |

sm_120 confirmed (`capability (12, 0)`, torch 2.11.0+cu128, CUDA 12.8) and the model's parameters
report `cuda:0`, so no silent CPU fallback. Cases: short 0.111 s, assistant 0.158 s, long 0.319 s
(25.4 s audio).

**Kitten TTS 2 (1.7B, C++)**: does not build on Windows with the documented flags. MSVC 19.44
rejects `llama-chat.cpp` (`char8_t` → `const char*`); the global `/Zc:char8_t-` workaround then
breaks the vendored nlohmann JSON (`std::u8string` missing). A targeted per-file patch or a newer
vendored llama.cpp is required before it can be screened.

## Findings

1. **Phonon 31m is the CPU winner.** 65 MB q8, no PyTorch, ~0.02 RTF on Apple silicon and 0.22 RTF
   on a badly loaded 6-vCPU Intel host, with 10–60 ms time to first audio. It is the only candidate
   that stays usable on docker-agent as it runs today. Apache-2.0 weights, MIT/Apache runtime.
2. **Phonon does not clone locally.** `supports_voice_cloning` is false; voice design/cloning happens
   in Gradium Studio behind an API key, and you download a `.safetensors`. Voice *catalog* use is
   local. The 31m model is English-only; the five-language models are 40m and **CC BY-NC 4.0**
   (non-commercial), and gated behind HF terms.
3. **Kokoro is the multilingual preset engine.** 54 voices across en-US/en-GB, fr, es, it, pt-BR,
   hi, ja, zh — but **no German** in this build, and no cloning. ONNX CPU RTF is ~0.11 on M5 (batch:
   2.8 s to first audio on a long sentence) and unusable on the currently loaded docker-agent.
   On the 5090 it is trivially fast, but that hardware is not the deployment target.
4. **Kitten nano is fast but redundant.** 15M, 8 English voices, no streaming, ~0.024 RTF on M5.
   It clips on the long case (peak 1.0) and its prosody is the weakest of the three. Phonon beats it
   on quality evidence, size, streaming and latency; there is no gap for it to fill.
5. **KokoClone is a real CPU cloning path.** Zero-shot from 3–10 s, 8 languages, Apache-2.0 code,
   RTF 0.15–0.23 on M5 with no GPU. It re-voices Kokoro output through Kanade, so identity transfer
   needs listening (Phase E) before it can be trusted; it is the only screened option that clones
   without a GPU or a cloud step.
6. **The 5090 does not accelerate this candidate set.** Native Kokoro on CUDA works perfectly
   (sm_120 confirmed) but is unnecessary; Kitten 2's C++ runtime is CPU-focused (GGML + CPU LibTorch,
   `GGML_CUDA=OFF` in the documented build); KokoClone would use CUDA if present. The 5090 matters
   for Phase E quality checks and for any future GPU engine, not for these.
7. **Packaging costs are real but containable.**
   - `kokoro-onnx` and `kittentts` pull **`phonemizer` + `espeak-ng` (GPL-3.0)**. Kitten and Kokoro
     also need a system `espeak-ng` (`brew install espeak-ng` on macOS; `apt-get install espeak-ng`
     on slim Linux); the Python wheels do not cover macOS/Linux-slim.
   - KokoClone adds PyTorch + torchaudio + a git-installed tokenizer (~2 GB) and needs Python ≤3.12.
   - Phonon is a native wheel: no torch, no espeak, no system libraries.
   - Native Kokoro's spaCy model auto-download shells out to `uv pip` and fails unless
     `VIRTUAL_ENV` is set — a launch-environment trap for pack installers.

## Tiers (screening only)

| Engine / target | Tier | Why |
| --- | --- | --- |
| Phonon / M5, Intel CPU | Conversational | TTFB ≤ 60 ms, RTF ≤ 0.25 |
| KokoClone / M5 | Batch | No streaming; 0.5–1.5 s total for short/assistant |
| Kokoro / M5 | Batch | TTFB 2.8 s; sustained RTF 0.11 |
| Kokoro / 5090 | Conversational | TTFB ≤ 0.32 s, RTF 0.013 |
| Kitten nano / M5 | Conversational | Total ≤ 0.6 s even without streaming |
| Kokoro, Kitten nano / docker-agent as loaded today | Not recommended | RTF ≥ 0.8–2.2; Kokoro is slower than real time |

## Blocked / unmeasured

- **Kitten TTS 2 (1.7B)**: Windows build blocked. Default C++20 fails in `llama-chat.cpp`; the
  global `/Zc:char8_t-` workaround fails in the vendored nlohmann JSON (`std::u8string`). Needs a
  per-file flag/patch or a newer llama.cpp. Cloning also needs an offline preparation step with a
  reference transcript, and the runtime is a batch CLI (no streaming), with a CPU LibTorch decoder.
- **KokoClone on the 5090 / Windows**: not run. It selects CUDA automatically; expected to be much
  faster than the M5 CPU result, but needs a Windows venv and reference audio.
- **Kokoro ONNX with CUDA provider**: not run; native torch already answers the sm_120 question and
  ONNX Runtime GPU adds cuDNN/DLL setup.
- **Phonon 40m**: gated + CC BY-NC 4.0; not downloaded (no accepted terms, non-commercial licence).
- **Pocket baseline**: not re-measured here; Phase E compares against it in-app.

## Implications for Phase C

1. **Integrate Phonon 31m first** as a preset-only, streaming, English engine. It is the only
   candidate that improves the product on the hardware we actually deploy to, and its licence is
   clean. Pack: ~65 MB q8 + catalog voices; no Python deps beyond `ptts`/numpy.
2. **Integrate Kokoro second**, as the multilingual preset engine, only if the GPL
   (`phonemizer`/`espeak-ng`) boundary is acceptable. Run it in its own pack process, never in the
   web worker.
3. **Treat KokoClone as an evaluation, not a ship decision yet**: add it to the Compare tab in
   Phase E, with cloned-voice identity tests against Pocket. If it wins on identity, it is the CPU
   cloning path; if not, Pocket remains the only cloner.
4. **Do not integrate Kitten nano.** **Defer Kitten 2** until the build and offline cloning prep are
   proven; its CPU-only runtime weakens the case for the 5090.
5. **Measurement pass** (20+ trials, p95, VRAM/RSS, cold/warm load) is only needed for the engines
   that survive Phase C integration; today's numbers are screening-grade.

## Caveats

- docker-agent was heavily oversubscribed; treat its absolute latencies as an upper bound and the
  engine ordering as the signal. Re-measure on a quiet host before quoting numbers to users.
- Three trials, one voice per engine (plus one alternative). No p95 is meaningful at n=3.
- "Sounds broken" was checked only mechanically (duration, peak/RMS, clipping); listening is Phase E.
- Kitten's long-case peak of 1.0 suggests clipping; any integration needs output normalisation.
