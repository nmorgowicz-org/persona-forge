# Phase B — technical screening results (2026-10-23)

> **Archived 2026-10-28** together with [the multi-engine plan](20261023-kokoro_phonon_kittentts2.md).
> Kept for provenance — this is not a live plan; active plans live in `docs/plans/`.

Companion to [20261023-kokoro_phonon_kittentts2.md](20261023-kokoro_phonon_kittentts2.md). This is
the **screening pass** from §6.2, not the measurement pass: 1 warmup + 3 trials per case, one
representative voice per engine plus one accent/alternative. It answers "does it run, does it clone,
what does it cost?" and decides what goes to Phase C. Ranking stays in Phase E.

Raw per-run JSON lives in [bench/](bench/). Audio stayed on the test machines, outside Git, and so did
the working directories this page names (`bench/scripts/`, `bench/listen/`, `bench/listen2/`): only the
eight JSON files are in the repository.

## Targets and method

| Target | Spec | Load during run |
| --- | --- | --- |
| `docker-agent` (Linux, Docker) | Intel i7-1360P, 6 vCPU, 16 GiB, cgroup `--cpus=4`, Python 3.13 | **14–23** load average (unrelated workloads: firecrawl/Erlang and a long-running CPU burner). Host is ~3× oversubscribed. |
| `macos-m5max` (native) | Apple M5 Max, 64 GiB, macOS 27.0.1, Python 3.13/3.12 | 3–6 load average (desktop apps) |
| `windows-5090` (native) | AMD Ryzen host, RTX 5090 32 GiB, driver 617.42, Python 3.12/3.13. Kokoro ran on torch 2.11.0+cu128; Kitten 2 ran on the app's pinned stack, torch 2.14.0+cu130 (CUDA 13.0) | quiet |

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

#### Intel re-run in the dev container (later session, host load 4-16)

Re-run inside the relaunched `persona-forge` dev container (compose files `docker-compose.yml` +
`docker-compose.persona-forge-dev.yml`), separate venvs under `/bench`. This container has **no CPU
limit** (`cpu.max` is `max`; 6 CPUs visible, 16 logical on the host), so the "`--cpus=4`" label in
the earlier results JSON does not describe it. Load was lower than in the first pass but still not
quiet.

| Engine | RTF | Notes |
| --- | ---: | --- |
| Phonon 31m | 0.26-0.31 | TTFB 0.10 s, peak RSS 511 MiB, 2 voices |
| Kitten nano (`kittentts` 0.1.3, `nano-0.1`) | 0.50-0.63 | peak RSS 857 MiB; this is the old 0.1 model, not the 0.8 nano |
| Kokoro, default ONNX Runtime | 1.41-1.74 | peak RSS 1.38 GiB |
| Kokoro, `intra_op_num_threads=4`, fp32 | **0.70** | 2 threads 0.90, 6 threads 0.72 |
| Kokoro, `intra_op_num_threads=4`, int8 | **0.64** | 2 threads 0.85, 6 threads 0.78 |
| Pocket-TTS 4.0.1 baseline (what the app ships) | 0.51-0.53 | `alba` preset; load 4.3 s |

The default Kokoro result was a **thread-configuration problem**, not model slowness. With no
explicit thread count, ONNX Runtime sized its pool to all 16 logical CPUs and logged
`pthread_setaffinity_np failed ... Specify the number of threads explicitly`. Pinning four intra-op
threads more than halves RTF. Any Kokoro integration must set thread counts explicitly. The tuning
probe used one 4.5 s utterance, not the corpus.

Against the shipped baseline: Phonon is about 2x faster than Pocket-TTS on this host; tuned Kokoro
is slower than Pocket and Kitten nano but now under real time. The Pocket baseline used a preset,
not a cloned voice, and one run each of `assistant` and `long`.

### Windows RTX 5090 (native)

