<script lang="ts">
  import type { PipelineStage } from '$lib/types';

  export let stages: PipelineStage[] = [];
  export let busyStage: string | null = null;
  export let disabled = false;
  export let onRun: (stage: PipelineStage) => void = () => undefined;

  const statusWord = (stage: PipelineStage): string => {
    if (busyStage === stage.id) return 'WORKING…';
    if (stage.state === 'active') return 'RUNNING';
    if (stage.state === 'error') return 'FAILED';
    if (stage.state === 'complete') return stage.cacheHit ? 'CACHED' : 'DONE';
    return 'PENDING';
  };

  const statusTone = (stage: PipelineStage): string => {
    if (busyStage === stage.id || stage.state === 'active') return 'status-running';
    if (stage.state === 'error') return 'status-rejected';
    if (stage.state === 'complete') return 'status-pass';
    return 'status-pending';
  };
</script>

<div class="stage-ledger" role="list" aria-label="Pipeline stages">
  {#each stages as stage, index (stage.id)}
    <div
      class="stage-row"
      class:stage-active={stage.state === 'active'}
      class:stage-error={stage.state === 'error'}
      role="listitem"
    >
      <span class="stage-no" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <span class="stage-name">{stage.name}<small>{stage.duration ?? stage.detail}</small></span>
      <span class={`cue-mono ${statusTone(stage)}`}>{statusWord(stage)}</span>
      <button
        type="button"
        class="btn btn-compact stage-run"
        disabled={disabled || busyStage !== null || stage.state === 'active'}
        on:click={() => onRun(stage)}
        aria-label={`${stage.state === 'complete' ? 'Re-run' : stage.state === 'error' ? 'Resume' : 'Run'} ${stage.name}`}
      >
        {busyStage === stage.id ? 'Working…' : stage.state === 'complete' ? 'Re-run' : stage.state === 'error' ? 'Resume' : 'Run'}
      </button>
    </div>
  {/each}
</div>
