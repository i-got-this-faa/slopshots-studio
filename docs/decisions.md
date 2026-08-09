# Decision Table

Every architectural fork, its resolution, and its epistemic status.
Status legend in [README.md](README.md#status-legend).

| # | Area | Decision | Status | Notes |
|---|------|----------|--------|-------|
| 1 | Compute strategy | Benchmark all stages before committing | Decided | See [14](14-benchmark-gate.md) |
| 2 | Overlay intelligence | LLM proposes, human approves | Decided | Approval surface = agent chat (video-use pattern) |
| 3 | Composition engine | Generated FFmpeg filtergraphs from JSON timeline | Decided | No MoviePy/Remotion render path |
| 4 | Footage | Self-recorded gameplay library | Decided | Cleanest rights; see [10](10-gameplay-library.md) |
| 5 | Duration target | 60–90 seconds | Decided | Shorts allow ≤3 min vertical; genre norm is ≤90s |
| 6 | Upload v1 | Manual | Decided | API automation deferred; see [13](13-upload.md) |
| 7 | TTS | Kokoro 82M, local CPU, Apache-2.0 | Decided | Ear-test gate remains; see [02](02-tts-kokoro.md) |
| 8 | Word timestamps | WhisperX forced alignment vs normalized script | Decided | Local TTS emits no usable word boundaries |
| 9 | LLM | OpenCode Zen OpenAI-compatible `/v1/chat/completions`; DeepSeek V4 Flash Free default | Decided | Only non-local dependency; API key stays server-side |
| 10 | LLM output safety | Probe `json_schema`; fallback = validate + repair retry | Decided | Pydantic/Zod schema; one repair round-trip |
| 11 | Asset ingest | LLM/vision auto-tag on ingest | Decided | Vision support on endpoint unproven — probe required |
| 12 | Effects | Fixed genre pack (zoom punch, shake, flash/fade, overlay pop) | Decided | Bounded params; no general keyframes in v1 |
| 13 | Music | Licensed library + sidechain duck | Decided | See [09](09-audio-music.md) |
| 14 | Reframe | Crop-aware recording (capture centered/vertical) | Decided | A 9:16 full-height crop of 16:9 keeps ~32% of the frame |
| 15 | Validation | Full automated gate + human eyeball | Decided | See [11](11-validation.md) |
| 16 | Orchestration | Stage-cached artifacts, resume from last good stage | Decided | See [12](12-orchestration-state.md) |
| 17 | Core pattern | video-use style: transcript → EDL → FFmpeg → self-eval | Decided | Approval in agent chat; no GUI timeline in v1 |
| 18 | Karaoke style | ASS `\kf` smooth sweep | **Selected (pending re-confirm)** | `\k` instant swap is the one-line fallback |
| 19 | Timing QA | WhisperX per-word confidence gate; flagged segments spot-checked | **Selected (pending re-confirm)** | Re-transcription self-eval was the declined alternative |
| 20 | Tag taxonomy | Fixed enum + 50–100 hand-tagged seed assets | **Selected (pending re-confirm)** | Prevents tag soup from free-form vision tags |
| 21 | Placement anchors | Word/phrase anchors resolved via `words.json` | **Selected (pending re-confirm)** | Survives voice regeneration; absolute seconds do not |
| 22 | Collision handling | Deterministic layout zones; conflicts queue/drop with logged warning | **Selected (pending re-confirm)** | No second LLM pass in v1 |
| 23 | Benchmark gate | 10s end-to-end prototype, every stage timed, target < 10 min/video | **Selected (pending re-confirm)** | See [14](14-benchmark-gate.md) |
| 24 | Script normalization | Normalize before TTS; align against normalized text | Recommendation | Makes transcript == audio by construction |
| 25 | Script length lint | 150–230 words ≈ 60–90s at genre pace | Recommendation | Lint at intake; Kokoro speed factor gives ±10% |
| 26 | Subtitle font | Montserrat ExtraBold (OFL) | Recommendation | Commercially safe; stroke 6–8px for gameplay contrast |
| 27 | Audio fades | 30 ms fades at every audio cut | Recommendation | Borrowed from video-use production rules |
| 28 | Channel variation | Vary voice/game/effect cadence across videos | Recommendation | Mitigates inauthentic-content pattern-matching |

## Single points of failure

- **LLM endpoint** (#9): the only network dependency between script and
  render. Endpoint down = no placements = pipeline halt. Accepted risk; no
  local fallback in v1.
- **WhisperX timing accuracy** (#8, #18): the `\kf` sweep exposes ±50 ms
  errors. The confidence gate (#19) is the only automated defense.