| Engine | Load | VRAM peak | TTFB | RTF median |
| --- | ---: | ---: | ---: | ---: |
| Kokoro 82M (native torch), torch 2.14.0+cu130 (the app's pin) | 2.49 s | 1,049 MiB | 0.07-0.20 s | **0.008-0.030** |

Rerun on the app's pinned stack (torch 2.14.0+cu130, CUDA 13.0, sm_120). Cases: short 0.070 s,
assistant 0.104 s, long 0.204 s (25.4 s audio). The earlier cu128 run (torch 2.11.0+cu128) gave
0.111, 0.158 and 0.319 s, so cu130 was about 35 % faster here. That is one run of 3 trials each, not
a controlled comparison. The model's parameters sit on `cuda:0`, so there is no silent CPU fallback.

**Kitten TTS 2 (1.7B), Python `kittenml` 0.9.6 (the supported path)**: installs and runs. The C++
fork (`kitten-tts-2-cpp`) was a feasibility probe only; it fails to build on Windows with MSVC 19.44
(`char8_t` in `llama-chat.cpp`) and has no prebuilt binaries, so it is not a shipping path.
`pip install kittenml` provides 115 voices, 16 languages and reference-audio cloning from 5-30 s of
speech (`generate(text, reference="clip.wav")`).

| Target | Backend | Load | Preset RTF | Clone RTF |
| --- | --- | ---: | ---: | ---: |
| M5 Max | torch CPU | n/a | 1.7-1.9 (long 54.6 s for 31.7 s audio) | 3.3 |
| M5 Max | MLX (`kittenml[mlx]`) | n/a | **0.24** | **0.34** |
| RTX 5090 | torch 2.14.0+cu130 CUDA, default eager | 70 s, incl. 243-file download | 1.16-1.36 | not run |
| RTX 5090 | same, **static KV cache + HF decode-step compile** | about 33 s first compiled call | **0.30-0.39** | **0.28-0.42** |

**CUDA diagnosis (5090, torch 2.14.0+cu130, CUDA 13.0).** The weights are on the GPU:
`Qwen3ForCausalLM`, 1,734 M parameters in bf16 on `cuda:0`, plus a 266 M fp32 S3 decoder. In the
default eager path the language model takes about 95 % of wall time (6.0-6.5 s of 6.3-6.7 s) at
about 21 tokens/s, with GPU utilization only 17-24 %. The decoder is 0.25-0.4 s. That is
launch-bound eager decoding, not a compute limit. It is not CPU throttling (Ryzen 7 5800XT at full
clock, Ultimate Performance power plan). Removing the repetition and run penalties moved RTF only
from 1.26 to 1.18, and that run generated 40 s of audio for one sentence, so the penalties are
needed for output quality.

Setting `generation_config.cache_implementation = "static"` lets Hugging Face compile the decode step
with CUDA graphs. A manual `torch.compile(..., mode="reduce-overhead")` on the forward failed with a
CUDA-graph overwrite error; the supported route is to set only the static cache.

| Case (5090, compiled, median of 3) | Preset RTF | Clone RTF |
| --- | ---: | ---: |
| short | 0.39 | 0.42 |
| assistant | 0.32 | 0.31 |
| structured | 0.31 | 0.30 |
| long (about 30 s audio) | 0.30 | 0.28 |

Peak VRAM 8.6 GiB. Cloning used a 2-3 s reference clip, shorter than the 5-30 s the model card
recommends.

**Costs and risks of the compiled path (do not skip):**

- **Tail latency.** Medians hide recompiles. Some trials took 40.8 s (`assistant` preset) and 85.4 s
  (`short` clone) against 1-4 s medians, probably recompilation at new shapes or the one-off load of
  a Whisper transcription model for the reference. I did not separate the causes. An integration
  needs fixed shape buckets and a warm-up pass, and must be measured for worst case, not median.
- **Whisper dependency for cloning.** Cloning without `reference_text` loaded a Whisper model
  (1,259 weights) to transcribe the reference. Supplying the transcript avoids it.
- **Windows needs a compiler toolchain.** The compile path needs `triton-windows` (3.8.0.post29
  worked with torch 2.14.0+cu130) and MSVC Build Tools 2022 on the machine. Linux CUDA torch wheels
  bundle Triton and need a C compiler. A packaged Windows desktop app would have to ship or require
  those, which is a real constraint to resolve before offering this engine there.
- **Not tested:** seed-for-seed audio parity with eager, quality of compiled output, and concurrent
  requests.

Without the compile fix, only the Apple MLX backend runs faster than real time, so Kitten 2 is not an
Intel-CPU option and is slow on CUDA unless compiled.

## Cloning bake-off (objective half; listening not yet done)

Owner decision: use is private and personal, so every cloning option is in scope, each is compared
against Pocket-TTS (what ships today), and the product should let users choose.

**Method.** Two references from the owner's voice library: `r1_default` (the mounted default
reference, 12.8 s) and `r2_aussie` (an OmniVoice-designed Aussie female voice, 11.2 s), both 24 kHz
mono, transcripts supplied to engines that accept them. Four English corpus texts per reference, one
warm-up and 3 timed trials each, 8 clips per engine. Engines: Pocket-TTS 4.0.1 (default settings),
Kitten 2 on Apple MLX, Kitten 2 on the 5090 (compiled), KokoClone. Phonon has no local cloning and
was not included. Scripts: `bench/scripts/clone_bakeoff.py`, `score_clones.py`,
`make_listening_sheet.py`. Reference audio and generated clips stay out of Git.

