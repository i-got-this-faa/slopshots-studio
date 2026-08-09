import type {
  BackendArtifact,
  BackendJob,
  BackendStageStatus,
  DashboardData,
  DashboardStats,
  HealthResponse,
  MediaAsset,
  MediaKind,
  MediaSource,
  NormalizationResult,
  PipelineStage,
  PlacementProposal,
  RuntimeSettings,
  StageName,
  ValidationResult,
  VideoJob
} from './types';

const envBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? '';
let activeBaseUrl = normalizeBaseUrl(envBaseUrl);

// Kept for the settings panel's build-time default. Runtime reconnects should
// use getApiBaseUrl(), because the operator can change this value in-browser.
export const apiBaseUrl = activeBaseUrl;

export class ApiError extends Error {
  status: number | null;
  code: string | null;
  jobId: string | null;

  constructor(
    message: string,
    status: number | null = null,
    code: string | null = null,
    jobId: string | null = null
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.jobId = jobId;
  }
}

export function getApiBaseUrl(): string {
  return activeBaseUrl;
}

export function setApiBaseUrl(value: string): void {
  activeBaseUrl = normalizeBaseUrl(value);
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${activeBaseUrl}${path.startsWith('/') ? path : `/${path}`}`;
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs?: number): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(
    () => controller.abort(),
    timeoutMs ?? (path.includes('/stages/') && init.method === 'POST' ? 60 * 60 * 1000 : 15_000)
  );

  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: { Accept: 'application/json', ...(init.headers ?? {}) },
      signal: controller.signal
    });

    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      let code: string | null = null;
      try {
        const body = await response.json();
        const detail = body?.detail;
        if (typeof detail === 'string') message = detail;
        if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
          message = typeof detail.message === 'string' ? detail.message : message;
          code = typeof detail.code === 'string' ? detail.code : null;
        }
        if (Array.isArray(detail)) {
          const validationMessages = detail
            .map((item) => (typeof item?.msg === 'string' ? item.msg : null))
            .filter((item): item is string => Boolean(item));
          if (validationMessages.length) message = validationMessages.join('; ');
        }
      } catch {
        // Keep the HTTP status when the response is not JSON.
      }
      throw new ApiError(message, response.status, code);
    }

    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) return (await response.json()) as T;
    return (await response.text()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The backend did not respond before the request timed out.');
    }
    throw new ApiError(error instanceof Error ? error.message : 'Could not reach the backend.');
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export async function loadDashboard(): Promise<DashboardData> {
  const [jobs, settings, health] = await Promise.all([
    listJobs(),
    request<RuntimeSettings>('/api/v1/settings'),
    request<HealthResponse>('/api/v1/health').catch(() => null)
  ]);
  return adaptDashboard(jobs, settings, health);
}

export async function listJobs(): Promise<VideoJob[]> {
  const jobs = await request<BackendJob[]>('/api/v1/jobs');
  return jobs.map((job) => adaptJob(job));
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/v1/health');
}

export async function getJob(jobId: string): Promise<VideoJob> {
  return adaptJob(await request<BackendJob>(`/api/v1/jobs/${encodeURIComponent(jobId)}`));
}

export async function normalizeScript(script: string): Promise<NormalizationResult> {
  return request<NormalizationResult>('/api/v1/intake/normalize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script })
  });
}

export async function uploadMedia(
  file: File,
  input: {
    assetId: string;
    kind: Exclude<MediaKind, 'overlay'>;
    source: MediaSource;
    confirmed: boolean;
    description?: string;
    tags?: string[];
  }
): Promise<MediaAsset> {
  const form = new FormData();
  form.append('asset_id', input.assetId);
  form.append('kind', input.kind);
  form.append('source', input.source);
  form.append('confirmed', String(input.confirmed));
  form.append('description', input.description ?? '');
  form.append('tags', (input.tags ?? []).join(','));
  form.append('file', file, file.name);

  return request<MediaAsset>('/api/v1/media/upload', {
    method: 'POST',
    body: form
  }, 60 * 60 * 1000);
}

export function deriveMediaAssetId(
  kind: Exclude<MediaKind, 'overlay'>,
  file: Pick<File, 'name' | 'size' | 'type'>
): string {
  const filename = slugify(file.name.replace(/\.[^.]+$/, '')).slice(0, 80) || 'asset';
  const fingerprint = stableHash(`${file.name}\u0000${file.size}\u0000${file.type}`);
  return `uploads/${kind}/${filename}-${fingerprint}`;
}

export async function createJob(input: {
  name: string;
  script: string;
  gameplayFile?: string;
  musicFile?: string;
  voice?: string;
  speed?: number;
  karaokeMode?: 'kf' | 'k';
}): Promise<{ job: VideoJob; intake: NormalizationResult }> {
  const created = await request<BackendJob>('/api/v1/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: input.name,
      script: input.script,
      ...(input.gameplayFile ? { gameplay_file: input.gameplayFile } : {}),
      ...(input.musicFile ? { music_file: input.musicFile } : {}),
      ...(input.voice ? { kokoro_voice: input.voice } : {}),
      ...(input.speed !== undefined ? { kokoro_speed: input.speed } : {}),
      ...(input.karaokeMode ? { karaoke_mode: input.karaokeMode } : {})
    })
  });

  try {
    const intake = await request<{ job: BackendJob; result: NormalizationResult }>(
      `/api/v1/jobs/${encodeURIComponent(created.id)}/intake`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: input.script })
      }
    );
    return { job: adaptJob(intake.job, intake.result), intake: intake.result };
  } catch (error) {
    if (error instanceof ApiError) {
      throw new ApiError(
        `Job ${created.id} was created, but intake failed: ${error.message}`,
        error.status,
        error.code,
        created.id
      );
    }
    throw error;
  }
}

export async function updateJob(
  jobId: string,
  update: {
    gameplay_file?: string;
    music_file?: string;
    kokoro_voice?: string;
    kokoro_speed?: number;
    karaoke_mode?: 'kf' | 'k';
  }
): Promise<VideoJob> {
  const job = await request<BackendJob>(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update)
  });
  return adaptJob(job);
}

export async function runJobStage(
  jobId: string,
  stage: StageName,
  options: {
    force?: boolean;
    placements?: PlacementProposal[];
    useOpenCodeZen?: boolean;
    gameplayFile?: string;
    musicFile?: string;
  } = {}
): Promise<VideoJob> {
  const response = await request<{ job: BackendJob }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/stages/${stage}/run`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        force: options.force ?? false,
        ...(options.placements !== undefined ? { placements: options.placements } : {}),
        ...(options.useOpenCodeZen ? { use_opencode_zen: true } : {}),
        ...(options.gameplayFile ? { gameplay_file: options.gameplayFile } : {}),
        ...(options.musicFile ? { music_file: options.musicFile } : {})
      })
    }
  );
  return adaptJob(response.job);
}

