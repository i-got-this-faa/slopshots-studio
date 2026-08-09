<script lang="ts">
  import Icon from './Icon.svelte';

  export let label: string;
  export let value: string | number;
  export let change: string;
  export let changeTone: 'good' | 'neutral' | 'warning' = 'good';
  export let icon: string;
</script>

<article class="stat-card">
  <div class="stat-card-top">
    <span class="eyebrow">{label}</span>
    <span class="stat-icon"><Icon name={icon} size={16} /></span>
  </div>
  <div class="stat-value">{value}</div>
  <div class:change-good={changeTone === 'good'} class:change-neutral={changeTone === 'neutral'} class:change-warning={changeTone === 'warning'} class="stat-change">
    {#if changeTone === 'good'}<Icon name="arrow-up" size={13} />{/if}
    {change}
  </div>
</article>
