# Output-Polish Validation Matrix

Objective, measurable invariants delivered audio must satisfy after a style
preset is applied. The executable half is
`tests/tier1_unit/test_output_polish_matrix.py`; keep the two in sync.

`src/qwen3_tts/audio_style.py` owns one preset table. `STYLE_PRESETS` display
metadata and `apply_style_preset` execution are derived from that table, so
advertised LUFS/peak values must match delivered behavior.

## Invariants

| Invariant | Threshold | Rationale |
| --- | --- | --- |
| `off` bypass | Output samples exactly equal input | Users can disable finishing without hidden normalization |
| Request bypass | `postprocess: false` preserves the prior trim-only PCM | API callers can opt out of the default chain |
| Sample peak ceiling | <= -1.0 dBFS (+0.02 linear tolerance) | Headroom for downstream encoders; this is not a dBTP claim |
| Hot input safety | Output peak <= 1.0 for 3x over-driven input | Limiter must catch over-driven references |
| Integrated loudness | Within +/-1.5 LU of the preset target | Consistent perceived volume across voices/presets |
| Metadata parity | `STYLE_PRESETS[preset].lufs/peak` equals the tested target | UI labels stay honest |

## Per-Preset Targets

| Preset | Delivered LUFS | Peak ceiling | Extra DSP in chain |
| --- | --- | --- | --- |
| off | bypass | bypass | none |
| default | -16.0 | -1.0 dBFS sample peak | normalize -> limit |
| Neutral | -20.0 | -1.0 dBFS | normalize -> limit |
| Clean | -20.0 | -1.0 dBFS | compress(-24, 2.5) -> normalize -> limit |
| Broadcast | -20.0 | -1.0 dBFS | compress(-20, 3.0) -> normalize -> presence boost -> limit |
| Calm | -23.0 | -1.0 dBFS | time-stretch 1.05 -> shape pauses 1.10 -> warm EQ -> normalize -> limit |
| Energetic | -20.0 | -1.0 dBFS | time-stretch 0.95 -> shape pauses 0.90 -> compress(-20, 2.0) -> normalize -> limit |
| Storyteller | -23.0 | -1.0 dBFS | warm EQ -> compress(-24, 2.0) -> shape pauses 1.10 -> normalize -> limit |

The `default` house chain applies when a generation request omits
`style_preset`. It intentionally does not shape pauses, compress, or EQ. Set
`postprocess: false` per request, or `TTS_DEFAULT_DSP=off` for the server-wide
implicit-default kill switch. The environment switch does not disable an
explicitly requested style preset.

## Running

```bash
PYTHONPATH=.:src pytest tests/tier1_unit/test_output_polish_matrix.py -q
```