**Speed (cloning, median RTF over the 8 clips; lower is faster):**

| Engine / target | RTF |
| --- | ---: |
| Pocket-TTS, M5 Max CPU | 0.08-0.10 |
| Kitten 2, M5 Max MLX | 0.15-0.18 |
| KokoClone, M5 Max CPU | 0.14-0.30 (short texts slowest) |
| Kitten 2, RTX 5090, compiled | 0.25-0.34 (one trial 9.1 s vs 3.0 s median) |

Pocket-TTS was **not** run on the Intel container or the 5090 for this test, so the CPU-vs-GPU
comparison across machines is not like for like.

**Objective quality (screening metrics only).** Speaker similarity is the cosine between WavLM-SV
x-vectors of output and reference. Reference points: two different speakers (R1 vs R2) score
**0.854**; one speaker against its own other half scores **0.979-0.992**. Word error rate comes from
Whisper-small against the input text.

| Engine | Mean similarity to reference | WER mean / max |
| --- | ---: | ---: |
| Pocket-TTS | **0.962** | 0.103 / 0.526 |
| KokoClone | 0.853 | 0.028 / 0.105 |
| Kitten 2, MLX | 0.847 | 0.032 / 0.158 |
| Kitten 2, 5090 compiled | 0.852 | 0.043 / 0.158 |

How to read it:

- By this metric Pocket-TTS transfers speaker identity far better. It sits near the same-speaker
  ceiling, while Kitten 2 and KokoClone score about where a *different* person scores (0.854). The
  "own minus other reference" margin is about 0.09 for all four, so it does not separate them.
  WavLM-SV is not calibrated for synthetic voices and both references are themselves synthetic or
  processed, so treat this as a strong prompt to listen, not a verdict.
- Pocket-TTS's WER is a real failure on structured text, not metric noise. For "invoice AB-104 totals
  $1,234.56" Whisper heard "AB 10 of 4 totals $1020.34.56" (WER 0.26 and 0.53 on the two references).
  KokoClone and Kitten 2 read the same sentence correctly. Pocket needs text normalisation for
  numbers and codes.
