# 06 — Asset Registry

**Status: Decided (auto-tag ingest), Selected pending re-confirm (fixed enum + seed pack)**

## Layout

```
assets/
  registry.yml          # generated + human-confirmed manifest
  meme/
    surprised-cat.png
    surprised-cat.yml   # optional per-asset overrides
  reaction/
    ...
```

## Manifest entry

```yaml
- id: meme/surprised-cat
  file: meme/surprised-cat.png
  tags: [surprise, reaction]        # MUST come from the enum below
  emotion: surprise                 # single primary emotion, enum
  subjects: [cat]                   # free-ish, but linted against known list
  description: "wide-eyed cat, mouth open"   # read by the placement LLM
  aspect: "1:1"
  anchor_zone: top-left             # preferred zone; placement may override
  source: original                  # original | licensed | community
  confirmed: true                   # human approved the auto-tag
```

## Taxonomy (pending re-confirm: fixed enum + seed pack)

Closed vocabularies, versioned in `taxonomy.yml`. Free-form vision tags are
the known failure mode (*tag soup*: `funny`, `reaction`, `surprised-face`,
`shocked` — the placement LLM can't match against an uncontrolled
vocabulary).

- `emotion`: ~12 values (surprise, anger, joy, disgust, fear, sadness, smug,
  confusion, hype, cringe, suspense, neutral)
- `tags`: ~40 values, extended only by human edit of `taxonomy.yml`
- Vision model must choose from the enum; out-of-enum output = validation
  error at ingest, retry once, else queue for manual tagging.

**Seed pack:** 50–100 hand-tagged assets before the first real video, so
early scripts have coverage and the vision model has in-context examples.

## Ingest flow

1. Drop images into `assets/inbox/`.
2. Ingest job sends each to the vision-capable LLM: enum-constrained tags +
  one-line description. (Requires the endpoint to accept image inputs —
  **probe this**; if no vision, ingest is manual until a local vision model
  is added.)
3. Human confirms in the approval chat (`confirmed: true`).
4. Asset becomes referenceable by [05](05-overlay-placement.md).

## Rights

`source` field is mandatory. `original` (self-made) and `licensed` are
publishable by default; `community` (meme culture gray zone) ships only with
human confirmation per asset — which the approval step already provides.

## Failure modes

| Failure | Detection | Fix |
|---------|-----------|-----|
| Out-of-enum tag | Ingest validation | Repair retry, else manual |
| Placement references missing asset | Placement validation ([05](05-overlay-placement.md)) | Repair retry with registry diff |
| Registry growth > ~200 assets | Prompt size audit | Split catalogue by script genre; pass relevant slice |