export async function saveRuntimeSettings(settings: Partial<RuntimeSettings>): Promise<RuntimeSettings> {
  const { data_dir: _dataDir, ...update } = settings;
  return request<RuntimeSettings>('/api/v1/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update)
  });
}

export async function decideJob(
  jobId: string,
  action: 'approve' | 'reject' | 'revise',
  comment: string
): Promise<VideoJob> {
  const path = `/api/v1/jobs/${encodeURIComponent(jobId)}/${action}`;
  const body = {
    decided_by: 'operator-dashboard',
    ...(comment.trim() ? { comment: comment.trim() } : {})
  };
  if (action === 'revise') return adaptJob(await request<BackendJob>(path, jsonPost(body)));
  const response = await request<{ job: BackendJob }>(path, jsonPost(body));
  return adaptJob(response.job);
}

export async function getValidation(job: VideoJob): Promise<ValidationResult | null> {
  const artifact = job.artifacts.find((item) => item.name === 'validation.json');
  if (!artifact?.url) return null;
  return request<ValidationResult>(artifact.url);
}

function jsonPost(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  };
}

function adaptDashboard(
  jobs: VideoJob[],
  settings: RuntimeSettings,
  health: HealthResponse | null
): DashboardData {
  const renderDurations = jobs
    .flatMap((job) => job.stages.filter((stage) => stage.id === 'render'))
    .map((stage) => parseDuration(stage.duration))
    .filter((value): value is number => value !== null);
  const validations = jobs.flatMap((job) =>
    job.stages.filter((stage) => stage.id === 'validate' && stage.status !== 'pending')
  );
  const passed = validations.filter((stage) => ['succeeded', 'cached'].includes(stage.status)).length;
  const stats: DashboardStats = {
    inFlight: jobs.filter((job) => ['queued', 'rendering'].includes(job.status)).length,
    review: jobs.filter((job) => job.status === 'review').length,
    averageRender: renderDurations.length
      ? formatDuration(renderDurations.reduce((sum, value) => sum + value, 0) / renderDurations.length)
      : '—',
    passRate: validations.length ? `${Math.round((passed / validations.length) * 100)}%` : '—'
  };
  return { jobs, settings, health, stats };
}

