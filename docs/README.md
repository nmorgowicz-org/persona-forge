# Persona Forge — Documentation

Start here. Docs are grouped by what you are trying to do.

## Run it

| Doc | What it covers |
|---|---|
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Docker Compose setup, first boot, the export step for Qwen/OpenVINO |
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

## Develop it

| Doc | What it covers |
|---|---|
| [dev/LOCAL_SETUP.md](dev/LOCAL_SETUP.md) | `uv`-managed local environment |
| [DEV_TEST_LOOP.md](DEV_TEST_LOOP.md) | The edit → test → deploy loop |
| [TEST_STRATEGY.md](TEST_STRATEGY.md) | Test tiers and what belongs in each |
| [dev/DESIGN_SYSTEM.md](dev/DESIGN_SYSTEM.md) | Frontend design tokens and component primitives |
| [dev/validation_checks.md](dev/validation_checks.md) | Pre-merge validation commands |

## Agent reference

Compact references written for AI coding agents working in this repo.

| Doc | What it covers |
|---|---|
| [agent-reference/RUNTIME_AND_MEMORY.md](agent-reference/RUNTIME_AND_MEMORY.md) | Runtime invariants, memory ceilings |
| [agent-reference/EXPORT_SYSTEM.md](agent-reference/EXPORT_SYSTEM.md) | The OpenVINO export pipeline |
| [agent-reference/TRANSFORMERS_COMPAT.md](agent-reference/TRANSFORMERS_COMPAT.md) | Transformers 5 compatibility shims |

## Archive

- [`dev/features/`](dev/features/), [`dev/voice/`](dev/voice/), [`dev/prosody/`](dev/prosody/) —
  dated design and implementation plans, kept as a record
- [`dev/benchmarks/`](dev/benchmarks/) — benchmark logs from the OpenVINO era
- [`dev/resolved/`](dev/resolved/) — completed plans
- [`plans/`](plans/) — in-flight plans

> Docs under the archive are **historical**. Where they conflict with the current docs above,
> the current docs win.
