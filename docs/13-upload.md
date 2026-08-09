# 13 — Upload

**Status: Decided (manual for v1)**

## v1: manual

The human downloads `final.mp4` and posts it. Zero API/quota/auth work while
output quality stabilizes. Metadata is still machine-assisted: the LLM
drafts title / description / hashtags from `script.normalized.txt` at
approval time; the human pastes and edits.

## Why not automated yet — the quota wall

- **YouTube Data API v3**: an upload costs **1600 quota units**; the default
  daily allotment is **10,000** → **~6 uploads/day**. A quota increase
  requires an app audit. Fine for one channel, a hard ceiling for a farm.
- **Instagram Graph API**: Business/Creator account only; two-step async
  flow (create container → poll status → publish). Rate limits per account.
- **TikTok Content Posting API**: requires an *approved* app; unaudited apps
  post as private/SELF_ONLY. Approval is a real process, not a formality.

## v2 shape (when manual hurts)

```
upload.py --platform youtube videos/2026-08-07-my-story/
```

- OAuth refresh tokens per platform/account, stored in `~/.config/slopshots/`,
  refreshed lazily; revocation mid-queue = pause that platform, never crash.
- **Idempotency**: `uploads.json` in the video dir records platform video
  IDs. Retry = check for an existing ID first; never double-post.
- Order: YouTube first (simplest real API), Instagram second, TikTok last
  (approval-gated).

## Metadata strategy (v1 and v2)

| Field | Source |
|-------|--------|
| Title | LLM from script; ≤ 60 chars; no clickbait policy violations |
| Description | LLM; first 100 chars carry the hook (Shorts shows little) |
| Hashtags | 3–5, platform-tuned (#shorts on YT; fewer, broader on IG) |
| Schedule | Manual — consistent daily time beats tooling at this scale |

## Platform policy note

60–90 s vertical uploads are Shorts/Reels natively (Shorts accepts up to
3 min). Content-ID-claimed music is the main silent-restriction trap — the
licensed library ([09](09-audio-music.md)) exists to keep this a non-event.
