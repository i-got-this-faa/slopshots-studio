<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import JobRow from '$lib/components/JobRow.svelte';
  import Pipeline from '$lib/components/Pipeline.svelte';
  import PreviewCard from '$lib/components/PreviewCard.svelte';
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
  let mobileMenuButton: HTMLButtonElement | undefined;
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

<a class="skip-link" href="#main-content">Skip to content</a>

<div class="sheet-wrap">
  <header class="masthead">
    <div class="wordmark-block">
      <span class="wordmark-square" aria-hidden="true">SS</span>
      <span class="wordmark-copy">
        <strong>SlopShots</strong>
        <small>Spotting sheet · script → final.mp4</small>
      </span>
    </div>

    <div class="masthead-meta">
      <span class="meta-cell">SHEET <strong>{new Date().toISOString().slice(0, 10)}</strong></span>
      <span class="meta-cell">SYNC <strong>{connectionSync}</strong></span>
      <span class={`stamp ${dataMode === 'live' ? 'stamp-live' : dataMode === 'checking' ? 'stamp-checking' : dataMode === 'degraded' || dataMode === 'demo' ? 'stamp-demo' : 'stamp-off'}`}>{connectionLabel}</span>
    </div>

    <div class="masthead-actions">
      <button type="button" class="icon-btn" aria-label="Refresh dashboard" disabled={refreshing} on:click={() => void refreshDashboard()}><Icon name="refresh" size={16} /></button>
      <button type="button" class="btn btn-solid" on:click={openNewJob}><Icon name="plus" size={14} /> New cue</button>
    </div>
  </header>

  {#if dataMode === 'demo'}
    <div class="notice-row notice-warn" role="status">
      <span class="notice-mark" aria-hidden="true"></span>
      <span class="notice-copy"><strong>Sample data.</strong> No backend connected — set <code>VITE_API_BASE_URL</code> or connect from Session setup. Mutations are disabled.</span>
      <button type="button" class="btn btn-compact btn-amber-outline" on:click={() => navigate('settings')}>Connect backend</button>
    </div>
  {:else if dataMode === 'stale'}
    <div class="notice-row notice-error" role="alert">
      <span class="notice-mark" aria-hidden="true"></span>
      <span class="notice-copy"><strong>Disconnected.</strong> Showing the last live snapshot; mutations are disabled until the backend returns.</span>
      <button type="button" class="btn btn-compact btn-cue-outline" disabled={refreshing} on:click={() => void refreshDashboard()}>Retry</button>
    </div>
  {:else if dataMode === 'degraded'}
    <div class="notice-row notice-warn" role="status">
      <span class="notice-mark" aria-hidden="true"></span>
      <span class="notice-copy"><strong>Connected — degraded.</strong> {healthSummary()}</span>
    </div>
  {/if}

  {#if connectionError && (dataMode === 'live' || dataMode === 'stale')}
    <div class="error-line" role="alert">{connectionError}</div>
  {/if}

  <nav class="sheet-tabs" aria-label="Sheet sections">
    <button type="button" class="sheet-tab" aria-pressed={activeNav !== 'scripts' && activeNav !== 'settings'} on:click={() => navigate('overview')}>
      <span class="tab-index" aria-hidden="true">01</span>Queue{#if jobs.length > 0}<span class="tab-count">{jobs.length}</span>{/if}
    </button>
    <button type="button" class="sheet-tab" aria-pressed={activeNav === 'scripts'} on:click={() => navigate('scripts')}>
      <span class="tab-index" aria-hidden="true">02</span>New cue
    </button>
    <button type="button" class="sheet-tab" aria-pressed={activeNav === 'settings'} on:click={() => navigate('settings')}>
      <span class="tab-index" aria-hidden="true">03</span>Session setup
    </button>
  </nav>

  <main id="main-content">
    {#if activeNav !== 'scripts' && activeNav !== 'settings'}
      <section aria-label="Queue summary">
        <div class="tally-strip">
          <StatCard label="In flight" value={initialLoading && jobs.length === 0 ? '—' : stats.inFlight} />
          <StatCard label="Ready for review" value={initialLoading && jobs.length === 0 ? '—' : stats.review} attention={stats.review > 0} />
          <StatCard label="Average render" value={stats.averageRender} />
          <StatCard label="Validation pass rate" value={stats.passRate} />
        </div>
      </section>

      <div class="queue-bar">
        <h2 class="section-title"><span class="section-no" aria-hidden="true">SEC 01</span>Cue queue</h2>
        <div class="filter-group" aria-label="Filter cues">
          {#each filterOrder as filter, index (filter)}
            <button
              type="button"
              bind:this={filterTabs[index]}
              class="filter-btn"
              aria-pressed={jobFilter === filter}
              tabindex={jobFilter === filter ? 0 : -1}
              on:click={() => selectFilter(filter)}
              on:keydown={(event) => onFilterKeydown(event, index)}
            >{filter === 'all' ? `All · ${jobs.length}` : filter === 'review' ? 'Review' : 'Running'}</button>
          {/each}
        </div>
      </div>

      <div class="cue-table" id="queue-list">
        {#if visibleJobs.length > 0}
          <div class="cue-head" aria-hidden="true">
            <span>№</span><span>Cue</span><span>Status</span><span>Stages</span><span class="head-dur">Dur</span><span class="head-updated">Updated</span>
          </div>
          <div>
            {#each visibleJobs as job, index (job.id)}
              <JobRow {job} index={index + 1} selected={displayedJob?.id === job.id} onSelect={selectJob} />
            {/each}
          </div>
        {:else if initialLoading && jobs.length === 0}
          <div class="empty-rule"><strong>Reading the sheet…</strong>Contacting the pipeline backend.</div>
        {:else if jobs.length === 0}
          <div class="empty-rule">
            <strong>No cues spotted yet</strong>
            Paste a script under New cue and run the sheet.
            <br /><br />
            <button type="button" class="btn btn-compact btn-solid" on:click={openNewJob}><Icon name="plus" size={13} /> New cue</button>
          </div>
        {:else}
          <div class="empty-rule">
            <strong>Nothing matches this filter</strong>
            {jobs.length} cues on the sheet; none in “{jobFilter}”.
            <br /><br />
            <button type="button" class="text-btn" on:click={() => selectFilter('all')}>Show all cues</button>
          </div>
        {/if}
      </div>

      {#if displayedJob}
        <section class="detail-sheet" aria-label="Selected cue">
          <div class="detail-head">
            <span class="cue-no" aria-hidden="true">{displayedJob.id.slice(0, 8)}</span>
            <div class="detail-title-block">
              <h2>{displayedJob.title}</h2>
              <p class="detail-meta">
                {displayedJob.slug}<span class="sep">·</span>{displayedJob.scriptWords === null ? 'word count unavailable' : `${displayedJob.scriptWords} words`}<span class="sep">·</span>updated {displayedJob.updated}
              </p>
            </div>
            <StatusPill status={displayedJob.status} label={displayedJob.statusLabel} />
            <div class="detail-actions">
              <button type="button" class="btn btn-compact" disabled={!mutationsEnabled || refreshing} on:click={() => void refreshSelectedJob()}><Icon name="refresh" size={13} /> Refresh status</button>
            </div>
          </div>

          <div class="detail-grid">
            <div class="detail-col">
              <div class="ledger-title"><span>Pipeline stages</span><span class="ledger-side">{displayedJob.progress}% complete</span></div>
              <Pipeline stages={displayedJob.stages} {busyStage} disabled={!mutationsEnabled || actionBusy !== null} onRun={(stage) => void handleRunStage(stage)} />
              <div class="pipeline-foot">
                <span>{#if displayedJob.backendStatus === 'running'}<span class="running-mark" aria-hidden="true"></span>{/if}{displayedJob.lastError ?? displayedJob.statusLabel}</span>
                <button type="button" class="text-btn" disabled={!mutationsEnabled} on:click={() => void refreshSelectedJob()}>Poll now</button>
              </div>

              <div class="ledger-title" style="margin-top: 24px;"><span>Validation gates</span><StatusPill status={validationStatus} label={validationLabel} /></div>
              {#if displayedJob.validation.length > 0}
                <div>
                  {#each displayedJob.validation as check (check.label)}
                    <div class={`check-row check-${check.state}`}>
                      <span class="check-mark" aria-hidden="true">{check.state === 'pass' ? '✓' : check.state === 'warn' ? '!' : '✗'}</span>
                      <span class="check-label">{check.label}</span>
                      <span class="check-detail">{check.value}</span>
                    </div>
                  {/each}
                </div>
              {:else}
                <div class="empty-rule">No validation report yet — run stage 08 on this cue.</div>
              {/if}
              {#if selectedValidation && selectedValidation.errors.length > 0}
                <div class="error-line" role="alert">{selectedValidation.errors.join(' · ')}</div>
              {/if}
            </div>

            <div class="detail-col">
              <PreviewCard
                title={displayedJob.status === 'approved' ? 'Final preview' : 'Rendered preview'}
                src={videoArtifact?.url || null}
                mediaType={videoArtifact?.meta ?? 'video/mp4'}
                posterLabel={dataMode === 'demo' ? 'Sample preview is not playable' : 'No rendered video yet'}
              />
              {#if videoArtifact?.url}
                <div class="upload-line">
                  <a class="btn btn-compact" href={videoArtifact.url} target="_blank" rel="noreferrer" download={videoArtifact.name}><Icon name="download" size={13} /> Download {videoArtifact.name}</a>
                </div>
              {/if}

              <div class="ledger-title" style="margin-top: 24px;"><span>Artifacts</span><span class="ledger-side">{displayedJob.artifacts.length} files</span></div>
              {#if displayedJob.artifacts.length > 0}
                <div>
                  {#each displayedJob.artifacts as artifact, artifactIndex (artifact.name)}
                    <div class="artifact-row">
                      <span class="a-no">{String(artifactIndex + 1).padStart(2, '0')}</span>
                      <span class="a-name">{artifact.name}</span>
                      <span class="a-meta">{artifact.size}{artifact.meta ? ` · ${artifact.meta}` : ''}</span>
                      {#if artifact.url}
                        <a class="text-btn" href={artifact.url} target="_blank" rel="noreferrer">Open</a>
                      {:else}
                        <span class="a-meta">no url</span>
                      {/if}
                    </div>
                  {/each}
                </div>
              {:else}
                <div class="empty-rule">No artifacts yet — stages write files as they run.</div>
              {/if}
            </div>
          </div>

          <div class="detail-foot">
            <div class="ledger-title"><span>Runner inputs</span><span class="ledger-side">media paths · overlay provider</span></div>
            <div class="media-grid">
              <div>
                <label class="field-label" for="detail-gameplay-path">Gameplay asset ID or runner path <span>· required for timeline/render</span></label>
                <input id="detail-gameplay-path" class="text-input" bind:value={gameplayPath} placeholder="uploads/gameplay/… or /absolute/path/gameplay.mp4" disabled={!mutationsEnabled} />
              </div>
              <div>
                <label class="field-label" for="detail-music-path">Music asset ID or runner path <span>· optional</span></label>
                <input id="detail-music-path" class="text-input" bind:value={musicPath} placeholder="uploads/music/… or /absolute/path/music.wav" disabled={!mutationsEnabled} />
              </div>
              <div class="field-span">
                <label class="check-field"><input type="checkbox" bind:checked={useOpenCodeZen} disabled={!mutationsEnabled} /> <span>Generate overlay placements with OpenCode Zen · DeepSeek V4 Flash Free</span></label>
              </div>
              {#if !useOpenCodeZen}
                <div class="field-span">
                  <label class="field-label" for="placement-proposals">Placement proposals <span>· JSON array, word-anchored</span></label>
                  <textarea id="placement-proposals" class="placement-input" bind:value={placementText} disabled={!mutationsEnabled} spellcheck="false" placeholder="[]"></textarea>
                </div>
              {/if}
              <div class="field-span">
                <div class="upload-line">
                  <button type="button" class="btn btn-compact" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:click={() => chooseMedia('gameplay')}><Icon name="upload" size={13} /> {mediaUploadBusy === 'gameplay' ? 'Uploading…' : 'Upload gameplay'}</button>
                  <button type="button" class="btn btn-compact" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:click={() => chooseMedia('music')}><Icon name="upload" size={13} /> {mediaUploadBusy === 'music' ? 'Uploading…' : 'Upload music'}</button>
                  <span class="spacer"></span>
                  <button type="button" class="btn btn-compact btn-solid" disabled={!mutationsEnabled || mediaBusy || actionBusy !== null} on:click={() => void registerMedia()}>{mediaBusy ? 'Registering…' : 'Register paths'}</button>
                </div>
                {#if displayedJob.gameplayFile || displayedJob.musicFile}
                  <p class="selection-note">Registered on this cue: {displayedJob.gameplayFile || '—'}{displayedJob.musicFile ? ` · ${displayedJob.musicFile}` : ''}</p>
                {/if}
                {#if gameplaySelection || musicSelection}
                  <p class="selection-note">{gameplaySelection}{gameplaySelection && musicSelection ? ' · ' : ''}{musicSelection}</p>
                {/if}
              </div>
            </div>
          </div>

          <div class="detail-foot">
            <div class="verdict-block">
              <div class="verdict-head">
                <span>Final verdict</span>
                {#if displayedJob.status === 'approved'}
                  <span class="stamp stamp-verdict stamp-pass">Approved</span>
                {:else if displayedJob.status === 'rejected'}
                  <span class="stamp stamp-verdict stamp-fail">Rejected</span>
                {:else if displayedJob.approval}
                  <span class="ledger-side">{displayedJob.approval.decision} · {displayedJob.approval.decided_at}</span>
                {:else}
                  <span class="ledger-side">no verdict recorded</span>
                {/if}
              </div>
              <div class="verdict-body">
                <label class="field-label" for="decision-comment">Review note</label>
                <textarea id="decision-comment" class="review-comment" bind:value={decisionComment} maxlength="2000" placeholder="Context for the next pass — optional for approval, useful for revision or rejection."></textarea>

                {#if pendingDecision}
                  <div class="verdict-confirm" role="group" aria-labelledby="verdict-confirm-title">
                    <strong id="verdict-confirm-title">Confirm {pendingDecision}</strong>
                    <p>
                      {#if pendingDecision === 'approve'}Approval is recorded permanently on the backend job.{:else if pendingDecision === 'reject'}Rejection records your note and closes this pass.{:else}A revision request sends your note back for a new pass.{/if}
                      Only the confirm button calls the API.
                    </p>
                    <div class="verdict-actions">
                      <button type="button" class="btn btn-compact btn-solid" disabled={actionBusy !== null} on:click={() => void confirmDecision()}>Confirm {pendingDecision}</button>
                      <button type="button" class="btn btn-compact" disabled={actionBusy !== null} on:click={cancelDecision}>Cancel</button>
                    </div>
                  </div>
                {:else}
                  <div class="verdict-actions">
                    <button type="button" class="btn btn-amber-outline" disabled={!mutationsEnabled || actionBusy !== null || displayedJob.backendStatus !== 'awaiting_approval'} on:click={() => requestDecision('revise')}>Request revision</button>
                    <button type="button" class="btn btn-cue-outline" disabled={!mutationsEnabled || actionBusy !== null || displayedJob.backendStatus !== 'awaiting_approval'} on:click={() => requestDecision('reject')}>Reject</button>
                    <span class="spacer"></span>
                    <button type="button" class="btn btn-pass" disabled={!canApprove} on:click={() => requestDecision('approve')}><Icon name="check" size={15} /> {actionBusy === 'approve' ? 'Approving…' : displayedJob.status === 'approved' ? 'Approved' : 'Approve final'}</button>
                  </div>
                  <div class={`gate-note ${canApprove ? 'gate-pass' : validationStatus === 'failed' ? 'gate-fail' : ''}`}>
                    <span class="gate-mark" aria-hidden="true"></span>
                    <span>{canApprove ? 'Validation passed — approval is unlocked.' : 'Approval stays locked until the validation gate passes and the cue awaits review.'}</span>
                  </div>
                {/if}
              </div>
            </div>
          </div>
        </section>
      {/if}
    {:else if activeNav === 'scripts'}
      <section id="script-intake" aria-label="New cue">
        <div class="queue-bar">
          <h2 class="section-title"><span class="section-no" aria-hidden="true">SEC 02</span>New cue</h2>
          <div class="masthead-actions">
            <span class={mutationsEnabled ? 'stamp stamp-live' : 'stamp stamp-off'}>{mutationsEnabled ? 'Backend intake ready' : 'Backend required'}</span>
            <button type="button" class="btn btn-compact" disabled={!mutationsEnabled} on:click={importScriptFile}>Import .txt</button>
          </div>
        </div>

        <form class="intake-grid" on:submit|preventDefault={() => void startPipeline()}>
          <div class="intake-col">
            <div class="intake-stack">
              <div>
                <label class="field-label" for="script-title">Cue title</label>
                <input id="script-title" class="text-input" bind:value={scriptTitle} placeholder="Working title for this cue" disabled={!mutationsEnabled} />
              </div>
              <div>
                <div class="lint-tally">
                  <span class="lint-count">{wordCount}<small> WORDS · ≈{estimatedSeconds}s</small></span>
                  {#if intakeResult}
                    <span class={`stamp ${intakeResult.hard_fail ? 'stamp-off' : 'stamp-live'}`}>{intakeResult.hard_fail ? 'Hard fail' : 'Backend lint'}</span>
                  {/if}
                </div>
                <textarea id="script-text" bind:value={scriptText} rows="10" placeholder="Paste the narration script. 150–230 words reads as 60–90 seconds at genre pace." disabled={!mutationsEnabled}></textarea>
                <div class={`lint-rule ${lintTone === 'good' ? 'lint-good' : lintTone === 'warning' ? 'lint-warn' : ''}`}>
                  <strong>{lintLabel}</strong>
                  {lintDetail}
                </div>
                {#if intakeResult && intakeResult.issues.length > 0}
                  <ul class="lint-issues">
                    {#each intakeResult.issues as issue (issue.code + issue.message)}
                      <li><span class="issue-code">{issue.code}</span> {issue.message}</li>
                    {/each}
                  </ul>
                {/if}
                <div class="upload-line">
                  <button type="button" class="text-btn" disabled={!mutationsEnabled || normalizeBusy || !scriptText.trim()} on:click={() => void normalizeScript()}>{normalizeBusy ? 'Normalizing…' : 'Normalize via backend'}</button>
                </div>
              </div>
            </div>
          </div>

          <div class="intake-col">
            <div class="intake-stack">
              <div class="spec-grid">
                <div>
                  <label class="field-label" for="intake-voice">Voice</label>
                  <select id="intake-voice" bind:value={intakeVoice} disabled={!mutationsEnabled}>
                    <option value="af_heart">af_heart · warm</option>
                    <option value="af_bella">af_bella · clear</option>
                    <option value="am_adam">am_adam · grounded</option>
                  </select>
                </div>
                <div>
                  <label class="field-label" for="intake-speed">Speed <output>{Number(intakeSpeed).toFixed(2)}×</output></label>
                  <input id="intake-speed" type="range" min="0.5" max="1.5" step="0.01" bind:value={intakeSpeed} disabled={!mutationsEnabled} />
                </div>
                <div class="field-span">
                  <label class="field-label" for="intake-karaoke">Karaoke mode</label>
                  <select id="intake-karaoke" bind:value={intakeKaraokeMode} disabled={!mutationsEnabled}>
                    <option value="kf">kf · progressive fill</option>
                    <option value="k">k · word highlight</option>
                  </select>
                </div>
              </div>

              <div class="ledger-title"><span>Media</span><span class="ledger-side">stored by the backend</span></div>
              <div class="media-grid">
                <div>
                  <label class="field-label" for="intake-source">Source</label>
                  <select id="intake-source" bind:value={mediaSource} disabled={!mutationsEnabled || mediaUploadBusy !== null}>
                    <option value="original">Original</option>
                    <option value="licensed">Licensed</option>
                    <option value="community">Community</option>
                  </select>
                </div>
                <label class="check-field" style="align-self: center;"><input type="checkbox" bind:checked={mediaConfirmed} disabled={!mutationsEnabled || mediaUploadBusy !== null} /> <span>I have permission to use these files</span></label>
                <div class="field-span">
                  <label class="field-label" for="intake-gameplay-path">Gameplay asset ID or runner path <span>· required for timeline/render</span></label>
                  <input id="intake-gameplay-path" class="text-input" bind:value={gameplayPath} placeholder="uploads/gameplay/… or /absolute/path/gameplay.mp4" disabled={!mutationsEnabled} />
                </div>
                <div class="field-span">
                  <label class="field-label" for="intake-music-path">Music asset ID or runner path <span>· optional</span></label>
                  <input id="intake-music-path" class="text-input" bind:value={musicPath} placeholder="uploads/music/… or /absolute/path/music.wav" disabled={!mutationsEnabled} />
                </div>
              </div>
              <div class="upload-line">
                <input bind:this={scriptFileInput} class="sr-only" type="file" accept=".txt,text/plain" on:change={(event) => void handleScriptFile(event)} />
                <input bind:this={gameplayFileInput} class="sr-only" type="file" accept="video/*" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:change={(event) => void handleMediaFile(event, 'gameplay')} />
                <input bind:this={musicFileInput} class="sr-only" type="file" accept="audio/*" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:change={(event) => void handleMediaFile(event, 'music')} />
                <button type="button" class="btn btn-compact" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:click={() => chooseMedia('gameplay')}><Icon name="upload" size={13} /> {mediaUploadBusy === 'gameplay' ? 'Uploading…' : 'Upload gameplay'}</button>
                <button type="button" class="btn btn-compact" disabled={!mutationsEnabled || mediaUploadBusy !== null} on:click={() => chooseMedia('music')}><Icon name="upload" size={13} /> {mediaUploadBusy === 'music' ? 'Uploading…' : 'Upload music'}</button>
              </div>
              {#if gameplaySelection || musicSelection}
                <p class="selection-note">{gameplaySelection}{gameplaySelection && musicSelection ? ' · ' : ''}{musicSelection}</p>
              {/if}
              <button type="submit" class="btn btn-solid btn-block" disabled={!mutationsEnabled || actionBusy === 'create' || !settings || mediaUploadBusy !== null}>
                <Icon name="arrow-right" size={15} /> {actionBusy === 'create' ? 'Creating cue…' : 'Create cue & intake'}
              </button>
            </div>
          </div>
        </form>
      </section>
    {:else}
      <section id="settings-panel" aria-label="Session setup">
        <div class="queue-bar">
          <h2 class="section-title"><span class="section-no" aria-hidden="true">SEC 03</span>Session setup</h2>
          <button type="button" class="btn btn-solid btn-compact" disabled={!mutationsEnabled || !settings || settingsBusy} on:click={() => void saveSettings()}><Icon name="check" size={13} /> {settingsBusy ? 'Saving…' : 'Save settings'}</button>
        </div>

        <div class="setup-section">
          <div class="setup-grid">
            <fieldset class="engine-block" disabled={!mutationsEnabled}>
              <legend><strong>Kokoro</strong><small>Local TTS</small><StatusPill status={healthFor('kokoro')} label={healthLabel('kokoro')} /></legend>
              <div class="engine-body">
                <div class="setting-field">
                  <label class="field-label" for="set-voice">Voice</label>
                  <select id="set-voice" bind:value={kokoroVoice}>
                    <option value="af_heart">af_heart · warm</option>
                    <option value="af_bella">af_bella · clear</option>
                    <option value="am_adam">am_adam · grounded</option>
                  </select>
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-speed">Speed factor</label>
                  <div class="settings-range-row">
                    <input id="set-speed" type="range" min="0.5" max="1.5" step="0.01" bind:value={kokoroSpeed} />
                    <output>{Number(kokoroSpeed).toFixed(2)}×</output>
                  </div>
                </div>
                <div class="setting-meta"><span>Backend default</span><strong>{settings?.kokoro_voice ?? '—'} · {settings ? Number(settings.kokoro_speed).toFixed(2) + '×' : '—'}</strong></div>
              </div>
            </fieldset>

            <fieldset class="engine-block" disabled={!mutationsEnabled}>
              <legend><strong>WhisperX</strong><small>Word alignment</small><StatusPill status={healthFor('whisperx')} label={healthLabel('whisperx')} /></legend>
              <div class="engine-body">
                <div class="setting-field">
                  <label class="field-label" for="set-wx-model">Model</label>
                  <input id="set-wx-model" class="text-input" bind:value={whisperModel} />
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-wx-lang">Language</label>
                  <select id="set-wx-lang" bind:value={whisperLanguage}>
                    <option value="auto">Auto detect</option>
                    <option value="en">English (en)</option>
                  </select>
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-wx-device">Device</label>
                  <select id="set-wx-device" bind:value={whisperDevice}>
                    <option value="cpu">cpu</option>
                    <option value="cuda">cuda</option>
                  </select>
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-wx-compute">Compute type</label>
                  <select id="set-wx-compute" bind:value={whisperComputeType}>
                    <option value="int8">int8</option>
                    <option value="int16">int16</option>
                    <option value="float16">float16</option>
                    <option value="float32">float32</option>
                  </select>
                </div>
                <div class="setting-meta"><span>Backend default</span><strong>{settings?.whisperx_model ?? '—'} · {settings?.whisperx_device ?? '—'}</strong></div>
              </div>
            </fieldset>

            <fieldset class="engine-block" disabled={!mutationsEnabled}>
              <legend><strong>FFmpeg</strong><small>Render & gates</small><StatusPill status={healthFor('ffmpeg')} label={healthLabel('ffmpeg')} /></legend>
              <div class="engine-body">
                <div class="setting-field">
                  <label class="field-label" for="set-ffmpeg-bin">ffmpeg binary</label>
                  <input id="set-ffmpeg-bin" class="text-input" bind:value={ffmpegBin} />
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-ffprobe-bin">ffprobe binary</label>
                  <input id="set-ffprobe-bin" class="text-input" bind:value={ffprobeBin} />
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-align-threshold">Alignment confidence threshold</label>
                  <div class="settings-range-row">
                    <input id="set-align-threshold" type="range" min="0" max="1" step="0.05" bind:value={alignmentThreshold} />
                    <output>{Number(alignmentThreshold).toFixed(2)}</output>
                  </div>
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-karaoke">Karaoke mode</label>
                  <select id="set-karaoke" bind:value={karaokeMode}>
                    <option value="kf">kf · progressive fill</option>
                    <option value="k">k · word highlight</option>
                  </select>
                </div>
                <div class="setting-field">
                  <label class="field-label" for="set-stage-timeout">Stage timeout (seconds)</label>
                  <input id="set-stage-timeout" class="text-input" type="number" min="60" step="1" bind:value={stageTimeout} />
                </div>
              </div>
            </fieldset>
          </div>

          <div class="api-block">
            <div class="engine-head"><strong>Backend connection</strong><small>{getApiBaseUrl() || 'not set — demo data'}</small></div>
            <div class="api-body">
              <label class="sr-only" for="api-base">API base URL</label>
              <input id="api-base" class="text-input" bind:value={apiBaseDraft} placeholder="http://127.0.0.1:8000" />
              <button type="button" class="btn btn-compact btn-solid" disabled={refreshing} on:click={() => void connectToApi()}>Connect</button>
              <button type="button" class="btn btn-compact" on:click={() => { apiBaseDraft = ''; }}>Clear</button>
            </div>
          </div>

          {#if health}
            <p class="health-line">{health.service} v{health.version} · {health.job_count ?? 0} jobs on disk · data dir {health.data_directory ?? 'unknown'}{health.data_directory_writable === false ? ' (read-only)' : ''} · {healthSummary()}</p>
          {/if}
        </div>
      </section>
    {/if}
  </main>

  <footer class="sheet-footer">
    <span>SlopShots · spotting sheet · v0.1 operator</span>
    <span>Manual publishing remains outside API v1</span>
  </footer>
</div>

{#if toastMessage}
  <div class={`toast ${toastTone === 'error' ? 'toast-error' : toastTone === 'warning' ? 'toast-warning' : ''}`} role="status">
    <span class="toast-mark" aria-hidden="true"></span>
    <span class="toast-copy">{toastMessage}</span>
    <button type="button" class="text-btn" on:click={() => (toastMessage = '')} aria-label="Dismiss notice">✕</button>
  </div>
{/if}
