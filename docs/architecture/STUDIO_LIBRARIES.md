# Studio libraries (voices, segments, projects)

Persona Forge persists user content with a "no database" pattern: bind-mounted
host directories, one subdirectory per item, a `meta.json` plus audio file(s),
and strict ID regexes that double as path-traversal defense. Three libraries
interlock: segments (locked-in audition takes) feed the stitch pipeline, stitch
results are saved as voices, and projects are name/description tags that group
voices and segments.

## Voice library

- Module: `src/persona_forge/voice_library.py`.
- Container path: `/voices` (`VOICE_LIBRARY_DIR`; compose binds the host's
  `${VOICE_LIBRARY_PATH:-./data/voices}`).
- Layout: `voices/<voice_id>/` with a master reference (`original.wav`,
  legacy `reference.wav`), a `current_wav` symlink to the active audio,
  `meta.json`, and optional `variants.json` + variant WAVs.
- IDs: `vd_<12hex>`; variants are lineage-preserving sub-IDs
  `vd_<parent_hex>.<slug>` (slug is a strict allowlist) for prosody-adjusted
  takes (`prosody_<slug>.wav`). Promoting a variant via
  `set_active_variant()` repoints the `current_wav` symlink (reset to
  `original.wav` with no argument).
- Used by `/generate` and `/v1/audio/speech` (via `voice_id`) and by the
  frontend voice library page. Endpoint shapes: `api/HTTP_API_REFERENCE.md`
  (Voice library section). Design→library lifecycle:
  `dev/architecture/voice_design.md`.

## Segment library

- Module: `src/persona_forge/segment_library.py`.
- Container path: `/segments` (`SEGMENT_LIBRARY_DIR`; compose binds the host's
  `${SEGMENT_LIBRARY_PATH:-./data/segments}`).
- Layout: `segments/<segment_id>/clip.wav` + `meta.json`; IDs are
  `seg_<12hex>`.
- A segment is one locked-in OmniVoice audition candidate (via
  `POST /omnivoice/segments`). `meta.json` keeps the full generation lineage:
  `text`, `instruct` (also parsed into `tags` on comma), `engine`,
  `accent_id`, `sample_rate`, `language`, `seed`, `num_step`, `speed`,
  `guidance_scale`, `diverse_candidates`, `postprocess_output`,
  `duration_target`, `candidate_id`, `job_id`, `whisper_transcript`,
  `match_score`, `duration_sec`, `feature_tags`, plus
  `project_id`/`project_name` and `created_at`.
- Segments are the durable inputs of the stitch pipeline; ephemeral
  `candidate_id`s from an audition job are cleared on the next audition and
  vanish on restart.

## Projects (Accent Design Projects)

- Module: `src/persona_forge/project_library.py`.
- A project is just a name/description tag: a `proj_<12hex>` registry entry
  in `projects.json` stored inside the voice library directory, so it rides
  the existing voice-library bind mount — no new volume.
- Membership is derived, never duplicated: voices and segments each carry
  their own `project_id`/`project_name` fields (set via
  `voice_library.set_voice_project` / `segment_library.set_segment_project`,
  exposed as `POST /voices/<id>/project` and
  `POST /omnivoice/segments/<id>/project`). Listing a project's contents
  scans those `meta.json` files.
- Deleting a project removes only the registry entry — its voices and segments
  are untouched and simply fall back to "Ungrouped" once their `project_id`
  no longer resolves to a live project.
- Endpoints: `GET /projects`, `POST /projects`, `PATCH /projects/<id>`
  (rename), `DELETE /projects/<id>`.

## Invariants

- The ID regexes (`vd_`/`seg_`/`proj_` + 12 hex, plus the variant pattern) are
  the path-traversal defense for IDs that travel straight into filesystem
  paths — keep them strict.
- No database, no migrations: schema evolution is additive `meta.json` fields,
  and readers must tolerate missing/legacy fields.
- Ephemeral state (audition candidates, VoiceDesign previews) is in-memory
  only; anything a user should keep goes through one of these libraries.
