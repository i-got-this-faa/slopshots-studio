<script lang="ts">
  import Icon from './Icon.svelte';
  import StatusPill from './StatusPill.svelte';
  import type { VideoJob } from '$lib/types';

  export let job: VideoJob;
  export let selected = false;
  export let onSelect: (id: string) => void;
</script>

<button type="button" class:selected class="job-row" aria-pressed={selected} on:click={() => onSelect(job.id)}>
  <span class:accent-violet={job.accent === 'violet'} class:accent-cyan={job.accent === 'cyan'} class:accent-orange={job.accent === 'orange'} class:accent-pink={job.accent === 'pink'} class:accent-lime={job.accent === 'lime'} class="job-thumb" aria-hidden="true">
    <span class="thumb-scanline"></span>
    <span class="thumb-orb"></span>
    <span class="thumb-label">SS</span>
  </span>
  <span class="job-row-main">
    <span class="job-row-heading">
      <strong>{job.title}</strong>
      <span class="job-id">{job.id.slice(0, 8)}</span>
    </span>
    <span class="job-row-meta">
      <StatusPill status={job.status} label={job.statusLabel} />
      <span>{job.updated}</span>
      <span class="meta-divider">·</span>
      <span>{job.duration}</span>
    </span>
  </span>
  <span class="job-row-progress" aria-label={`${job.progress}% complete`}>
    <span class="mini-progress"><span style={`width: ${job.progress}%`}></span></span>
    <span>{job.progress}%</span>
  </span>
  <span class="job-row-chevron"><Icon name="chevron-right" size={16} /></span>
</button>
