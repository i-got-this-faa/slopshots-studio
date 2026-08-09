<script lang="ts">
  import Icon from './Icon.svelte';

  export let active = 'overview';
  export let collapsed = false;
  export let jobCount = 0;
  export let onNavigate: (id: string) => void;
  export let onToggle: () => void;

  const navItems = [
    { id: 'overview', label: 'Overview', icon: 'grid' },
    { id: 'jobs', label: 'Video jobs', icon: 'film' },
    { id: 'scripts', label: 'Scripts', icon: 'script' },
    { id: 'artifacts', label: 'Artifacts', icon: 'layers' }
  ];
</script>

<aside class:sidebar-collapsed={collapsed} class="sidebar">
  <div class="brand-row">
    <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
    {#if !collapsed}<span class="brand-wordmark">slop<span>shots</span></span>{/if}
    <button type="button" class="sidebar-toggle icon-button" aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} on:click={onToggle}>
      <Icon name={collapsed ? 'chevron-right' : 'chevron-left'} size={15} />
    </button>
  </div>

  {#if !collapsed}<div class="workspace-switcher"><span class="workspace-avatar">O</span><span class="workspace-copy"><strong>Operator</strong><small>Production workspace</small></span><Icon name="chevron-down" size={14} /></div>{/if}

  <nav class="primary-nav" aria-label="Primary navigation">
    <span class="nav-section-label">Workspace</span>
    {#each navItems as item}
      <button type="button" class:nav-active={active === item.id} class="nav-item" aria-current={active === item.id ? 'page' : undefined} on:click={() => onNavigate(item.id)}>
        <Icon name={item.icon} size={18} />
        {#if !collapsed}<span>{item.label}</span>{/if}
        {#if item.id === 'jobs' && !collapsed}<span class="nav-count">{jobCount}</span>{/if}
        {#if collapsed}<span class="sr-only">{item.label}</span>{/if}
      </button>
    {/each}
    <span class="nav-section-label">System</span>
    <button type="button" class:nav-active={active === 'settings'} class="nav-item" aria-current={active === 'settings' ? 'page' : undefined} on:click={() => onNavigate('settings')}>
      <Icon name="settings" size={18} />
      {#if !collapsed}<span>Engine settings</span>{/if}
      {#if collapsed}<span class="sr-only">Engine settings</span>{/if}
    </button>
  </nav>

  <div class="sidebar-bottom">
    {#if !collapsed}
      <div class="storage-meter">
        <div class="storage-head"><span>Local storage</span><span>—</span></div>
        <div class="storage-track storage-track-unknown"><span></span></div>
        <small>Usage is not reported by API v1</small>
      </div>
      <button type="button" class="help-row"><span class="help-icon"><Icon name="help" size={15} /></span><span>Pipeline docs</span><span class="shortcut">⌘ /</span></button>
    {/if}
    <div class="profile-row">
      <span class="profile-avatar">MK</span>
      {#if !collapsed}<span class="profile-copy"><strong>Marin K.</strong><small>Admin operator</small></span><button type="button" class="icon-button subtle" aria-label="Open account menu"><Icon name="more" size={16} /></button>{/if}
    </div>
  </div>
</aside>
