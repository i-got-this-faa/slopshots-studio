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
</script>

<span class:status-review={status === 'review'} class:status-rendering={status === 'rendering'} class:status-queued={status === 'queued'} class:status-approved={status === 'approved' || status === 'completed'} class:status-failed={status === 'failed' || status === 'rejected' || status === 'offline'} class:status-active={status === 'active'} class:status-complete={status === 'complete'} class:status-pending={status === 'pending' || status === 'unknown'} class:status-pass={status === 'pass'} class:status-warn={status === 'warn' || status === 'degraded'} class="status-pill">
  <span class="status-dot" aria-hidden="true"></span>
  {displayLabel}
</span>
