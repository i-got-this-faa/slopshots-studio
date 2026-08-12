---
target: SlopShots operator dashboard
total_score: 29
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
timestamp: 2026-08-09T10-38-37Z
slug: frontend-src-routes-page-svelte
---
Method: dual-agent (A: DesignReview · B: EvidenceReview)

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|-----------|---:|---|
| 1 | Visibility of System Status | 4/4 | Strong checking/live/degraded/demo/stale states, sync timestamp, banners, toasts, and stage status. |
| 2 | Match System / Real World | 4/4 | Pipeline language, stage names, artifacts, validation, and operator copy match the actual media workflow. |
| 3 | User Control and Freedom | 2/4 | Same-page scrolling, dense controls, and immediate approval/rejection actions make recovery and navigation harder than necessary. |
| 4 | Consistency and Standards | 3/4 | Status pills and control styling are coherent, but the tablist and nav do not follow expected interaction semantics. |
| 5 | Error Prevention | 3/4 | Approval is validation-gated and demo/stale modes disable mutations; destructive decisions still have no confirmation. |
| 6 | Recognition Rather Than Recall | 3/4 | Labels and pipeline stages are visible, but tiny helper copy and duplicated connection state increase interpretation effort. |
| 7 | Flexibility and Efficiency | 3/4 | Refresh, polling, stage reruns, and New video job focus help power users; no keyboard shortcuts or efficient mode separation. |
| 8 | Aesthetic and Minimalist Design | 2/4 | Cohesive dark control-room styling, but one very long page carries too many unrelated jobs at once. |
| 9 | Error Recovery | 3/4 | Errors expose banners/toasts and retry paths; recovery is less clear for individual fields and destructive actions. |
| 10 | Help and Documentation | 2/4 | Pipeline docs is a dead button and the dashboard offers no contextual guidance for terms such as kf/karaoke modes. |
| **Total** |  | **29/40** | **Solid but not polished** |

## Design Specificity Verdict

### LLM assessment

This feels authored for SlopShots rather than a generic admin panel in its mechanism: the 8-stage orchestration track, API-backed artifact language, validation-gated approval, and honest sample/disconnected states are specific and useful. The visual language is a cohesive dark control-room system with a consistent status vocabulary. The main missed opportunity is structural: authoring, monitoring, review, artifacts, and raw engine configuration are all presented as one long scroll, so the product's specific workflow is buried inside a familiar dashboard frame. The design is product-specific in its data and states, but not yet specific enough in how an operator moves through time-sensitive work.

### Deterministic scan

The target-scoped detector command `node /home/radhey/.claude/skills/impeccable/scripts/detect.mjs --json frontend/src/routes/+page.svelte` returned `[]` with exit status 0. No primary or advisory findings were reported for this `.svelte` target, and there are no false positives to dismiss. The scan does not inspect the global styling in `frontend/src/app.css` because the component has no `<style>` block. Browser overlay evidence was unavailable: no browser-automation runtime was exposed, so no fresh tab, mutable injection, or `[Human]` overlay could be created. A live HTTP probe confirmed the SSR shell at `http://127.0.0.1:5173/`, but it cannot prove hydrated layout or viewport behavior.

## Overall Impression

The dashboard has a serious, credible operating-system feel and unusually good state honesty for an early tool. It tells the operator when the backend is disconnected, what is safe to do, and why approval is blocked. But the page asks a single surface to be a queue, editor, orchestration console, review desk, artifact browser, and settings admin. The biggest opportunity is to make the operator's next decision dominant: separate the operating modes, raise the type scale, and make navigation/action risk explicit.

## Cognitive Load Assessment

### Checklist failures

- One very long page carries the entire product: script editor, queue, selected-job detail, artifacts, validation, media registration, and engine settings have no mode separation.
- `activeNav` only drives `scrollIntoView`; the nav labels imply destinations, but the user remains in the same dense context.
- Base text is 13px, with 8–13px pills, eyebrows, metadata, and helper copy in muted grays. The operator must zoom or closely read nearly every control.
- Connection state is repeated across the topbar, sync label, banner, queue pill, engine health pills, footer, and API config state. This is reassuring once, noisy seven times.
- A blank script starts with a "Below hard minimum" warning before the user has entered anything, which makes the empty state feel like an error.

### Decision points with more than four options

- Approval row: Refresh status, Request revision, Reject, and Approve final, with two irreversible actions adjacent.
- Pipeline: eight stages, each with Run/Re-run/Resume controls.
- Create-job form: title, script, voice, speed, karaoke mode, media source, permission, gameplay path, music path, and two upload actions before one CTA.
- Engine settings: roughly fifteen controls spread across Kokoro, WhisperX, and FFmpeg cards.

## Emotional Journey

- **Onset:** "Keep the pipeline moving" and "control room" create a clear mission and momentum.
- **Middle:** Scanning becomes workmanlike but dense as stats, queue, editor, and settings compete for attention.
- **Peak:** The approval moment is the strongest part. Validation must pass, the artifact should be reviewed, and demo/stale modes cannot mutate data. This is excellent reassurance at the highest-stakes point.
- **End:** The page ends on engine settings and a footer rather than a completion state. The emotional peak sits mid-page, and the scroll has no deliberate close.

## What's Working

1. **System status is unusually legible.** The `checking/live/degraded/demo/stale` state machine is surfaced in banners, pills, timestamps, and disabled controls instead of being hidden behind a spinner.
2. **Approval safety is real, not decorative.** `canApprove` requires a live-capable mode, an awaiting-approval job, a passing backend validation result, and no active action. The copy tells the operator to inspect the actual artifact.
3. **The visual/status system is coherent and honest.** The 8-stage pipeline, canonical status pills, sample-only artifact labels, and API-backed language form a consistent product grammar.

