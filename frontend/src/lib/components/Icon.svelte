<script lang="ts">
  export let name: string;
  export let size = 18;
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.8"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
  focusable="false"
>
  {#if name === 'grid'}
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  {:else if name === 'layers'}
    <path d="m12 3 9 4.8-9 4.8-9-4.8L12 3Z" />
    <path d="m3 12 9 4.8 9-4.8" />
    <path d="m3 16.2 9 4.8 9-4.8" />
  {:else if name === 'script'}
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
    <path d="M14 2v6h6M8 13h8M8 17h5" />
  {:else if name === 'film'}
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M7 4v16M17 4v16M3 9h4M17 9h4M3 15h4M17 15h4" />
  {:else if name === 'check'}
    <path d="m5 12 4 4L19 6" />
  {:else if name === 'check-circle'}
    <circle cx="12" cy="12" r="9" />
    <path d="m8 12 2.6 2.6L16.5 9" />
  {:else if name === 'settings'}
    <path d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z" />
    <path d="m19.4 15 .1.1a1.8 1.8 0 0 1-2.5 2.5l-.1-.1a1.8 1.8 0 0 0-3.1 1.3v.2a1.8 1.8 0 0 1-3.6 0v-.2a1.8 1.8 0 0 0-3.1-1.3l-.1.1a1.8 1.8 0 1 1-2.5-2.5l.1-.1a1.8 1.8 0 0 0-1.3-3.1h-.2a1.8 1.8 0 0 1 0-3.6h.2a1.8 1.8 0 0 0 1.3-3.1l-.1-.1a1.8 1.8 0 1 1 2.5-2.5l.1.1a1.8 1.8 0 0 0 3.1-1.3v-.2a1.8 1.8 0 0 1 3.6 0v.2a1.8 1.8 0 0 0 3.1 1.3l.1-.1a1.8 1.8 0 1 1 2.5 2.5l-.1.1a1.8 1.8 0 0 0 1.3 3.1h.2a1.8 1.8 0 0 1 0 3.6h-.2a1.8 1.8 0 0 0-1.3 3.1Z" transform="scale(.84) translate(2.3 2.3)" />
  {:else if name === 'help'}
    <circle cx="12" cy="12" r="9" />
    <path d="M9.6 9a2.5 2.5 0 1 1 4.5 1.5c-.8 1.1-2.1 1.3-2.1 2.8M12 17h.01" />
  {:else if name === 'search'}
    <circle cx="10.8" cy="10.8" r="6.8" />
    <path d="m16 16 4.5 4.5" />
  {:else if name === 'bell'}
    <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
  {:else if name === 'plus'}
    <path d="M12 5v14M5 12h14" />
  {:else if name === 'more'}
    <circle cx="5" cy="12" r="1" fill="currentColor" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
    <circle cx="19" cy="12" r="1" fill="currentColor" />
  {:else if name === 'clock'}
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  {:else if name === 'play'}
    <path d="m9 6 9 6-9 6V6Z" fill="currentColor" stroke="none" />
  {:else if name === 'pause'}
    <path d="M8 6v12M16 6v12" stroke-width="2.5" />
  {:else if name === 'arrow-up'}
    <path d="M12 19V5M6 11l6-6 6 6" />
  {:else if name === 'arrow-right'}
    <path d="M5 12h14M13 6l6 6-6 6" />
  {:else if name === 'wand'}
    <path d="m15 4 5 5M4 20 16.8 7.2M7 4v3M5.5 5.5h3M19 15v3M17.5 16.5h3" />
  {:else if name === 'download'}
    <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
  {:else if name === 'external'}
    <path d="M14 5h5v5M19 5l-8 8M19 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h4" />
  {:else if name === 'chevron-down'}
    <path d="m6 9 6 6 6-6" />
  {:else if name === 'chevron-right'}
    <path d="m9 6 6 6-6 6" />
  {:else if name === 'chevron-left'}
    <path d="m15 6-6 6 6 6" />
  {:else if name === 'sliders'}
    <path d="M4 6h16M4 12h16M4 18h16M8 4v4M15 10v4M11 16v4" />
  {:else if name === 'activity'}
    <path d="M3 12h4l2.5-7 5 14 2.5-7H21" />
  {:else if name === 'terminal'}
    <path d="m5 7 4 5-4 5M12 17h7" />
  {:else if name === 'refresh'}
    <path d="M20 11a8 8 0 0 0-14.8-4L3 10M3 5v5h5M4 13a8 8 0 0 0 14.8 4L21 14M21 19v-5h-5" />
  {:else if name === 'x'}
    <path d="m6 6 12 12M18 6 6 18" />
  {:else if name === 'upload'}
    <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
  {:else if name === 'alert'}
    <path d="M12 4 21 20H3L12 4Z" />
    <path d="M12 10v4M12 17h.01" />
  {:else if name === 'circle'}
    <circle cx="12" cy="12" r="8" />
  {:else if name === 'gauge'}
    <path d="M4.8 16a8 8 0 1 1 14.4 0" />
    <path d="m12 12 4-4M5 20h14" />
  {:else if name === 'mic'}
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
  {:else if name === 'align'}
    <path d="M4 6h16M4 12h12M4 18h8" />
  {:else if name === 'sparkle'}
    <path d="m12 3 1.3 5.7L19 10l-5.7 1.3L12 17l-1.3-5.7L5 10l5.7-1.3L12 3ZM19 16l.6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6L19 16Z" />
  {:else if name === 'file'}
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
    <path d="M14 2v6h6" />
  {:else if name === 'eye'}
    <path d="M2.5 12s3.3-6 9.5-6 9.5 6 9.5 6-3.3 6-9.5 6-9.5-6-9.5-6Z" />
    <circle cx="12" cy="12" r="2.5" />
  {:else if name === 'send'}
    <path d="m21 3-7.2 18-3.4-7.4L3 10.2 21 3Z" />
    <path d="M10.4 13.6 21 3" />
  {:else if name === 'database'}
    <ellipse cx="12" cy="5" rx="7" ry="3" />
    <path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" />
  {:else}
    <circle cx="12" cy="12" r="8" />
  {/if}
</svg>
