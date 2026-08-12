<script lang="ts">
  export let status: string;
  export let label: string | undefined = undefined;

  const defaultLabels: Record<string, string> = {
    rendering: 'Rendering',
    review: 'Ready for review',
    queued: 'Queued',
    approved: 'Approved',
    rejected: 'Rejected',
    completed: 'Completed',
    failed: 'Needs attention',
    active: 'Running',
    complete: 'Complete',
    pending: 'Pending',
    pass: 'Pass',
    warn: 'Review',
    unknown: 'Unknown',
    degraded: 'Degraded',
    offline: 'Offline'
  };

  $: displayLabel = label ?? defaultLabels[status] ?? status;
  $: toneClass =
    status === 'rendering' || status === 'active'
      ? 'status-running'
      : status === 'review'
        ? 'status-review'
        : status === 'queued'
          ? 'status-queued'
          : status === 'approved' || status === 'completed'
            ? 'status-approved'
            : status === 'rejected' || status === 'failed' || status === 'offline'
              ? 'status-rejected'
              : status === 'complete' || status === 'pass'
                ? 'status-pass'
                : status === 'warn' || status === 'degraded'
                  ? 'status-warn'
                  : 'status-pending';
  $: running = status === 'rendering' || status === 'active';
</script>

<span class={`status-chip ${toneClass}`} class:status-blink={running}>
  {displayLabel}
</span>