## Priority Issues

### [P0] Mobile navigation drawer opens over the first viewport

- **What:** `sidebarCollapsed` defaults to `false` in `frontend/src/routes/+page.svelte`. At `max-width: 700px`, `.sidebar` is fixed and translated to `translateX(0)` unless it has `.sidebar-collapsed` (`frontend/src/app.css:2044-2057`).
- **Why it matters:** A phone visitor starts with a full navigation drawer covering the dashboard. The content, focus order, and primary action are obscured before the user has done anything.
- **Fix:** Default the drawer closed on narrow screens, add a backdrop and Escape-to-close behavior, and move focus to the first navigation item only when the drawer opens. Preserve the desktop collapse behavior.
- **Suggested command:** `/impeccable adapt`

### [P1] Operator text is too small and too low-contrast

- **What:** The global base is 13px; eyebrows are 9px; pills, tabs, metadata, and helper text fall to 8–10px. Muted tokens such as `#555d6d`, `#626a7b`, and `#8d93a4` carry important instructions.
- **Why it matters:** Monitoring a pipeline is a glance task. The current type scale turns status, timestamps, stage detail, and recovery instructions into fine print, increasing fatigue and error risk.
- **Fix:** Establish an operator type scale with a 14–15px reading minimum, 11–12px metadata minimum, stronger contrast for action-adjacent copy, and fewer all-caps eyebrows. Keep compact labels compact only where they are genuinely secondary.
- **Suggested command:** `/impeccable typeset`

### [P1] Navigation advertises destinations that are only scroll anchors, including a dead Artifacts path

- **What:** `Sidebar.svelte` presents Overview, Video jobs, Scripts, Artifacts, and Engine settings. `navigate()` maps only settings, scripts, and jobs; the Artifacts item falls through to `overview-top`. The Pipeline docs button at `Sidebar.svelte:54` has no click handler.
- **Why it matters:** Operators build a mental map from the sidebar. A click that silently returns to Overview, or a docs control that does nothing, breaks trust and makes the long page feel less navigable.
- **Fix:** Either convert these into real route/view boundaries, or label them explicitly as page sections and map every item to a valid anchor. Wire Pipeline docs to an actual help surface or remove the affordance until it exists.
- **Suggested command:** `/impeccable clarify`

### [P2] Irreversible review decisions fire without confirmation

- **What:** `decide()` immediately posts approve, reject, or revise actions from adjacent buttons in `frontend/src/routes/+page.svelte:560-586`. Only approval has a validation gate; reject and revision have no second-step confirmation.
- **Why it matters:** A fast operator can click Reject while aiming for Approve, especially with small adjacent controls. The backend records the action immediately and the UI only offers a toast afterward.
- **Fix:** Add an inline confirmation step or native dialog with the job title, decision, and review note; visually separate destructive Reject from Approve and keep the high-confidence path primary.
- **Suggested command:** `/impeccable harden`

### [P2] Queue tabs and motion lack complete accessibility affordances

- **What:** The three buttons use `role="tab"` and `aria-selected` but do not expose `aria-controls`, a tabpanel, or arrow-key roving behavior. There is no skip link, no focus management for the mobile drawer, and pulse/smooth-scroll animation has no `prefers-reduced-motion` guard.
- **Why it matters:** Keyboard users cannot use the queue filter as a conventional tablist, and motion-sensitive users receive no reduced-motion path. Mobile focus can remain behind the drawer.
- **Fix:** Implement the tab pattern fully or use ordinary filter buttons; add a skip link and drawer focus management; gate pulse, smooth scrolling, and transitions behind `prefers-reduced-motion: reduce`.
- **Suggested command:** `/impeccable audit`

## Persona Red Flags

**Alex (Power User):** To approve a reviewed job, Alex must navigate down the same long page from queue to job detail. The approval row is far from the small 247px preview (`app.css:1430`), Approve is one of four similar-weight actions, and there is no keyboard shortcut or fast review mode. Queue filtering also cannot be arrow-key navigated as a standard tablist.

**Jordan (First-Timer):** The New video job action correctly scrolls to the editor and focuses the title (`+page.svelte:357-361`). After that, Jordan faces roughly ten decisions, unexplained `kf` versus `k` karaoke modes, a permission checkbox that can be missed, and a blank-form warning that says "Below hard minimum" before any content exists. When disconnected, the form mostly says "Backend required" instead of guiding a staged setup.

**Riley (Keyboard/Accessibility):** Riley encounters icon-only collapsed navigation, 8–9px low-contrast labels, no skip link, incomplete tab semantics, and no Escape/focus model for the mobile drawer. The status/error system is strong, but the recovery path is not keyboard-complete.

## Minor Observations

- The live dot in the preview styling can read as offline rather than live.
- WhisperX shows Device and Compute as read-only metadata and then immediately repeats them as editable text inputs, creating conflicting affordances.
- `content-wrap` can grow to 1470px, making the monitoring surface unusually wide on large screens.
- At <=420px, the topbar refresh icon is hidden without an obvious replacement action.

## Questions to Consider

- Why is "Approve final" a single action inside an authoring-and-operations page instead of a distinct review mode?
- If the sidebar names five destinations, should they become real views, or should the interface commit to being one scrollable control room?
- Is 8px type serving the operator, or is it preserving a visual density that the task does not need?
- Would the approval peak be safer if the preview and validation gate shared one focused review surface?
- Why does the journey end on engine settings rather than a clear completion or next-job state?
