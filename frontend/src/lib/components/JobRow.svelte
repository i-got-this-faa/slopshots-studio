<script lang="ts">
  import StatusPill from './StatusPill.svelte';
  import type { VideoJob } from '$lib/types';

  export let job: VideoJob;
  export let index: number;
  export let selected = false;
  export let onSelect: (id: string) => void;

  $: doneStages = job.stages.filter((stage) => stage.state === 'complete').length;
</script>

<button type="button" class="cue-row" aria-pressed={selected} on:click={() => onSelect(job.id)}>
  <span class="cue-no" aria-hidden="true">{String(index).padStart(2, '0')}</span>
  <span class="cue-main">
    <span class="cue-title">{job.title}</span>
    <span class="cue-sub">{job.id.slice(0, 8)} · {job.slug}</span>
  </span>
  <span><StatusPill status={job.status} label={job.statusLabel} /></span>
  <span class="stage-ticks" aria-label={`${doneStages} of ${job.stages.length} stages complete`}>
    {#each job.stages as stage (stage.id)}
      <span
        class="tick"
        class:tick-complete={stage.state === 'complete' && !stage.cacheHit}
        class:tick-cached={stage.state === 'complete' && stage.cacheHit}
        class:tick-active={stage.state === 'active'}
        class:tick-error={stage.state === 'error'}
        title={`${stage.name}: ${stage.state}${stage.cacheHit ? ' · cached' : ''}`}
      ></span>
    {/each}
  </span>
  <span class="cue-mono cue-dur">{job.duration}</span>
  <span class="cue-mono cue-updated">{job.updated}</span>
</button>