- Kitten 2 outputs on the two Aussie references all peaked at 0.99 with RMS 0.16-0.22, against about
  0.09 for Pocket and KokoClone, so they were roughly twice as loud. On the later US and UK
  references the peaks ranged 0.63-0.99 and RMS was about 0.10 against 0.065 (Pocket) and 0.085
  (KokoClone), so "peak-normalised to 0.99" was too strong; the accurate claim is that Kitten 2 is
  louder, by 1.5-2x here. The listening sheets are level-matched for this reason.
- Whisper-small is itself fallible on numbers; a human check of the `structured` clips is warranted.
- Same model on two backends (MLX vs compiled CUDA) scored alike (0.847 vs 0.852), which is weak
  evidence that compiling did not change identity transfer. Seed-for-seed parity was not tested.

**Listening results (owner, blind, 32 clips, 1-5 scale, one rater).** `bench/listen/index.html` held 8
items with 4 anonymous, level-matched, shuffled clips each. Means per engine (8 clips each):

| Engine | Similarity | Naturalness | Artifacts (5 = clean) |
| --- | ---: | ---: | ---: |
| Pocket-TTS | **4.50** | 3.75 | 4.12 |
| Kitten 2, M5 MLX | 3.62 | 3.75 | 4.75 |
| Kitten 2, 5090 compiled | 2.75 | 3.62 | **5.00** |
| KokoClone | 2.38 | 3.00 | 3.12 |

By reference, Pocket scored similarity 4.0 on `r1_default` and 5.0 on `r2_aussie` (naturalness 2.75 and
4.75). Kitten 2 MLX scored 3.5 and 3.75. KokoClone was worst on `r1_default` (similarity 2.0,
artifacts 2.25).

Reading it, with n=8 per engine and one listener, so differences under about 0.5 are not meaningful:

- **Pocket-TTS is the best cloner by ear**, agreeing with the objective score. Its weak spot is
  `r1_default` naturalness (2.75), and its number misreading is a separate, measured failure.
- **Kitten 2 is a credible second**: cleanest audio, similar naturalness, weaker identity.
- **The two Kitten 2 backends differ by ear** (similarity 3.62 MLX vs 2.75 CUDA), though they scored
  alike objectively (0.847 vs 0.852). Same model, so this is either sampling noise at n=8, or the
  compiled static-cache path changes output quality. Unresolved; it needs the same seed and text
  rendered on both backends and compared directly before the CUDA path is trusted.
- **KokoClone is the weakest** on identity, naturalness and artifacts.

**Confound the owner raised, which limits all of the above.** Both references are **female Aussie
accents** (and `r2_aussie` is an OmniVoice-designed voice, so synthetic). Nothing here tests male
voices, American or British accents, or a real recorded person. The result may not generalise:
KokoClone re-voices a US/UK Kokoro source toward the target, so an Australian target is a plausible
reason for its weak scores; Pocket or Kitten 2 could rank differently on other voices. Treat the
ranking as "cloning the owner's two existing voices", which is the app's current workflow, and not
as a general cloning ranking.

**Artifacts, measured.** All three clips rated 2/5 for artifacts (c001, c005, c010) are KokoClone on
`r1_default`, and they have 3-6.6 % of their energy above 6 kHz against about 1 % for Pocket and
about 2 % for Kitten 2, consistent with a noisy vocoder. Pocket's three 3/5 clips are structured-text
and long cases, one of them the clip where numbers were misread. No clip in the first round clips (0.0 %
of samples at full scale). What the artifacts sounded like is the listener's report ("some were
weird") and is not yet recorded here beyond which clips were rated low.

### Second round: real human US and UK references

Run because both first-round references were female Aussie voices, one of them synthetic.
References are real recordings from the VCTK corpus (CC BY 4.0, via the `kth-tmh/vctk` copy, which
carries age, gender and accent): **`r3_us_f`** speaker p299, American (California), age 25, 14.4 s from
three unique sentences; **`r4_uk_f`** speaker p228, English (Southern England), age 22, 11.6 s from two
unique sentences. Chosen by the owner's brief (young female, American and British); the sentences are
VCTK's elicitation text, so the references contain no personal data. Same engines, texts and
protocol as round one, 16 new clips per engine set.

