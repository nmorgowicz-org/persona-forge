# Dev / Test Loop with dockermisc1

This doc exists so future sessions (Claude or human) can quickly understand:
- What’s on this branch
- How the app runs on dockermisc1
- How to rapidly test local changes

## 1. Branch and purpose

- Branch: voice-design-accent-and-queueing
- Goal: implement Persona Forge / OmniVoice workflows with accent-specific voice design, streaming segments, and queueing while models load.

Key capabilities:
- Per-sentence OmniVoice segment generation (audition → cherry-pick → stitch → save).
- Streaming segments into the rack as they complete.
- Diverse candidates (guidance_scale), real progress/ETA.
- Async model loading + job queueing (no hard failure while loading).
- Lazy Base model swap-back (stays unloaded until needed).
- Persistent segment library and “Save to library” for VoiceDesign.
- UX: composer-style Script input, Non-Verbals/Examples toolbars, sidebar polish.

## 2. dockermisc1: how the app runs

- Machine: dockermisc1 (access via SSH as usual).
- Container: qwen3-tts
- Image: qwen3-tts-openvino:voice-design-accent-and-queueing
- Port: 8318 → 8318 (HTTP)

Runtime mode:
- Command:
  - scripts/entrypoint.sh gunicorn qwen3_tts.app:app \
    -w 1 -k gthread --threads 4 --timeout 300 \
    --bind 0.0.0.0:8318 --log-level info
- Env (important subset):
  - TTS_BACKEND=openvino
  - MODEL_SIZE=1.7B
  - LOW_RAM_MODE=1
  - FRONTEND_ENABLED=1
  - (REF_TEXT set to a fixed reference; confirm if it must change for your use.)

Key mounts:
- Host: /var/data/autopirate/qwen3-tts-new/voices
  - Container: /voices
- Host: /var/data/autopirate/qwen3-tts-new/segments
  - Container: /segments
- Host: /var/data/autopirate/qwen3-tts-new/reference/voice_A.wav
  - Container: /voice/reference.wav
- Host: /var/data/autopirate/qwen3-tts-new/model
  - Container: /root/.cache/huggingface/hub
- Host: /var/data/autopirate/qwen3-tts-new/ov
  - Container: /ov
- Host: /home/nick/projects/qwen3-tts-openvino/src
  - Container: /app/src

Important:
- The running container uses /app/src from:
  - /home/nick/projects/qwen3-tts-openvino/src on dockermisc1.
- That directory is git-tracked to the same repo as this project.

## 3. Dev-test loop (current default)

Use this when developing locally (or in Claude) and testing on dockermisc1.

From the local repo (e.g. this CWD):

1) Make changes:
   - Edit backend/frontend in src/qwen3_tts and frontend/src as needed.
2) Commit and push:
   - git add -A
   - git commit -m "descriptive message"
   - git push origin voice-design-accent-and-queueing
3) On dockermisc1:
   - cd /home/nick/projects/qwen3-tts-openvino
   - git pull origin voice-design-accent-and-queueing
4) Reload backend:
   - The container’s code mount already reflects the new src, but gunicorn has no auto-reload.
   - Choose one:
     - Fast reload: docker exec qwen3-tts kill -HUP 1
     - Or full restart (safer for bigger changes): docker restart qwen3-tts
5) Test:
   - Hit http://<dockermisc1-host>:8318 to verify behavior.

Notes:
- If you change Python-only files: HUP or restart is sufficient.
- If you change Dockerfile, requirements, or system-level deps: rebuild image and recreate container.

## 4. Rapid dev mode (optional, for heavy iteration)

When iterating quickly (e.g., tuning OmniVoice behavior), swap gunicorn for uvicorn with --reload.

Example (run on dockermisc1, or script it):

- Stop existing container:
  - docker stop qwen3-tts && docker rm qwen3-tts

- Run in dev-reload mode (same mounts/env, uvicorn instead of gunicorn):
  - docker run -d \
      --name qwen3-tts \
      --memory=13g \
      -p 8318:8318 \
      -v /var/data/autopirate/qwen3-tts-new/voices:/voices \
      -v /var/data/autopirate/qwen3-tts-new/segments:/segments \
      -v /home/nick/projects/qwen3-tts-openvino/src:/app/src \
      -v /var/data/autopirate/qwen3-tts-new/reference/voice_A.wav:/voice/reference.wav \
      -v /var/data/autopirate/qwen3-tts-new/model:/root/.cache/huggingface/hub \
      -v /var/data/autopirate/qwen3-tts-new/ov:/ov \
      -e TTS_BACKEND=openvino \
      -e MODEL_SIZE=1.7B \
      -e LOW_RAM_MODE=1 \
      -e FRONTEND_ENABLED=1 \
      -e "REF_TEXT=Welcome to Rosies. What can I get for you today? You know, Im a good girl. You want me, dont you? I am on the menu too." \
      qwen3-tts-openvino:voice-design-accent-and-queueing \
      python -m uvicorn qwen3_tts.app:app \
        --host 0.0.0.0 --port 8318 --reload \
        --timeout-graceful-shutdown 300

Effect:
- Any change in /home/nick/projects/qwen3-tts-openvino/src triggers auto-reload inside ~1-2 seconds.
- Combine with git pull on dockermisc1 after pushing from local.

When done iterating, revert to normal gunicorn-based container command.

## 5. How future Claude sessions should use this

If you’re a new Claude session:

- Assume:
  - We are developing on voice-design-accent-and-queueing.
  - Running instance is dockermisc1:qwen3-tts (8318), using /app/src mounted from git-tracked repo.
- Default workflow:
  - Implement in this repo.
  - Commit + push.
  - Instruct user to (or assist with):
    - cd /home/nick/projects/qwen3-tts-openvino && git pull
    - docker exec qwen3-tts kill -HUP 1 (or docker restart qwen3-tts).
- Only propose heavier changes (image rebuilds, env changes) when necessary and confirm first.
