# 05 — Overlay Placement (LLM)

**Status: Decided (mechanism, contract), Selected pending re-confirm (anchors, collisions)**

## Mechanism

LLM proposes, human approves. The endpoint is OpenCode Zen's OpenAI-compatible
`/v1/chat/completions` API by default, using the free
`deepseek-v4-flash-free` model. The backend accepts provider-specific
`SLOPSHOTS_OPENCODE_ZEN_*` settings and retains the older
`SLOPSHOTS_OPENAI_*` names as aliases. This is the **only network dependency**
in the pipeline — endpoint down = no placements = halt.

## Output schema

One call per video. Response must validate against:

```json
{
  "placements": [
    {
      "asset_id": "meme/surprised-cat",
      "anchor_text": "forty-two",
      "zone": "top-left",
      "duration_s": 2.5,
      "animation": "pop-in",
      "reason": "reaction beat on the number reveal"
    }
  ]
}
```

- `asset_id` must exist in the registry ([06](06-asset-registry.md)) —
  validated post-response; invalid ids go to the repair retry.
- `zone` from the fixed layout enum ([07](07-timeline-edl.md)).
- `animation` from the fixed genre pack (`pop-in`, `bounce`, `slide-up`).

## Contract: probe, then repair

1. **Probe once** (first run, cached): does the endpoint honor
   `response_format: {"type": "json_schema", ...}`? Also probe **vision**
   support (needed by [06](06-asset-registry.md) ingest).
2. If yes → constrained output. If no → prompt-for-JSON.
3. Either way: validate with Pydantic/Zod. On failure, **one repair retry**
   with the validation errors fed back verbatim. Second failure → halt the
   video, report to the human. Never silently drop placements.

## Anchoring (pending re-confirm)

Placements carry **`anchor_text`**, not seconds. Resolution happens after
alignment: find the anchor phrase in `words.json`, set `t_start` to the
phrase midpoint. Regenerating the voiceover re-resolves all placements
automatically — absolute seconds would silently break on every re-TTS.

Ambiguous anchor (phrase occurs twice) → first occurrence, warn in approval.

## Collisions (pending re-confirm)

Deterministic layout zones; **one active overlay per zone**. A second
placement targeting an occupied zone at an overlapping time queues to the
zone's next free slot if `duration_s` allows, else drops with a logged
warning surfaced at approval. No second LLM pass in v1.

## Approval surface

Agent chat (video-use pattern): the human sees a compact table — asset,
anchor, resolved time, zone, duration, reason — and approves, edits, or
rejects before `timeline.json` is finalized. No GUI in v1.

## Prompt inputs

`script.normalized.txt` (with word indices), the registry's asset catalogue
(id + enum tags + description per asset), the zone list, and the placement
schema. Keep the catalogue under ~200 assets or the prompt dominates cost.
