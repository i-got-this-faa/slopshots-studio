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
  stroke-width="2"
  stroke-linecap="square"
  stroke-linejoin="miter"
  aria-hidden="true"
  focusable="false"
>
  {#if name === 'check'}
    <path d="m5 12 4 4L19 6" />
  {:else if name === 'x'}
    <path d="m6 6 12 12M18 6 6 18" />
  {:else if name === 'refresh'}
    <path d="M20 11a8 8 0 0 0-14.8-4L3 10M3 5v5h5M4 13a8 8 0 0 0 14.8 4L21 14M21 19v-5h-5" />
  {:else if name === 'upload'}
    <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
  {:else if name === 'download'}
    <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
  {:else if name === 'external'}
    <path d="M14 5h5v5M19 5l-8 8M19 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h4" />
  {:else if name === 'arrow-right'}
    <path d="M5 12h14M13 6l6 6-6 6" />
  {:else if name === 'plus'}
    <path d="M12 5v14M5 12h14" />
  {:else if name === 'chevron-down'}
    <path d="m6 9 6 6 6-6" />
  {:else if name === 'film'}
    <rect x="3" y="4" width="18" height="16" />
    <path d="M7 4v16M17 4v16M3 9h4M17 9h4M3 15h4M17 15h4" />
  {:else if name === 'alert'}
    <path d="M12 4 21 20H3L12 4Z" />
    <path d="M12 10v4M12 17h.01" />
  {:else if name === 'clock'}
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  {:else}
    <rect x="4" y="4" width="16" height="16" />
  {/if}
</svg>
