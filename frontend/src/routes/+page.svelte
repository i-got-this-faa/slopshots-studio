<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import JobRow from '$lib/components/JobRow.svelte';
  import Pipeline from '$lib/components/Pipeline.svelte';
  import PreviewCard from '$lib/components/PreviewCard.svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import StatCard from '$lib/components/StatCard.svelte';
  import StatusPill from '$lib/components/StatusPill.svelte';
  import {
    ApiError,
    createJob,
    deriveMediaAssetId,
    decideJob,
    formatSeconds,
    getApiBaseUrl,
    getJob,
    getValidation,
    listJobs,
    loadDashboard,
    normalizeScript as normalizeScriptWithApi,
    runJobStage,
    saveRuntimeSettings,
    setApiBaseUrl,
    updateJob,
    uploadMedia,
    validationChecks
  } from '$lib/api';
  import { demoDashboard } from '$lib/demo-data';
  import type {
    Artifact,
    DashboardStats,
    HealthResponse,
    MediaSource,
    NormalizationResult,
    PlacementProposal,
    RuntimeSettings,
    StageName,
    VideoJob
  } from '$lib/types';

  type DataMode = 'checking' | 'live' | 'degraded' | 'demo' | 'stale';
  type JobFilter = 'all' | 'review' | 'running';
  type ToastTone = 'success' | 'error' | 'warning';

  const emptyStats: DashboardStats = {
    inFlight: 0,
    review: 0,
    averageRender: '—',
    passRate: '—'
  };

  let jobs: VideoJob[] = [];
  let stats = emptyStats;
  let settings: RuntimeSettings | null = null;
  let health: HealthResponse | null = null;
  let selectedJobId = '';
  let activeNav = 'overview';
  let sidebarCollapsed = false;
  let mobileNavOpen = false;
  let mobileMenuButton: HTMLButtonElement;
  let pendingDecision: 'approve' | 'reject' | 'revise' | null = null;
  let dataMode: DataMode = 'checking';
  let connectionError = '';
  let syncLabel = 'Connecting…';
  let initialLoading = true;
  let refreshing = false;
  let activePanel: 'editor' | 'artifacts' | 'settings' = 'editor';
  let jobFilter: JobFilter = 'all';
  const filterOrder: JobFilter[] = ['all', 'review', 'running'];
  let filterTabs: HTMLButtonElement[] = [];

  let scriptText = '';
  let scriptTitle = '';
  let intakeVoice = 'af_heart';
  let intakeSpeed = 1;
  let intakeKaraokeMode: 'kf' | 'k' = 'kf';
  let gameplayPath = '';
  let musicPath = '';
  let gameplaySelection = '';
  let musicSelection = '';
  let mediaSource: MediaSource = 'original';
  let mediaConfirmed = false;
  let placementText = '[]';
  let useOpenCodeZen = true;
  let intakeResult: NormalizationResult | null = null;

  let kokoroVoice = 'af_heart';
  let kokoroSpeed = 1;
  let whisperModel = 'small';
  let whisperLanguage = 'auto';
  let whisperDevice = 'cpu';
  let whisperComputeType = 'int8';
  let ffmpegBin = 'ffmpeg';
  let ffprobeBin = 'ffprobe';
  let alignmentThreshold = 0.6;
  let karaokeMode: 'kf' | 'k' = 'kf';
  let stageTimeout = 3600;

  let decisionComment = '';
  let apiBaseDraft = getApiBaseUrl();
  let actionBusy: string | null = null;
  let busyStage: StageName | null = null;
  let normalizeBusy = false;
  let mediaBusy = false;
  let mediaUploadBusy: 'gameplay' | 'music' | null = null;
  let settingsBusy = false;
  let selectedValidation: import('$lib/types').ValidationResult | null = null;
  let selectedValidationJobId = '';
  let lastError = '';
  let toastMessage = '';
  let toastTone: ToastTone = 'success';
  let toastTimer: ReturnType<typeof setTimeout> | undefined;
  let scriptFileInput: HTMLInputElement;
  let gameplayFileInput: HTMLInputElement;
  let musicFileInput: HTMLInputElement;

  let selectedJob: VideoJob | null = null;
  let displayedJob: VideoJob | null = null;
  let visibleJobs: VideoJob[] = [];
  let videoArtifact: Artifact | null = null;

  $: selectedJob = jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null;
  $: displayedJob = selectedJob && selectedValidationJobId === selectedJob.id && selectedValidation
    ? {
        ...selectedJob,
        validation: validationChecks(selectedValidation, selectedJob),
        duration:
          selectedValidation.measured_duration_s === null
            ? selectedJob.duration
            : formatSeconds(selectedValidation.measured_duration_s)
      }
    : selectedJob;
  $: visibleJobs = jobs.filter((job) =>
    jobFilter === 'review' ? job.status === 'review' : jobFilter === 'running' ? job.status === 'rendering' : true
  );
  $: videoArtifact = displayedJob?.artifacts.find((artifact) => artifact.type === 'video') ?? null;
  $: wordCount = scriptText.trim() ? scriptText.trim().split(/\s+/).length : 0;
  $: estimatedSeconds = Math.max(0, Math.round(wordCount / 2.5));
  $: lintTone = !scriptText.trim()
    ? 'notice'
    : intakeResult?.hard_fail
      ? 'warning'
      : wordCount < 130 || wordCount > 260
        ? 'warning'
        : wordCount < 150 || wordCount > 230
          ? 'notice'
          : 'good';
  $: lintLabel = !scriptText.trim()
    ? 'No script yet'
    : intakeResult?.hard_fail
      ? 'Backend intake rejected this script'
      : intakeResult && intakeResult.issues.length
        ? 'Backend intake returned review notes'
        : wordCount < 130
          ? 'Below hard minimum'
          : wordCount > 260
            ? 'Over hard maximum'
            : wordCount < 150 || wordCount > 230
              ? 'Outside target pace'
              : 'Within target pace';
  $: lintDetail = !scriptText.trim()
    ? 'Write or import a narration script here. Backend intake is authoritative once text exists.'
    : intakeResult?.issues[0]?.message
      ? intakeResult.issues[0].message
      : lintTone === 'good'
        ? 'Local estimate looks within target; backend is authoritative.'
        : 'Normalize or adjust before starting the pipeline.';
  $: mutationsEnabled = dataMode === 'live' || dataMode === 'degraded';
  $: connectionLabel =
    dataMode === 'checking'
      ? 'Connecting…'
      : dataMode === 'live'
        ? 'API connected'
        : dataMode === 'degraded'
          ? 'API connected · degraded'
          : dataMode === 'demo'
            ? 'Disconnected · sample data'
            : 'Disconnected · last live snapshot';
  $: connectionSync = dataMode === 'demo' ? 'No live sync' : syncLabel;
  $: validationStatus = selectedValidation
    ? selectedValidation.passed
      ? 'pass'
      : 'failed'
    : displayedJob?.validation.some((check) => check.state === 'fail')
      ? 'failed'
      : 'warn';
  $: validationLabel = selectedValidation
    ? selectedValidation.passed
      ? 'Passed'
      : 'Failed'
    : displayedJob?.validation.some((check) => check.state === 'fail')
      ? 'Failed'
      : 'Not verified';
  $: canApprove = Boolean(
    mutationsEnabled &&
      selectedJob?.backendStatus === 'awaiting_approval' &&
      selectedValidation?.passed === true &&
      !actionBusy
  );

  onMount(() => {
    const storedBaseUrl = window.localStorage.getItem('slopshots.apiBaseUrl');
    if (storedBaseUrl !== null) {
      apiBaseDraft = storedBaseUrl;
      setApiBaseUrl(storedBaseUrl);
    }

    void refreshDashboard();
    const pollTimer = window.setInterval(() => void refreshDashboard({ quiet: true }), 5000);
    window.addEventListener('keydown', handleGlobalKeydown);
    return () => {
      window.clearInterval(pollTimer);
      window.removeEventListener('keydown', handleGlobalKeydown);
      if (toastTimer) clearTimeout(toastTimer);
    };
  });

  async function refreshDashboard(options: { quiet?: boolean } = {}) {
    const hadLiveData = dataMode === 'live' || dataMode === 'degraded' || dataMode === 'stale';
    if (!options.quiet) {
      refreshing = true;
      if (dataMode === 'checking') initialLoading = true;
    }

    const previousSelectedId = selectedJobId;
    try {
      const response = await loadDashboard();
      jobs = response.jobs;
      stats = response.stats;
      health = response.health;
      applySettings(response.settings);
      dataMode = health?.status === 'degraded' ? 'degraded' : 'live';
      connectionError = '';
      lastError = '';
      syncLabel = `Synced ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;

      const nextSelectedId = jobs.some((job) => job.id === selectedJobId)
        ? selectedJobId
        : jobs[0]?.id ?? '';
      if (nextSelectedId !== previousSelectedId) {
        selectedValidation = null;
        selectedValidationJobId = '';
      }
      selectedJobId = nextSelectedId;
      const selectedFromResponse = jobs.find((job) => job.id === selectedJobId) ?? null;
      const hasValidationArtifact = Boolean(selectedFromResponse?.artifacts.some((artifact) => artifact.name === 'validation.json'));
      if (
        selectedJobId &&
        (nextSelectedId !== previousSelectedId ||
          selectedValidationJobId !== selectedJobId ||
          (hasValidationArtifact && selectedValidation === null))
      ) {
        await loadValidationForJob(selectedFromResponse);
      }
    } catch (error) {
      const message = errorMessage(error);
      connectionError = message;
      syncLabel = 'Sync failed';
      if (dataMode === 'checking' && !hadLiveData) {
        jobs = demoDashboard.jobs;
        stats = demoDashboard.stats;
        health = null;
        applySettings(demoDashboard.settings);
        dataMode = 'demo';
        if (!selectedJobId) selectedJobId = jobs[0]?.id ?? '';
        selectedValidation = null;
        selectedValidationJobId = '';
      } else if (hadLiveData) {
        dataMode = 'stale';
      }
      if (!options.quiet) showToast(`Backend unavailable: ${message}`, 'error');
    } finally {
      initialLoading = false;
      refreshing = false;
    }
  }

  async function loadValidationForJob(job: VideoJob | null) {
    if (!job) return;
    try {
      const result = await getValidation(job);
      selectedValidationJobId = job.id;
      selectedValidation = result;
      if (result) {
        const checks = validationChecks(result, job);
        jobs = jobs.map((item) =>
          item.id === job.id
            ? {
                ...item,
                validation: checks,
                duration:
                  result.measured_duration_s === null ? item.duration : formatSeconds(result.measured_duration_s)
              }
            : item
        );
      }
    } catch (error) {
      selectedValidationJobId = job.id;
      selectedValidation = null;
      if (dataMode === 'live' || dataMode === 'degraded') {
        lastError = `Could not read validation.json: ${errorMessage(error)}`;
      }
    }
  }

  async function refreshSelectedJob() {
    if (!selectedJobId || !mutationsEnabled) return;
    try {
      const latest = await getJob(selectedJobId);
      jobs = jobs.map((job) => (job.id === latest.id ? latest : job));
      gameplayPath = latest.gameplayFile;
      musicPath = latest.musicFile;
      await loadValidationForJob(latest);
      showToast('Selected job refreshed from the API.');
    } catch (error) {
      handleFailure(error, 'Refresh failed');
    }
  }

  function applySettings(next: RuntimeSettings) {
    settings = next;
    kokoroVoice = next.kokoro_voice;
    kokoroSpeed = next.kokoro_speed;
    intakeVoice = next.kokoro_voice;
    intakeSpeed = next.kokoro_speed;
    whisperModel = next.whisperx_model;
    whisperLanguage = next.whisperx_language ?? 'auto';
    whisperDevice = next.whisperx_device;
    whisperComputeType = next.whisperx_compute_type;
    ffmpegBin = next.ffmpeg_bin;
    ffprobeBin = next.ffprobe_bin;
    alignmentThreshold = next.alignment_confidence_threshold;
    karaokeMode = next.karaoke_mode;
    intakeKaraokeMode = next.karaoke_mode;
    stageTimeout = next.stage_timeout_s;
  }

  function showToast(message: string, tone: ToastTone = 'success') {
    toastMessage = message;
    toastTone = tone;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toastMessage = ''), 4200);
  }

  function selectJob(id: string) {
    selectedJobId = id;
    activePanel = 'editor';
    decisionComment = '';
    pendingDecision = null;
    selectedValidation = null;
    selectedValidationJobId = '';
    const job = jobs.find((item) => item.id === id);
    gameplayPath = job?.gameplayFile ?? '';
    musicPath = job?.musicFile ?? '';
    if (mutationsEnabled) void refreshSelectedJobSilently(id);
  }

  async function refreshSelectedJobSilently(id: string) {
    try {
      const latest = await getJob(id);
      jobs = jobs.map((job) => (job.id === latest.id ? latest : job));
      await loadValidationForJob(latest);
    } catch (error) {
      lastError = `Could not load job ${id}: ${errorMessage(error)}`;
    }
  }

  function scrollBehavior(): ScrollBehavior {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  }

  function navigate(id: string) {
    activeNav = id;
    const target =
      id === 'settings'
        ? 'settings-panel'
        : id === 'scripts'
          ? 'script-intake'
          : id === 'jobs'
            ? 'jobs-panel'
            : id === 'artifacts'
              ? 'artifacts-panel'
              : 'main-content';
    document.getElementById(target)?.scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
    if (mobileNavOpen) closeMobileNav();
  }

  function openNewJob() {
    activeNav = 'scripts';
    if (mobileNavOpen) closeMobileNav();
    document.getElementById('script-intake')?.scrollIntoView({ behavior: scrollBehavior(), block: 'center' });
    window.setTimeout(() => document.getElementById('script-title')?.focus(), 450);
  }

  function openMobileNav() {
    sidebarCollapsed = false;
    mobileNavOpen = true;
    window.setTimeout(() => document.querySelector<HTMLButtonElement>('#primary-nav-drawer .nav-item')?.focus(), 0);
  }
  function closeMobileNav() {
    if (!mobileNavOpen) return;
    mobileNavOpen = false;
    // Restore focus to the trigger once the drawer is out of the way.
    window.setTimeout(() => mobileMenuButton?.focus(), 0);
  }

  function toggleMobileNav() {
    if (mobileNavOpen) closeMobileNav();
    else openMobileNav();
  }

  function toggleSidebar() {
    if (window.innerWidth <= 700) {
      toggleMobileNav();
      return;
    }
    sidebarCollapsed = !sidebarCollapsed;
  }


  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && mobileNavOpen) {
      event.preventDefault();
      closeMobileNav();
    }
  }

  function requestDecision(action: 'approve' | 'reject' | 'revise') {
    if (actionBusy) return;
    if (action === 'approve' && !canApprove) {
      showToast('Approval requires a passing validation report from the backend.', 'warning');
      return;
    }
    if (selectedJob?.backendStatus !== 'awaiting_approval') {
      showToast('This job is no longer awaiting approval.', 'warning');
      return;
    }
    pendingDecision = action;
  }

  function confirmDecision() {
    if (!pendingDecision) return;
    if (selectedJob?.backendStatus !== 'awaiting_approval') {
      pendingDecision = null;
      showToast('This job is no longer awaiting approval.', 'warning');
      return;
    }
    const action = pendingDecision;
    pendingDecision = null;
    void decide(action);
  }

  function cancelDecision() {
    pendingDecision = null;
  }

  function selectFilter(filter: JobFilter) {
    jobFilter = filter;
  }

  function onFilterKeydown(event: KeyboardEvent, index: number) {
    const count = filterOrder.length;
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = (index + 1) % count;
    else if (event.key === 'ArrowLeft') next = (index - 1 + count) % count;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = count - 1;
    if (next === null) return;
    event.preventDefault();
    const targetFilter = filterOrder[next];
    jobFilter = targetFilter;
    filterTabs[next]?.focus();
  }

  function importScriptFile() {
    scriptFileInput?.click();
  }

  async function handleScriptFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      scriptText = await file.text();
      if (!scriptTitle.trim()) scriptTitle = file.name.replace(/\.txt$/i, '');
      intakeResult = null;
      showToast(`Imported ${file.name} into the editor.`);
    } catch (error) {
      showToast(`Could not read ${file.name}: ${errorMessage(error)}`, 'error');
    } finally {
      input.value = '';
    }
  }

  async function handleMediaFile(event: Event, kind: 'gameplay' | 'music') {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    if (!mutationsEnabled) {
      showToast('Connect to the backend before uploading media.', 'warning');
      input.value = '';
      return;
    }
    if (mediaUploadBusy) return;

    if (kind === 'gameplay') gameplaySelection = `Uploading ${file.name}…`;
    else musicSelection = `Uploading ${file.name}…`;
    mediaUploadBusy = kind;
    try {
      const asset = await uploadMedia(file, {
        assetId: deriveMediaAssetId(kind, file),
        kind,
        source: mediaSource,
        confirmed: mediaConfirmed,
        description: `${kind} uploaded from the operator dashboard`,
        tags: [kind]
      });
      if (kind === 'gameplay') {
        gameplayPath = asset.id;
        gameplaySelection = `Uploaded ${asset.filename} → ${asset.id}`;
      } else {
        musicPath = asset.id;
        musicSelection = `Uploaded ${asset.filename} → ${asset.id}`;
      }
      showToast(`${asset.filename} uploaded and registered as ${asset.id}.`);
    } catch (error) {
      if (kind === 'gameplay') gameplaySelection = `Upload failed: ${file.name}`;
      else musicSelection = `Upload failed: ${file.name}`;
      handleFailure(error, `${kind[0].toUpperCase()}${kind.slice(1)} upload failed`);
    } finally {
      mediaUploadBusy = null;
      input.value = '';
    }
  }

  function chooseMedia(kind: 'gameplay' | 'music') {
    if (kind === 'gameplay') gameplayFileInput?.click();
    else musicFileInput?.click();
  }

  async function normalizeScript() {
    if (!mutationsEnabled) {
      showToast('Connect to the backend before using intake normalization.', 'warning');
      return;
    }
    if (!scriptText.trim()) {
      showToast('Enter a script before normalizing it.', 'warning');
      return;
    }
    normalizeBusy = true;
    try {
      const result = await normalizeScriptWithApi(scriptText);
      intakeResult = result;
      scriptText = result.normalized;
      showToast(result.hard_fail ? 'Backend intake returned a hard-fail lint result.' : 'Script normalized by the backend.');
    } catch (error) {
      handleFailure(error, 'Normalization failed');
    } finally {
      normalizeBusy = false;
    }
  }

  async function startPipeline() {
    if (!mutationsEnabled) {
      showToast('Connect to the backend before creating a job.', 'warning');
      return;
    }
    if (!scriptTitle.trim() || !scriptText.trim()) {
      showToast('A title and script are required.', 'warning');
      return;
    }

    actionBusy = 'create';
    lastError = '';
    try {
      const response = await createJob({
        name: scriptTitle.trim(),
        script: scriptText,
        gameplayFile: gameplayPath.trim() || undefined,
        musicFile: musicPath.trim() || undefined,
        voice: intakeVoice,
        speed: Number(intakeSpeed),
        karaokeMode: intakeKaraokeMode
      });
      jobs = [response.job, ...jobs.filter((job) => job.id !== response.job.id)];
      selectedJobId = response.job.id;
      selectedValidation = null;
      selectedValidationJobId = '';
      intakeResult = response.intake;
      stats = {
        ...stats,
        inFlight: jobs.filter((job) => ['queued', 'rendering'].includes(job.status)).length
      };
      showToast(
        response.intake.hard_fail
          ? `Job ${response.job.id} was created, but backend intake rejected the script.`
          : `Job ${response.job.id} created and intake completed.`
      );
      void refreshDashboard({ quiet: true });
    } catch (error) {
      handleFailure(error, 'Job creation failed');
      if (error instanceof ApiError && error.jobId) void refreshDashboard({ quiet: true });
    } finally {
      actionBusy = null;
    }
  }

  function parsePlacements(): PlacementProposal[] | undefined {
    try {
      const parsed: unknown = JSON.parse(placementText || '[]');
      if (!Array.isArray(parsed)) throw new Error('placement proposals must be a JSON array');
      return parsed as PlacementProposal[];
    } catch (error) {
      showToast(`Placement JSON is invalid: ${errorMessage(error)}`, 'warning');
      return undefined;
    }
  }

  async function handleRunStage(stage: import('$lib/types').PipelineStage) {
    if (!selectedJob || !mutationsEnabled || busyStage || actionBusy) return;
    // Pass the provider choice through dependency runs too: timeline and
    // later stages may invoke the placement stage before they execute.
    const useProvider = useOpenCodeZen;
    const placements = useProvider ? undefined : parsePlacements();
    if (!useProvider && !placements) return;

    busyStage = stage.id;
    lastError = '';
    selectedValidation = null;
    selectedValidationJobId = '';
    try {
      const updated = await runJobStage(selectedJob.id, stage.id, {
        force: stage.state === 'complete',
        placements,
        useOpenCodeZen: useProvider,
        gameplayFile: gameplayPath.trim() || selectedJob.gameplayFile || undefined,
        musicFile: musicPath.trim() || selectedJob.musicFile || undefined
      });
      jobs = jobs.map((job) => (job.id === updated.id ? updated : job));
      await loadValidationForJob(updated);
      showToast(`${stage.name} finished according to the API.`);
    } catch (error) {
      handleFailure(error, `${stage.name} failed`);
      await refreshSelectedJobSilently(selectedJob.id);
    } finally {
      busyStage = null;
    }
  }

  async function registerMedia() {
    if (!selectedJob || !mutationsEnabled || mediaBusy) return;
    if (!gameplayPath.trim()) {
      showToast('A runner-readable gameplay path is required before timeline/render.', 'warning');
      return;
    }
    mediaBusy = true;
    try {
      const updated = await updateJob(selectedJob.id, {
        gameplay_file: gameplayPath.trim(),
        ...(musicPath.trim() ? { music_file: musicPath.trim() } : {})
      });
      jobs = jobs.map((job) => (job.id === updated.id ? updated : job));
      showToast('Media paths registered on the backend job.');
    } catch (error) {
      handleFailure(error, 'Media registration failed');
    } finally {
      mediaBusy = false;
    }
  }

  async function decide(action: 'approve' | 'reject' | 'revise') {
    if (!selectedJob || !mutationsEnabled || actionBusy) return;
    if (action === 'approve' && !canApprove) {
      showToast('Approval requires a passing validation report from the backend.', 'warning');
      return;
    }
    actionBusy = action;
    lastError = '';
    try {
      const updated = await decideJob(selectedJob.id, action, decisionComment);
      jobs = jobs.map((job) => (job.id === updated.id ? updated : job));
      selectedValidation = null;
      selectedValidationJobId = '';
      decisionComment = '';
      showToast(
        action === 'approve'
          ? 'Approval recorded by the backend.'
          : action === 'reject'
            ? 'Rejection recorded by the backend.'
            : 'Revision request recorded by the backend.'
      );
    } catch (error) {
      handleFailure(error, `${action} failed`);
    } finally {
      actionBusy = null;
      pendingDecision = null;
    }
  }

  async function saveSettings() {
    if (!settings || !mutationsEnabled || settingsBusy) return;
    settingsBusy = true;
    try {
      const saved = await saveRuntimeSettings({
        ffmpeg_bin: ffmpegBin.trim(),
        ffprobe_bin: ffprobeBin.trim(),
        kokoro_voice: kokoroVoice,
        kokoro_speed: Number(kokoroSpeed),
        whisperx_model: whisperModel.trim(),
        whisperx_device: whisperDevice.trim(),
        whisperx_compute_type: whisperComputeType.trim(),
        whisperx_language: whisperLanguage === 'auto' ? null : whisperLanguage,
        alignment_confidence_threshold: Number(alignmentThreshold),
        karaoke_mode: karaokeMode,
        stage_timeout_s: Number(stageTimeout)
      });
      applySettings(saved);
      showToast('Runtime settings saved by the backend.');
    } catch (error) {
      handleFailure(error, 'Settings save failed');
    } finally {
      settingsBusy = false;
    }
  }

  async function connectToApi() {
    setApiBaseUrl(apiBaseDraft);
    window.localStorage.setItem('slopshots.apiBaseUrl', apiBaseDraft.trim());
    dataMode = 'checking';
    connectionError = '';
    initialLoading = true;
    await refreshDashboard();
  }

  function handleFailure(error: unknown, context: string) {
    const message = `${context}: ${errorMessage(error)}`;
    lastError = message;
    showToast(message, 'error');
    if (!(error instanceof ApiError) || error.status === null || error.status >= 500) {
      if (dataMode === 'live' || dataMode === 'degraded') dataMode = 'stale';
      connectionError = errorMessage(error);
    }
  }

  function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : 'Unknown error';
  }

  function healthFor(key: string): 'complete' | 'failed' | 'pending' {
    if (!health) return 'pending';
    return health.integrations[key]?.available ? 'complete' : 'failed';
  }

  function healthLabel(key: string): string {
    if (!health) return 'Unknown';
    return health.integrations[key]?.available ? 'Ready' : 'Unavailable';
  }

  function healthSummary(): string {
    if (!health) return 'Health endpoint did not return integration details.';
    const unavailable = Object.values(health.integrations)
      .filter((integration) => !integration.available)
      .map((integration) => integration.dependency)
      .join(', ');
    return unavailable ? `Unavailable dependencies: ${unavailable}.` : 'All reported integrations are available.';
  }
</script>

<svelte:head>
  <title>SlopShots · Operator</title>
  <meta name="description" content="SlopShots video pipeline operator dashboard" />
</svelte:head>

<div class:mobile-nav-open={mobileNavOpen} class="app-shell">
  <a href="#main-content" class="skip-link">Skip to main content</a>
  <Sidebar
    active={activeNav}
    collapsed={sidebarCollapsed}
    mobileOpen={mobileNavOpen}
    jobCount={jobs.length}
    onNavigate={navigate}
    onToggle={toggleSidebar}
  />
  {#if mobileNavOpen}
    <button type="button" class="mobile-backdrop" aria-label="Close navigation" tabindex="-1" on:click={closeMobileNav}></button>
  {/if}

  <main class="main-shell" id="main-content" tabindex="-1" inert={mobileNavOpen}>
    <header class="topbar">
      <div class="topbar-context">
        <button type="button" bind:this={mobileMenuButton} class="mobile-menu icon-button" aria-label={mobileNavOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileNavOpen} aria-controls="primary-nav-drawer" on:click={toggleMobileNav}><Icon name="grid" size={18} /></button>
        <span class="crumb-muted">Production</span>
        <Icon name="chevron-right" size={14} />
        <span class="crumb-current">Operator dashboard</span>
      </div>
      <div class="topbar-actions">
        <span class:api-live={dataMode === 'live' || dataMode === 'degraded'} class:api-demo={dataMode === 'demo'} class:api-offline={dataMode === 'stale' || dataMode === 'checking'} class="api-status"><span class="api-status-dot"></span>{connectionLabel}</span>
        <span class="sync-label">{connectionSync}</span>
        <span class="topbar-divider"></span>
        <button type="button" class="icon-button subtle" aria-label="Refresh dashboard" disabled={refreshing} on:click={() => void refreshDashboard()}><Icon name="refresh" size={17} /></button>
        <span class="topbar-avatar">MK</span>
      </div>
    </header>

    <div class="content-wrap">
      <section class="page-heading">
        <div>
          <span class="eyebrow accent-eyebrow">SlopShots / control room</span>
          <h1>Keep the pipeline moving.</h1>
          <p>Intake, render, inspect, approve. Every state below comes from the runner.</p>
        </div>
        <div class="heading-actions">
          <input bind:this={scriptFileInput} class="sr-only" type="file" accept=".txt,text/plain" on:change={handleScriptFile} />
          <button type="button" class="button button-secondary" on:click={importScriptFile}><Icon name="upload" size={16} /> Import script</button>
          <button type="button" class="button button-primary" on:click={openNewJob}><Icon name="plus" size={17} /> New video job</button>
        </div>
      </section>

      {#if dataMode === 'demo' || dataMode === 'stale' || dataMode === 'degraded'}
        <div class:connection-banner-demo={dataMode === 'demo'} class:connection-banner-error={dataMode === 'stale'} class:connection-banner-warning={dataMode === 'degraded'} class="connection-banner" role="status">
          <span class="connection-banner-icon"><Icon name={dataMode === 'degraded' ? 'alert' : dataMode === 'demo' ? 'activity' : 'x'} size={15} /></span>
          <span>
            <strong>{dataMode === 'demo' ? 'Disconnected: sample data only.' : dataMode === 'stale' ? 'Connection lost: showing the last live snapshot.' : 'Backend is connected but degraded.'}</strong>
            {#if dataMode === 'demo'} {connectionError || 'Mutating actions and artifact links are disabled until the API connects.'}{:else if dataMode === 'degraded'} {healthSummary()}{:else} {connectionError || 'Retry to resume live updates.'}{/if}
          </span>
          <button type="button" class="button button-ghost compact" disabled={refreshing} on:click={() => void refreshDashboard()}>{refreshing ? 'Retrying…' : 'Retry connection'}</button>
        </div>
      {/if}

      {#if lastError && dataMode !== 'demo'}
        <div class="inline-error" role="alert"><Icon name="alert" size={14} /><span>{lastError}</span><button type="button" class="icon-button subtle" aria-label="Dismiss error" on:click={() => (lastError = '')}><Icon name="x" size={14} /></button></div>
      {/if}

      <section class="stats-grid" aria-label="Pipeline summary">
        <StatCard label="In flight" value={initialLoading && jobs.length === 0 ? '—' : stats.inFlight} change={dataMode === 'demo' ? 'Sample data' : stats.inFlight ? 'Live stage count' : 'No active stages'} icon="activity" changeTone={dataMode === 'demo' ? 'warning' : 'neutral'} />
        <StatCard label="Ready for review" value={initialLoading && jobs.length === 0 ? '—' : stats.review} change={stats.review ? 'Needs your eye' : 'No pending approvals'} icon="eye" changeTone={stats.review ? 'warning' : 'neutral'} />
        <StatCard label="Average render" value={stats.averageRender} change={dataMode === 'demo' ? 'Sample data' : 'From completed render stages'} icon="gauge" changeTone="neutral" />
        <StatCard label="Validation pass rate" value={stats.passRate} change={dataMode === 'demo' ? 'Sample data' : 'From validation stages'} icon="check-circle" changeTone={dataMode === 'demo' ? 'warning' : 'neutral'} />
      </section>

      <section class="top-panels">
        <article class="panel jobs-panel" id="jobs-panel">
          <div class="panel-heading">
            <div><span class="eyebrow">Production queue</span><h2>Video jobs <span class="heading-count">{jobs.length}</span></h2></div>
            <StatusPill status={dataMode === 'demo' ? 'offline' : dataMode === 'degraded' ? 'degraded' : dataMode === 'checking' ? 'unknown' : 'complete'} label={dataMode === 'demo' ? 'Sample only' : dataMode === 'checking' ? 'Loading' : dataMode === 'degraded' ? 'Degraded' : dataMode === 'stale' ? 'Snapshot' : 'Live'} />
          </div>
          <div class="job-tabs" role="tablist" aria-label="Job filters">
            <button type="button" id="job-filter-all" data-filter="all" bind:this={filterTabs[0]} class:tab-selected={jobFilter === 'all'} role="tab" aria-selected={jobFilter === 'all'} aria-controls="job-filter-panel" tabindex={jobFilter === 'all' ? 0 : -1} on:click={() => selectFilter('all')} on:keydown={(event) => onFilterKeydown(event, 0)}>All jobs <span>{jobs.length}</span></button>
            <button type="button" id="job-filter-review" data-filter="review" bind:this={filterTabs[1]} class:tab-selected={jobFilter === 'review'} role="tab" aria-selected={jobFilter === 'review'} aria-controls="job-filter-panel" tabindex={jobFilter === 'review' ? 0 : -1} on:click={() => selectFilter('review')} on:keydown={(event) => onFilterKeydown(event, 1)}>Needs review <span>{jobs.filter((job) => job.status === 'review').length}</span></button>
            <button type="button" id="job-filter-running" data-filter="running" bind:this={filterTabs[2]} class:tab-selected={jobFilter === 'running'} role="tab" aria-selected={jobFilter === 'running'} aria-controls="job-filter-panel" tabindex={jobFilter === 'running' ? 0 : -1} on:click={() => selectFilter('running')} on:keydown={(event) => onFilterKeydown(event, 2)}>Running <span>{jobs.filter((job) => job.status === 'rendering').length}</span></button>
          </div>
          <div class="job-tabpanel" id="job-filter-panel" role="tabpanel" tabindex="0" aria-labelledby={'job-filter-' + jobFilter}>
            <div class="job-list">
            {#if initialLoading && jobs.length === 0}
              <div class="empty-state"><span class="empty-state-spinner"></span><strong>Connecting to the pipeline…</strong><small>Waiting for /api/v1/jobs.</small></div>
            {:else if visibleJobs.length === 0}
              <div class="empty-state"><span class="empty-state-icon"><Icon name="film" size={18} /></span><strong>{jobs.length ? 'No jobs match this filter.' : 'No jobs returned by the API.'}</strong><small>{jobs.length ? 'Choose another queue filter.' : 'Create a job after the backend connection is ready.'}</small></div>
            {:else}
              {#each visibleJobs as job (job.id)}
                <JobRow {job} selected={displayedJob?.id === job.id} onSelect={selectJob} />
              {/each}
            {/if}
            </div>
          </div>
          <button type="button" class="panel-footer-link" disabled={jobs.length === 0} on:click={() => navigate('jobs')}><span>View queue</span><Icon name="arrow-right" size={15} /></button>
        </article>

        <article class="panel intake-panel" id="script-intake">
          <div class="panel-heading intake-heading">
            <div><span class="eyebrow">Stage 01 · intake</span><h2>Script editor</h2></div>
            <span class="editor-mode"><span class:editor-mode-dot={mutationsEnabled} class="editor-mode-dot"></span>{mutationsEnabled ? 'Backend intake ready' : 'Backend required'}</span>
          </div>
          <form on:submit|preventDefault={startPipeline}>
            <label class="field-label" for="script-title">Working title</label>
            <input id="script-title" class="text-input title-input" bind:value={scriptTitle} placeholder="Give this short a name" />
            <label class="field-label" for="script-body">Plain-text script <span>· no inline markup</span></label>
            <div class="script-editor-wrap">
              <div class="line-numbers" aria-hidden="true">{#each scriptText.split('\n') as _, index (index)}<span>{String(index + 1).padStart(2, '0')}</span>{/each}</div>
              <textarea id="script-body" bind:value={scriptText} on:input={() => (intakeResult = null)} spellcheck="true" aria-describedby="script-help" placeholder="Paste the narration script here..."></textarea>
            </div>
            <div class="editor-meta">
              <span>{wordCount} words <span class="meta-divider">·</span> ~{estimatedSeconds}s narration</span>
              <span id="script-help">Backend lint target 130–260 words</span>
            </div>
            <div class:lint-good={lintTone === 'good'} class:lint-notice={lintTone === 'notice'} class:lint-warning={lintTone === 'warning'} class="lint-row">
              <span class="lint-icon"><Icon name={!scriptText.trim() ? 'file' : lintTone === 'good' ? 'check' : 'alert'} size={14} /></span>
              <span><strong>{lintLabel}</strong> · {lintDetail}</span>
              <button type="button" class="text-button" disabled={normalizeBusy || !mutationsEnabled} on:click={() => void normalizeScript()}><Icon name="wand" size={14} /> {normalizeBusy ? 'Normalizing…' : 'Normalize via API'}</button>
            </div>
            <div class="intake-controls">
              <label class="select-field"><span class="field-label">Kokoro voice</span><span class="select-wrap"><select bind:value={intakeVoice} disabled={!settings || !mutationsEnabled}><option value="af_heart">af_heart · warm</option><option value="af_bella">af_bella · clear</option><option value="am_adam">am_adam · grounded</option></select><Icon name="chevron-down" size={14} /></span></label>
              <label class="select-field"><span class="field-label">Speed factor</span><span class="select-wrap"><select bind:value={intakeSpeed} disabled={!settings || !mutationsEnabled}><option value={0.96}>0.96× slower</option><option value={1}>1.00× natural</option><option value={1.02}>1.02× natural</option><option value={1.08}>1.08× faster</option></select><Icon name="chevron-down" size={14} /></span></label>
            </div>
            <div class="intake-controls">
              <label class="select-field"><span class="field-label">Karaoke mode</span><span class="select-wrap"><select bind:value={intakeKaraokeMode} disabled={!settings || !mutationsEnabled}><option value="kf">kf · progressive fill</option><option value="k">k · word highlight</option></select><Icon name="chevron-down" size={14} /></span><small class="field-note">kf fills captions progressively · k highlights word-by-word</small></label>
              <span class="field-note">Create performs the real <code>POST /api/v1/jobs</code> and intake call.</span>
            </div>
            <div class="media-fields">
              <div class="media-fields-heading"><span><strong>Upload or register media</strong><small>Uploads are stored by the backend; absolute runner paths remain supported.</small></span><Icon name="upload" size={15} /></div>
              <div class="media-upload-options">
                <label class="select-field"><span class="field-label">Media source</span><span class="select-wrap"><select bind:value={mediaSource} disabled={!mutationsEnabled || mediaUploadBusy !== null}><option value="original">Original</option><option value="licensed">Licensed</option><option value="community">Community</option></select><Icon name="chevron-down" size={14} /></span></label>
                <label class="media-confirm"><input type="checkbox" bind:checked={mediaConfirmed} disabled={!mutationsEnabled || mediaUploadBusy !== null} /> <span>I have permission to use these files</span></label>
              </div>
              <label class="field-label" for="new-gameplay-path">Gameplay asset ID or runner path <span>· required for timeline/render</span></label>
              <input id="new-gameplay-path" class="text-input" bind:value={gameplayPath} placeholder="uploads/gameplay/… or /absolute/path/to/gameplay.mp4" />
              <label class="field-label" for="new-music-path">Music asset ID or runner path <span>· optional</span></label>
              <input id="new-music-path" class="text-input" bind:value={musicPath} placeholder="uploads/music/… or /absolute/path/to/music.wav" />
              <div class="media-picker-row">
                <input bind:this={gameplayFileInput} class="sr-only" type="file" accept="video/*" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:change={(event) => void handleMediaFile(event, 'gameplay')} />
                <input bind:this={musicFileInput} class="sr-only" type="file" accept="audio/*" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:change={(event) => void handleMediaFile(event, 'music')} />
                <button type="button" class="text-button" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:click={() => chooseMedia('gameplay')}><Icon name="upload" size={13} /> {mediaUploadBusy === 'gameplay' ? 'Uploading gameplay…' : 'Upload gameplay file'}</button>
                <button type="button" class="text-button" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:click={() => chooseMedia('music')}><Icon name="upload" size={13} /> {mediaUploadBusy === 'music' ? 'Uploading music…' : 'Upload music file'}</button>
              </div>
              {#if gameplaySelection || musicSelection}<small class="field-note">{gameplaySelection || ''}{gameplaySelection && musicSelection ? ' · ' : ''}{musicSelection || ''}</small>{/if}
            </div>
            <button type="submit" class="button button-primary full-button" disabled={!mutationsEnabled || actionBusy === 'create' || !settings || mediaUploadBusy !== null}><Icon name="arrow-right" size={16} /> {actionBusy === 'create' ? 'Creating job…' : 'Create job & intake'} <span class="button-note">⌘ ↵</span></button>
          </form>
        </article>
      </section>

      {#if displayedJob}
        <section class="active-job-heading">
          <div>
            <span class="eyebrow accent-eyebrow">Selected job · {displayedJob.id}</span>
            <div class="active-job-title"><h2>{displayedJob.title}</h2><StatusPill status={displayedJob.status} label={displayedJob.statusLabel} /></div>
            <p>{displayedJob.slug} <span class="meta-divider">·</span> {displayedJob.scriptWords === null ? 'word count unavailable' : `${displayedJob.scriptWords} words`} <span class="meta-divider">·</span> updated {displayedJob.updated}</p>
          </div>
          <div class="approval-actions">
            <button type="button" class="button button-ghost" disabled={!mutationsEnabled || refreshing} on:click={() => void refreshSelectedJob()}><Icon name="refresh" size={15} /> Refresh status</button>
            <button type="button" class="button button-secondary" disabled={!mutationsEnabled || actionBusy !== null || displayedJob.backendStatus !== 'awaiting_approval'} on:click={() => requestDecision('revise')}><Icon name="x" size={15} /> Request revision</button>
            <button type="button" class="button button-secondary" disabled={!mutationsEnabled || actionBusy !== null || displayedJob.backendStatus !== 'awaiting_approval'} on:click={() => requestDecision('reject')}><Icon name="x" size={15} /> Reject</button>
            <button type="button" class="button button-approve" disabled={!canApprove} on:click={() => requestDecision('approve')}><Icon name="check" size={16} /> {actionBusy === 'approve' ? 'Approving…' : displayedJob.status === 'approved' ? 'Approved' : 'Approve final'}</button>
          </div>
          {#if pendingDecision}
            <div class="decision-confirmation" role="group" aria-labelledby="decision-confirmation-title">
              <div class="decision-confirmation-copy" aria-live="polite">
                <strong id="decision-confirmation-title">{pendingDecision === 'approve' ? 'Approve' : pendingDecision === 'reject' ? 'Reject' : 'Request revision'} {displayedJob.title}?</strong>
                <span>Review note {decisionComment.trim() ? `"${decisionComment.trim()}" will be sent with this action.` : 'is empty — confirm to send without a note.'} Only the confirm button calls the API.</span>
              </div>
              <div class="decision-confirmation-actions">
                <button type="button" class="decision-cancel" on:click={cancelDecision}>Cancel</button>
                <button type="button" class:decision-danger={pendingDecision !== 'approve'} class:decision-approve={pendingDecision === 'approve'} on:click={confirmDecision}>
                  {pendingDecision === 'approve' ? 'Confirm approval' : pendingDecision === 'reject' ? 'Confirm rejection' : 'Confirm revision request'}
                </button>
              </div>
            </div>
          {/if}
        </section>

        {#if displayedJob.backendStatus === 'awaiting_approval'}
          <div class="decision-row"><label class="field-label" for="decision-comment">Review note <span>· included with approval/rejection/revision</span></label><textarea id="decision-comment" class="review-comment" bind:value={decisionComment} maxlength="2000" placeholder="Add context for the next operator (optional for approval, useful for revision/rejection)."></textarea></div>
        {/if}

        <section class="detail-grid">
          <article class="panel pipeline-panel">
            <div class="panel-heading"><div><span class="eyebrow">Orchestration</span><h2>Pipeline stages</h2></div><span class="panel-kicker"><Icon name="activity" size={14} /> {displayedJob.progress}% complete</span></div>
            <Pipeline stages={displayedJob.stages} busyStage={busyStage} disabled={!mutationsEnabled || actionBusy !== null} onRun={handleRunStage} />
            <div class="stage-options">
              <label class="media-confirm"><input type="checkbox" bind:checked={useOpenCodeZen} disabled={!mutationsEnabled} /> <span>Generate placements with OpenCode Zen · DeepSeek V4 Flash Free</span></label>
              <label class="field-label" for="placement-proposals">Placement proposals <span>· manual fallback</span></label>
              <textarea id="placement-proposals" class="placement-input" bind:value={placementText} disabled={useOpenCodeZen} spellcheck="false" placeholder="[]"></textarea>
              <small>{useOpenCodeZen ? 'The placement stage calls the configured OpenCode Zen endpoint; the API key stays on the backend.' : 'Use [] when this job has no overlays. The backend validates proposal shape.'}</small>
            </div>
            <div class="pipeline-footer"><span><span class:running-dot={displayedJob.backendStatus === 'running'} class="running-dot"></span>{displayedJob.lastError ?? displayedJob.statusLabel}</span><button type="button" class="text-button" disabled={!mutationsEnabled} on:click={() => void refreshSelectedJob()}><Icon name="refresh" size={14} /> Poll now</button></div>
          </article>

          <article class="panel preview-panel">
            <div class="panel-heading"><div><span class="eyebrow">Artifact preview</span><h2>{displayedJob.status === 'approved' ? 'Final preview' : 'Rendered preview'}</h2></div><span class="preview-format">{videoArtifact?.meta ?? 'No video artifact'}</span></div>
            <PreviewCard title={displayedJob.status === 'approved' ? 'Final preview' : 'Rendered preview'} src={videoArtifact?.url || null} mediaType={videoArtifact?.meta ?? 'video/mp4'} accent={displayedJob.accent} posterLabel={dataMode === 'demo' ? 'Sample preview is not connected' : 'Run render to create final.mp4'} />
            <div class="preview-actions">
              {#if videoArtifact?.url}
                <a class="button button-secondary compact" href={videoArtifact.url} target="_blank" rel="noreferrer" download={videoArtifact.name}><Icon name="download" size={14} /> Download {videoArtifact.name}</a>
              {:else}
                <button type="button" class="button button-secondary compact" disabled><Icon name="download" size={14} /> Download unavailable</button>
              {/if}
            </div>
          </article>

          <article class="panel artifacts-panel" id="artifacts-panel">
            <div class="panel-heading"><div><span class="eyebrow">Stage outputs</span><h2>Artifacts <span class="heading-count">{displayedJob.artifacts.length}</span></h2></div><span class="panel-kicker">Links are API-backed</span></div>
            <div class="artifact-list">
              {#if displayedJob.artifacts.length === 0}
                <div class="empty-state compact-empty"><span class="empty-state-icon"><Icon name="layers" size={18} /></span><strong>No artifacts yet.</strong><small>Run a stage to create outputs.</small></div>
              {:else}
                {#each displayedJob.artifacts as artifact (artifact.name)}
                  <div class:artifact-unavailable={!artifact.url} class="artifact-row">
                    <span class:artifact-video={artifact.type === 'video'} class:artifact-audio={artifact.type === 'audio'} class:artifact-text={artifact.type === 'text'} class:artifact-data={artifact.type === 'data'} class:artifact-command={artifact.type === 'command'} class="artifact-icon"><Icon name={artifact.type === 'video' ? 'film' : artifact.type === 'audio' ? 'mic' : artifact.type === 'data' ? 'database' : artifact.type === 'command' ? 'terminal' : 'file'} size={15} /></span>
                    {#if artifact.url}
                      <a class="artifact-name artifact-link" href={artifact.url} target="_blank" rel="noreferrer" download={artifact.name}><strong>{artifact.name}</strong><small>{artifact.meta}</small></a>
                      <a class="icon-button subtle" href={artifact.url} target="_blank" rel="noreferrer" download={artifact.name} aria-label={`Download ${artifact.name}`}><Icon name="download" size={15} /></a>
                    {:else}
                      <span class="artifact-name"><strong>{artifact.name}</strong><small>{artifact.meta} · unavailable in sample mode</small></span>
                      <span class="artifact-size">—</span>
                    {/if}
                    {#if artifact.url}<span class="artifact-size">{artifact.size}</span>{/if}
                  </div>
                {/each}
              {/if}
            </div>
          </article>

          <article class="panel validation-panel">
            <div class="panel-heading"><div><span class="eyebrow">Automated gate</span><h2>Validation checks</h2></div><StatusPill status={validationStatus} label={validationLabel} /></div>
            <div class="validation-list">
              {#each displayedJob.validation as check (check.label)}
                <div class="validation-row"><span class:validation-pass={check.state === 'pass'} class:validation-warn={check.state === 'warn'} class:validation-fail={check.state === 'fail'} class="validation-mark"><Icon name={check.state === 'pass' ? 'check' : check.state === 'warn' ? 'alert' : 'x'} size={13} /></span><span>{check.label}</span><strong>{check.value}</strong></div>
              {/each}
            </div>
            <div class="eyeball-note"><Icon name="eye" size={14} /><span>{selectedValidation?.passed ? 'Backend validation passed; review the actual artifact before approval.' : 'Approval stays disabled until validation.json reports passed.'}</span></div>
          </article>

          <article class="panel media-panel" id="media-panel">
            <div class="panel-heading"><div><span class="eyebrow">Runner inputs</span><h2>Register media paths</h2></div><span class="panel-kicker">PATCH /api/v1/jobs/{displayedJob.id}</span></div>
            <label class="field-label" for="selected-gameplay-path">Gameplay asset ID or path <span>· backend host</span></label>
            <input id="selected-gameplay-path" class="text-input" bind:value={gameplayPath} placeholder="uploads/gameplay/… or /absolute/path/to/gameplay.mp4" />
            <label class="field-label" for="selected-music-path">Music asset ID or path <span>· optional</span></label>
            <input id="selected-music-path" class="text-input" bind:value={musicPath} placeholder="uploads/music/… or /absolute/path/to/music.wav" />
            <p class="media-disclaimer"><Icon name="database" size={14} /> Uploads use <code>POST /api/v1/media/upload</code>; manual absolute-path registration remains available for files already readable by the runner.</p>
            <button type="button" class="button button-secondary full-button" disabled={!mutationsEnabled || mediaBusy || !gameplayPath.trim()} on:click={() => void registerMedia()}><Icon name="database" size={14} /> {mediaBusy ? 'Registering…' : 'Register paths on backend'}</button>
          </article>
        </section>
      {:else if !initialLoading}
        <section class="panel no-selection"><span class="empty-state-icon"><Icon name="film" size={18} /></span><h2>Select a live job to inspect stages and artifacts.</h2><p>Create a job or refresh the queue after connecting to the API.</p></section>
      {/if}

      <section class="panel settings-panel" id="settings-panel">
        <div class="panel-heading settings-heading"><div><span class="eyebrow">Runtime configuration</span><h2>Engine settings</h2><p>These controls map directly to <code>PATCH /api/v1/settings</code>.</p></div><button type="button" class="button button-secondary compact" disabled={!mutationsEnabled || !settings || settingsBusy} on:click={() => void saveSettings()}><Icon name="check" size={14} /> {settingsBusy ? 'Saving…' : 'Save settings'}</button></div>
        {#if settings}
          <div class="settings-grid">
            <fieldset class="engine-card" disabled={!mutationsEnabled}>
              <legend><span class="engine-icon engine-kokoro"><Icon name="mic" size={16} /></span><span><strong>Kokoro</strong><small>Voice synthesis</small></span><StatusPill status={healthFor('kokoro')} label={healthLabel('kokoro')} /></legend>
              <label class="setting-field"><span>Voice</span><select bind:value={kokoroVoice}><option value="af_heart">af_heart · warm</option><option value="af_bella">af_bella · clear</option><option value="am_adam">am_adam · grounded</option></select></label>
              <label class="setting-field"><span>Speed factor <output>{Number(kokoroSpeed).toFixed(2)}×</output></span><input type="range" min="0.5" max="1.5" step="0.01" bind:value={kokoroSpeed} /></label>
              <div class="setting-meta"><span>Current backend default</span><strong>{settings.kokoro_voice}</strong></div>
            </fieldset>
            <fieldset class="engine-card" disabled={!mutationsEnabled}>
              <legend><span class="engine-icon engine-whisper"><Icon name="align" size={16} /></span><span><strong>WhisperX</strong><small>Word alignment</small></span><StatusPill status={healthFor('whisperx')} label={healthLabel('whisperx')} /></legend>
              <label class="setting-field"><span>Model</span><input class="text-input" bind:value={whisperModel} /></label>
              <label class="setting-field"><span>Language</span><select bind:value={whisperLanguage}><option value="auto">Auto detect</option><option value="en">English (en)</option><option value="es">Spanish (es)</option></select></label>
              <div class="settings-split"><div class="setting-meta"><span>Device</span><strong>{whisperDevice}</strong></div><div class="setting-meta"><span>Compute</span><strong>{whisperComputeType}</strong></div></div>
              <label class="setting-field"><span>Device</span><input class="text-input" bind:value={whisperDevice} /></label>
              <label class="setting-field"><span>Compute type</span><input class="text-input" bind:value={whisperComputeType} /></label>
            </fieldset>
            <fieldset class="engine-card" disabled={!mutationsEnabled}>
              <legend><span class="engine-icon engine-ffmpeg"><Icon name="film" size={16} /></span><span><strong>FFmpeg</strong><small>Render + validation</small></span><StatusPill status={healthFor('ffmpeg')} label={healthLabel('ffmpeg')} /></legend>
              <label class="setting-field"><span>FFmpeg executable</span><input class="text-input" bind:value={ffmpegBin} /></label>
              <label class="setting-field"><span>FFprobe executable</span><input class="text-input" bind:value={ffprobeBin} /></label>
              <label class="setting-field"><span>Stage timeout (seconds)</span><input class="text-input" type="number" min="1" step="1" bind:value={stageTimeout} /></label>
              <label class="setting-field"><span>Alignment confidence <output>{Number(alignmentThreshold).toFixed(2)}</output></span><input type="range" min="0" max="1" step="0.01" bind:value={alignmentThreshold} /></label>
              <label class="setting-field"><span>Karaoke mode</span><select bind:value={karaokeMode}><option value="kf">kf · progressive fill</option><option value="k">k · word highlight</option></select><small>kf fills captions progressively · k highlights word-by-word</small></label>
            </fieldset>
          </div>
        {:else}
          <div class="settings-empty"><span class="empty-state-icon"><Icon name="settings" size={18} /></span><strong>Settings are unavailable.</strong><small>Connect to the backend to read and save runtime configuration.</small></div>
        {/if}
        <form class="api-config" on:submit|preventDefault={connectToApi}>
          <span class="api-config-icon"><Icon name="activity" size={16} /></span>
          <span class="api-config-copy"><strong>Python API base URL</strong><small>Blank uses same-origin; this override persists in this browser.</small></span>
          <input class="text-input api-input" aria-label="Python API base URL" bind:value={apiBaseDraft} placeholder="http://127.0.0.1:8000" />
          <span class:api-config-connected={dataMode === 'live' || dataMode === 'degraded'} class:api-config-demo={dataMode === 'demo'} class:api-config-offline={dataMode === 'stale' || dataMode === 'checking'} class="api-config-state"><span></span>{dataMode === 'demo' ? 'Disconnected' : dataMode === 'stale' ? 'Retry required' : dataMode === 'checking' ? 'Checking…' : dataMode === 'degraded' ? 'Degraded' : 'Connected'}</span>
          <button type="submit" class="button button-secondary compact" disabled={refreshing}>{refreshing ? 'Checking…' : 'Connect'}</button>
        </form>
      </section>

      <footer class="app-footer"><span><span class:footer-pulse={dataMode === 'live' || dataMode === 'degraded'} class="footer-pulse"></span> {connectionLabel}</span><span>v0.1 operator <span class="meta-divider">·</span> manual publishing remains outside API v1</span></footer>
    </div>
  </main>
</div>

{#if toastMessage}
  <div class:toast-error={toastTone === 'error'} class:toast-warning={toastTone === 'warning'} class="toast" role="status"><span class="toast-check"><Icon name={toastTone === 'success' ? 'check' : toastTone === 'warning' ? 'alert' : 'x'} size={14} /></span>{toastMessage}<button type="button" class="toast-close" aria-label="Dismiss notification" on:click={() => (toastMessage = '')}><Icon name="x" size={14} /></button></div>
{/if}
