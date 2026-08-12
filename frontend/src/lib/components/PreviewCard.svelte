<script lang="ts">
  import Icon from './Icon.svelte';

  export let title = 'Artifact preview';
  export let src: string | null = null;
  export let posterLabel = 'No rendered video yet';
  export let mediaType = 'video/mp4';
</script>

<div class="monitor">
  <div class="monitor-bar">
    <span>{title}</span>
    {#if src}
      <a class="text-btn" href={src} target="_blank" rel="noreferrer">Open <Icon name="external" size={12} /></a>
    {/if}
  </div>
  <div class="monitor-screen">
    {#if src}
      <video controls preload="metadata" playsinline aria-label={title}>
        <source {src} type={mediaType} />
        Your browser cannot play this video artifact.
      </video>
    {:else}
      <div class="monitor-empty">
        <Icon name="film" size={26} />
        <strong>{posterLabel}</strong>
        <small>Run the render stage to create <code>final.mp4</code>.</small>
      </div>
    {/if}
  </div>
</div>
