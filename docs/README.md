# Persona Forge — Documentation

Start here. Docs are grouped by what you are trying to do.

## Run it

| Doc | What it covers |
|---|---|
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Docker Compose setup, first boot, the export step for Qwen/OpenVINO |
| [RUN_LOCAL.md](RUN_LOCAL.md) | Running natively — source checkout, installed wheel, or launcher archive, no Docker |
| [MIGRATION.md](MIGRATION.md) | Moving a deployment's data between Docker and native |
| [ENV_REFERENCE.md](ENV_REFERENCE.md) | Every environment variable, with defaults |
| [api/HTTP_API_REFERENCE.md](api/HTTP_API_REFERENCE.md) | Every HTTP endpoint, request and response shapes |

## Understand it

| Doc | What it covers |
|---|---|
| [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md) | Components, request flow, endpoint map |
| [architecture/FRONTEND_OVERVIEW.md](architecture/FRONTEND_OVERVIEW.md) | React pages, zustand state, key UI flows |
| [architecture/MODEL_SWAP_AND_QUEUEING.md](architecture/MODEL_SWAP_AND_QUEUEING.md) | Backend swapping, request queueing, idle unload |
| [architecture/pocket_tts_integration.md](architecture/pocket_tts_integration.md) | The default CPU backend and its prosody behavior |
| [architecture/OMNIVOICE_REFERENCE.md](architecture/OMNIVOICE_REFERENCE.md) | OmniVoice accent engine, audition flow, licensing |
| [architecture/STUDIO_LIBRARIES.md](architecture/STUDIO_LIBRARIES.md) | Voice/segment/project libraries: storage layout, ID scheme, invariants |
| [architecture/ACCELERATOR_FAMILIES.md](architecture/ACCELERATOR_FAMILIES.md) | GPU family resolution and per-family first-boot torch install (Phase A6) |
| [architecture/VOICE_DESIGN.md](architecture/VOICE_DESIGN.md) | Qwen VoiceDesign: model, design flow, design→library lifecycle |
| [architecture/PERSONA_FORGE_STUDIO.md](architecture/PERSONA_FORGE_STUDIO.md) | Studio UI architecture: layout, panels, cross-cutting flows |

## Develop it

| Doc | What it covers |
|---|---|
| [dev/LOCAL_SETUP.md](dev/LOCAL_SETUP.md) | `uv`-managed local environment |
| [DEV_TEST_LOOP.md](DEV_TEST_LOOP.md) | The edit → test → deploy loop |
| [TEST_STRATEGY.md](TEST_STRATEGY.md) | Test tiers and what belongs in each |
| [dev/DESIGN_SYSTEM.md](dev/DESIGN_SYSTEM.md) | Frontend design tokens and component primitives |
| [dev/validation_checks.md](dev/validation_checks.md) | Pre-merge validation commands |
| [dev/PROSODY_HARDENING.md](dev/PROSODY_HARDENING.md) | Prosody alignment hardening: shared edit/repair contracts |
| [dev/OUTPUT_POLISH_MATRIX.md](dev/OUTPUT_POLISH_MATRIX.md) | Objective invariants delivered audio must satisfy |
| [dev/INTERNAL_OPERATIONS.md](dev/INTERNAL_OPERATIONS.md) | Host-specific ops: docker-agent layout, export, deploy |

## Agent reference

Compact references written for AI coding agents working in this repo.

| Doc | What it covers |
|---|---|
| [agent-reference/RUNTIME_AND_MEMORY.md](agent-reference/RUNTIME_AND_MEMORY.md) | Runtime invariants, memory ceilings |
| [agent-reference/EXPORT_SYSTEM.md](agent-reference/EXPORT_SYSTEM.md) | The OpenVINO export pipeline |
| [agent-reference/TRANSFORMERS_COMPAT.md](agent-reference/TRANSFORMERS_COMPAT.md) | Transformers 5 compatibility shims |

## Archive

- [`archive/`](archive/) — dated design, implementation, and analysis plans, grouped by topic,
  kept as a record once resolved or superseded
- [`dev/benchmarks/`](dev/benchmarks/) — benchmark logs from the OpenVINO era
- [`archive/openvino/OPENVINO_IMPLEMENTATION.md`](archive/openvino/OPENVINO_IMPLEMENTATION.md)
  and [`dev/benchmarks/OPENVINO_RESULTS.md`](dev/benchmarks/OPENVINO_RESULTS.md) —
  Qwen3-TTS/OpenVINO-era implementation and benchmark records (both carry historical banners;
  AGENTS.md still cites the staged validation gates in the former)
- [`plans/`](plans/) — in-flight plans

> Docs under the archive are **historical**. Where they conflict with the current docs above,
> the current docs win.