| Engine | Similarity, US ref | Similarity, UK ref | Speed (clone RTF) |
| --- | ---: | ---: | ---: |
| Pocket-TTS, M5 CPU | 0.938 | **0.975** | 0.06-0.08 |
| Kitten 2, M5 MLX | 0.953 | 0.931 | 0.16-0.20 |
| Kitten 2, 5090 compiled | 0.947 | 0.940 | 0.25-0.31 |
| KokoClone, M5 CPU | **0.959** | 0.922 | 0.16-0.33 |

Reference points for these two speakers: different-speaker floor **0.769**, same-speaker ceiling
**0.990-0.995**. Every engine is near the ceiling, so on real human US and UK voices the objective
gap between engines is small (0.92-0.98), and KokoClone is no longer near the floor as it was on the
Aussie references. The earlier floor was 0.854 because the two Aussie voices resemble each other, which
is why that metric separated engines poorly.

- **Pocket-TTS's number misreading reproduces** on this round: for "invoice AB-104 totals $1,234.56
  for 3.5 kilograms" Whisper heard "AB-1004 totals 1,034 bond 5.6" (WER 0.26). It is now a finding
  on three of four references.
- **The Kitten 2 CUDA WER of 0.316 is a metric artefact**: Whisper wrote "23rd", "9.45am", "3.5kg",
  which differ from the input text in formatting only. The word-error scorer does not normalise
  numbers or abbreviations, so WER overstates errors for every engine on the structured case.
- Speed is unchanged by reference voice.

**Listening for round two is pending.** `bench/listen2/index.html` has 8 items with 32 anonymous,
level-matched, shuffled clips. No round-two ratings exist, so identity by ear on non-Aussie voices is
unknown; the objective similarity alone has already proved a poor guide once.

**Round two listening results (owner, blind, 32 clips, 8 per engine, one rater).**

| Engine | Similarity | Naturalness | Artifacts (5 = clean) |
| --- | ---: | ---: | ---: |
| Pocket-TTS | 4.38 | **4.50** | 5.00 |
| Kitten 2, M5 MLX | 4.38 | 4.00 | 5.00 |
| Kitten 2, 5090 compiled | 4.25 | 4.25 | 5.00 |
| KokoClone | 4.12 | 4.12 | 5.00 |

All four are within about 0.3 on every axis, which is inside the noise for n=8 and one listener. No
clip was rated below 5 for artifacts, so the weird artifacts in round one were specific to the Aussie
references (KokoClone on `r1_default` above all). The two Kitten 2 backends are indistinguishable here
(4.38 vs 4.25), so the round-one MLX/CUDA gap looks like noise or a reference effect, not a compile
defect; seed-matched comparison is still unrun. KokoClone is not weak on real US/UK voices (UK 4.5).

**Conclusion.** On real US and UK female voices all four cloners are comparably good by ear; Pocket
leads only slightly on naturalness. Round one's gap came from the Aussie references. Because Pocket is
fastest and already shipped, it stays the default; the others are credible optional choices, which
matches the "let users choose" decision. Male voices and the owner's own recordings remain untested.

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
   2.8 s to first audio on a long sentence). On the Intel host it is **0.64-0.70 RTF once ONNX
   threads are pinned to 4** (1.4-1.7 with defaults). On the 5090 it is trivially fast, but that
   hardware is not the deployment target.
4. **Kitten nano is fast but redundant.** 15M, 8 English voices, no streaming, ~0.024 RTF on M5.
   It clips on the long case (peak 1.0) and its prosody is the weakest of the three. Phonon beats it
   on quality evidence, size, streaming and latency; there is no gap for it to fill.
5. **KokoClone is a real CPU cloning path.** Zero-shot from 3–10 s, 8 languages, Apache-2.0 code,
   RTF 0.15–0.23 on M5 with no GPU. It re-voices Kokoro output through Kanade, so identity transfer
   needs listening (Phase E) before it can be trusted; it is the only screened option that clones
   without a GPU or a cloud step.