export function adaptJob(job: BackendJob, intake?: NormalizationResult): VideoJob {
  const stages: PipelineStage[] = job.stages.map((stage) => {
    const seconds = elapsedSeconds(stage.started_at, stage.finished_at);
    return {
      id: stage.stage,
      name: stageName(stage.stage),
      detail: stage.error ?? stage.message ?? statusDetail(stage.status),
      state: ['succeeded', 'cached'].includes(stage.status)
        ? 'complete'
        : stage.status === 'running'
          ? 'active'
          : ['failed', 'blocked'].includes(stage.status)
            ? 'error'
            : 'pending',
      status: stage.status,
      duration: seconds === null ? undefined : formatDuration(seconds),
      cacheHit: stage.cache_hit,
      errorCode: stage.error_code
    };
  });
  const validateStage = stages.find((stage) => stage.id === 'validate');
  const validation = job.last_error
    ? [{ label: 'Pipeline error', value: job.last_error, state: 'fail' as const }]
    : validateStage?.state === 'complete'
      ? [{ label: 'Validation gate', value: validateStage.detail, state: 'pass' as const }]
      : validateStage?.state === 'error'
        ? [{ label: 'Validation gate', value: validateStage.detail, state: 'fail' as const }]
        : [{ label: 'Validation gate', value: 'Not run yet', state: 'warn' as const }];

  return {
    id: job.id,
    title: job.name,
    slug: slugify(job.name),
    status: uiStatus(job.status),
    backendStatus: job.status,
    statusLabel: statusLabel(job.status),
    updated: formatTimestamp(job.updated_at),
    duration: '—',
    progress: Math.round(
      (stages.filter((stage) => stage.state === 'complete').length / Math.max(1, stages.length)) * 100
    ),
    scriptWords: intake?.word_count ?? null,
    owner: job.approval?.decided_by ?? '—',
    accent: accentFor(job.id),
    stages,
    artifacts: job.artifacts.filter((artifact) => artifact.exists).map(adaptArtifact),
    validation,
    gameplayFile: job.gameplay_file ?? '',
    musicFile: job.music_file ?? '',
    voice: job.kokoro_voice,
    speed: job.kokoro_speed,
    karaokeMode: job.karaoke_mode,
    approval: job.approval,
    lastError: job.last_error
  };
}

