<script lang="ts">
  import Icon from './Icon.svelte';
  import type { PipelineStage } from '$lib/types';

  export let stages: PipelineStage[] = [];
  export let busyStage: string | null = null;
  export let disabled = false;
  export let onRun: (stage: PipelineStage) => void = () => undefined;
</script>

<div class="pipeline-track" aria-label="Pipeline progress">
  {#each stages as stage, index}
    <div class:stage-complete={stage.state === 'complete'} class:stage-active={stage.state === 'active'} class:stage-error={stage.state === 'error'} class="pipeline-item" aria-current={stage.state === 'active' ? 'step' : undefined}>
      <div class="pipeline-node">
        {#if stage.state === 'complete'}
          <Icon name="check" size={13} />
        {:else if stage.state === 'error'}
          <Icon name="x" size={12} />
        {:else if stage.state === 'active'}
          <span class="pipeline-pulse"></span>
        {:else}
          <span class="pipeline-number">{index + 1}</span>
        {/if}
      </div>
      <div class="pipeline-copy">
        <strong>{stage.name}</strong>
        <span title={stage.detail}>{stage.cacheHit ? 'Cached' : stage.state === 'active' ? 'Running now' : stage.duration ?? stage.detail}</span>
        <button
          type="button"
          class="stage-run-button"
          disabled={disabled || busyStage !== null || stage.state === 'active'}
          on:click={() => onRun(stage)}
          aria-label={`${stage.state === 'complete' ? 'Re-run' : stage.state === 'error' ? 'Resume' : 'Run'} ${stage.name}`}
        >
          {busyStage === stage.id ? 'Working…' : stage.state === 'complete' ? 'Re-run' : stage.state === 'error' ? 'Resume' : 'Run'}
        </button>
      </div>
      {#if index < stages.length - 1}<span class="pipeline-connector" aria-hidden="true"></span>{/if}
    </div>
  {/each}
</div>
