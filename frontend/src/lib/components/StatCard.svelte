<script lang="ts">
  export let label: string;
  export let value: string | number;
  export let attention = false;
</script>

<div class="tally-cell" class:tally-attention={attention}>
  <span class="tally-label">{label}</span>
  <span class="tally-value">{value}</span>
</div>

