# Residual Risks

What four grilling rounds couldn't close. Ordered by blast radius.

## 1. Karaoke timing stack (`\kf` × WhisperX)

The selected subtitle style is the one most sensitive to alignment error,
and the only automated defense is the WhisperX confidence gate
(re-transcription self-eval was not selected). ±50 ms drift is visible.

- **Mitigation**: generator supports `\k` instant swap per run from day one —
  switching is one flag, zero timing-logic changes.
- **Early warning**: the benchmark slice is judged by eye for exactly this.

## 2. Vision support on the LLM endpoint (unproven)

Asset auto-tagging ([06](06-asset-registry.md)) requires the `/v1` endpoint
to accept image inputs. Many relays don't.

- **Mitigation**: probe on day one (same probe run as `json_schema`). If
  absent: hand-tag the seed pack, defer auto-tagging, or add a local vision
  model later.

## 3. Kokoro genre fit (unverified by ear)

Right size, right license — but whether its voices carry Reddit-narration
energy is a listening test, not a spec.

- **Mitigation**: 3-sample ear test before the first real video; voice
  choice is isolated from every downstream stage.

## 4. Single external dependency

The LLM endpoint sits between script and render. Down = pipeline halt.
Accepted consciously; no local fallback in v1.

- **Mitigation**: failure halts one video, corrupts nothing; stage-cached
  state resumes cleanly when the endpoint returns.

## 5. Channel-level platform risk

Self-recorded footage + real editing clears *video-level* reuse policy. The
remaining risk is *channel-level*: dozens of structurally identical videos
is what inauthentic-content enforcement pattern-matches.

- **Mitigation**: vary voice, game, and effect cadence across videos
  (decision #28); keep the human approval step real — channels die faster
  when approval becomes rubber-stamping.

## Accepted without mitigation

- **Software-encode speed** on unknown hardware — the benchmark gate exists
  precisely to answer this before it matters.
- **Meme licensing gray zone** — `source` field + per-asset human
  confirmation is the posture; absolute certainty is not available at any
  price in this genre.
