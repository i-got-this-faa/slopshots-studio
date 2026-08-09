<script lang="ts">
  import Icon from './Icon.svelte';

  export let title = 'Artifact preview';
  export let src: string | null = null;
  export let posterLabel = 'No rendered video yet';
  export let mediaType = 'video/mp4';
  export let accent: 'violet' | 'cyan' | 'orange' | 'pink' | 'lime' = 'violet';
</script>

<div class:preview-violet={accent === 'violet'} class:preview-cyan={accent === 'cyan'} class:preview-orange={accent === 'orange'} class:preview-pink={accent === 'pink'} class:preview-lime={accent === 'lime'} class="preview-shell">
  <div class="preview-toolbar">
    <span class="preview-live"><span class:available={Boolean(src)} class="live-dot"></span> {title}</span>
    {#if src}<a class="icon-button subtle" href={src} target="_blank" rel="noreferrer" aria-label="Open preview in new window"><Icon name="external" size={15} /></a>{/if}
  </div>
  <div class:video-empty={!src} class="video-frame">
    {#if src}
      <video controls preload="metadata" playsinline aria-label={title}>
        <source src={src} type={mediaType} />
        Your browser cannot play this video artifact.
      </video>
    {:else}
      <span class="empty-preview-icon"><Icon name="film" size={24} /></span>
      <strong>{posterLabel}</strong>
      <small>Run the render stage to create <code>final.mp4</code>.</small>
    {/if}
  </div>
</div>