6. **The 5090 helps one engine: Kitten 2, once its decode step is compiled.** Native Kokoro on CUDA works (sm_120 confirmed, torch 2.14.0+cu130) but is unnecessary.
   Kitten 2 on the app's torch 2.14.0+cu130 is launch-bound in eager mode (1.2-1.3 RTF) and reaches
   0.28-0.42 RTF with a static KV cache and compiled decode step. KokoClone would use CUDA if
   present. The 5090 matters for Phase E quality checks and for this one engine.
7. **Kitten TTS 2 is the only screened engine with a documented local cloning path and 115 voices.
   It is fast only on Apple MLX or a compiled CUDA path, and the weights carry a restrictive licence.** Weights are under the **Stellon Labs
   Community License**, not Apache: commercial use needs registration and is limited to under
   USD 1M annual revenue and under USD 1M total funding, requires "Powered by KittenML"
   attribution, and bars using outputs to train other models. The `kittenml` wheel needs
   `torch>=2.6` and `transformers>=4.55`; the app pins `torch>=2.13.0,<2.15` and the container has
   transformers 5.12.1, so a co-install looks feasible but was **not tested** against the app's
   lockfile. Treat it as an isolated pack process regardless.
8. **Packaging costs are real but containable.**
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
| Kokoro (threads pinned to 4) / Intel | Batch | RTF 0.64-0.70, slower than the Pocket baseline (0.51-0.53); default threads give 1.4-1.7 and are not usable |
| Kitten nano (old 0.1 model) / Intel | Batch | RTF 0.50-0.63, no streaming |

## Blocked / unmeasured

- **Kitten TTS 2 (1.7B) compiled path**: seed parity with eager, concurrency, recompile/tail-latency
  root cause, and a packaging answer for Triton and MSVC on Windows are all open. The first full
  eager run hung at about 72 CPU-minutes and was killed without a diagnosis; two later runs
  completed normally, so I could not reproduce it. The C++ route is dropped; the supported path is
  `pip install kittenml`. vLLM was ruled out by the owner.
- **KokoClone on the 5090 / Windows**: not run. It selects CUDA automatically; expected to be much
  faster than the M5 CPU result, but needs a Windows venv and reference audio.
- **Kokoro ONNX with CUDA provider**: not run; native torch already answers the sm_120 question and
  ONNX Runtime GPU adds cuDNN/DLL setup.
- **Phonon 40m**: gated + CC BY-NC 4.0; not downloaded (no accepted terms, non-commercial licence).
- **Pocket baseline**: measured once on the Intel container (see re-run section), with a preset
  voice. Cloned-voice latency and identity are compared in Phase E.

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
4. **Do not integrate Kitten nano.** **Re-evaluate Kitten 2 for cloning**, but only as an optional
   isolated pack. The owner has said the use is private and personal, so the licence terms are not a
   blocker. It is fast on Apple MLX (0.24 preset / 0.34 clone RTF) and on CUDA once the decode step
   is compiled (0.28-0.42), and not usable on the Intel host (RTF 1.7+ on CPU).
5. **Measurement pass** (20+ trials, p95, VRAM/RSS, cold/warm load) is only needed for the engines
   that survive Phase C integration; today's numbers are screening-grade.

## Caveats

- docker-agent load was still non-zero in the re-run (4-16) and was moderate in the first pass
  (14-23); treat absolute latencies as upper bounds and the ordering as the signal. Re-measure on
  a quiet host before quoting numbers to users.
- Three trials, one voice per engine (plus one alternative). No p95 is meaningful at n=3.
- "Sounds broken" was checked only mechanically (duration, peak/RMS, clipping); listening is Phase E.
- Kitten's long-case peak of 1.0 suggests clipping; any integration needs output normalisation.