export function validationChecks(result: ValidationResult | null, job: VideoJob): VideoJob['validation'] {
  if (!result) {
    return job.lastError
      ? [{ label: 'Pipeline error', value: job.lastError, state: 'fail' }]
      : [{ label: 'Validation gate', value: 'Not run yet', state: 'warn' }];
  }
  const checks: VideoJob['validation'] = result.checks.map((check) => ({
    label: check.name,
    value: check.detail,
    state: check.passed ? 'pass' : 'fail'
  }));
  if (result.measured_duration_s !== null) {
    checks.push({ label: 'Duration', value: `${result.measured_duration_s.toFixed(1)}s`, state: 'pass' });
  }
  if (result.measured_lufs !== null) {
    checks.push({ label: 'Integrated loudness', value: `${result.measured_lufs.toFixed(1)} LUFS`, state: 'pass' });
  }
  if (result.measured_true_peak_db !== null) {
    checks.push({ label: 'True peak', value: `${result.measured_true_peak_db.toFixed(1)} dB`, state: 'pass' });
  }
  result.errors.forEach((error, index) =>
    checks.push({ label: `Validation error ${index + 1}`, value: error, state: 'fail' })
  );
  return checks.length
    ? checks
    : [{ label: 'Validation gate', value: result.passed ? 'Passed' : 'Failed', state: result.passed ? 'pass' : 'fail' }];
}

export function formatSeconds(seconds: number): string {
  return formatDuration(seconds);
}

function adaptArtifact(artifact: BackendArtifact): VideoJob['artifacts'][number] {
  const type = artifact.media_type.startsWith('video')
    ? 'video'
    : artifact.media_type.startsWith('audio')
      ? 'audio'
      : artifact.name.endsWith('.json')
        ? 'data'
        : artifact.name.endsWith('.sh')
          ? 'command'
          : 'text';
  return {
    name: artifact.name,
    type,
    size: formatBytes(artifact.size_bytes),
    meta: artifact.media_type,
    url: artifact.download_path ? apiUrl(artifact.download_path) : ''
  };
}

function uiStatus(status: BackendJob['status']): VideoJob['status'] {
  if (status === 'awaiting_approval') return 'review';
  if (status === 'approved') return 'approved';
  if (status === 'rejected') return 'rejected';
  if (status === 'completed') return 'completed';
  if (status === 'failed') return 'failed';
  if (status === 'running') return 'rendering';
  return 'queued';
}

function statusLabel(status: BackendJob['status']): string {
  const labels: Record<BackendJob['status'], string> = {
    created: 'Ready to run',
    running: 'Stage running',
    awaiting_approval: 'Ready for review',
    approved: 'Approved',
    rejected: 'Rejected',
    completed: 'Completed',
    failed: 'Needs attention'
  };
  return labels[status];
}

function stageName(stage: StageName): string {
  return ({
    intake: 'Script intake',
    tts: 'Kokoro TTS',
    align: 'WhisperX align',
    placements: 'Overlay pass',
    subtitles: 'Subtitles',
    timeline: 'Timeline',
    render: 'FFmpeg render',
    validate: 'Validation gate'
  })[stage];
}

function statusDetail(status: BackendStageStatus): string {
  return ({
    pending: 'Waiting to run',
    running: 'Running now',
    cached: 'Reused cached outputs',
    succeeded: 'Completed',
    failed: 'Stage failed',
    blocked: 'Blocked by validation',
    awaiting_approval: 'Waiting for approval'
  })[status];
}

function elapsedSeconds(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const elapsed = (new Date(end).getTime() - new Date(start).getTime()) / 1000;
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : null;
}

function parseDuration(value: string | undefined): number | null {
  if (!value) return null;
  const seconds = Number.parseFloat(value);
  if (value.endsWith('m')) return seconds * 60;
  if (value.includes('m ')) {
    const match = /^(\d+)m\s+(\d+)s$/.exec(value);
    return match ? Number(match[1]) * 60 + Number(match[2]) : null;
  }
  return value.endsWith('s') ? seconds : null;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'untitled';
}

function accentFor(id: string): VideoJob['accent'] {
  const colors: VideoJob['accent'][] = ['violet', 'cyan', 'orange', 'pink', 'lime'];
  const hash = [...id].reduce((total, char) => total + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/$/, '');
}

function stableHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}
