export type BackendJobStatus =
  | 'created'
  | 'running'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'completed'
  | 'failed';

export type StageName =
  | 'intake'
  | 'tts'
  | 'align'
  | 'placements'
  | 'subtitles'
  | 'timeline'
  | 'render'
  | 'validate';

export type MediaKind = 'gameplay' | 'music' | 'overlay';
export type MediaSource = 'original' | 'licensed' | 'community';

export type BackendStageStatus =
  | 'pending'
  | 'running'
  | 'cached'
  | 'succeeded'
  | 'failed'
  | 'blocked'
  | 'awaiting_approval';
export type JobStatus = 'rendering' | 'review' | 'queued' | 'approved' | 'rejected' | 'completed' | 'failed';
export type StageState = 'complete' | 'active' | 'pending' | 'error';

export interface BackendStage {
  stage: StageName;
  status: BackendStageStatus;
  started_at: string | null;
  finished_at: string | null;
  outputs: string[];
  cache_hit: boolean;
  message: string | null;
  error_code: string | null;
  error: string | null;
}

export interface BackendArtifact {
  name: string;
  exists: boolean;
  size_bytes: number;
  media_type: string;
  download_path: string | null;
}

export interface MediaAsset {
  id: string;
  kind: MediaKind;
  filename: string;
  media_type: string;
  size_bytes: number;
  created_at: string;
  source: MediaSource;
  confirmed: boolean;
  description: string;
  tags: string[];
  duration_s: number | null;
  width: number | null;
  height: number | null;
}

export interface ApprovalRecord {
  decision: string;
  decided_at: string;
  decided_by: string | null;
  comment: string | null;
}

export interface BackendJob {
  id: string;
  name: string;
  status: BackendJobStatus;
  created_at: string;
  updated_at: string;
  directory: string;
  gameplay_file: string | null;
  music_file: string | null;
  kokoro_voice: string;
  kokoro_speed: number;
  karaoke_mode: 'kf' | 'k';
  stages: BackendStage[];
  artifacts: BackendArtifact[];
  approval: ApprovalRecord | null;
  last_error: string | null;
}

export interface PipelineStage {
  id: StageName;
  name: string;
  detail: string;
  state: StageState;
  status: BackendStageStatus;
  duration?: string;
  cacheHit: boolean;
  errorCode?: string | null;
}

export interface Artifact {
  name: string;
  type: 'video' | 'audio' | 'text' | 'data' | 'command';
  size: string;
  meta: string;
  url: string;
}

export interface ValidationCheck {
  label: string;
  value: string;
  state: 'pass' | 'warn' | 'fail';
}

export interface ValidationResult {
  passed: boolean;
  checks: Array<{ name: string; passed: boolean; detail: string }>;
  errors: string[];
  measured_duration_s: number | null;
  measured_lufs: number | null;
  measured_true_peak_db: number | null;
}

export interface VideoJob {
  id: string;
  title: string;
  slug: string;
  status: JobStatus;
  backendStatus: BackendJobStatus;
  statusLabel: string;
  updated: string;
  duration: string;
  progress: number;
  scriptWords: number | null;
  owner: string;
  accent: 'violet' | 'cyan' | 'orange' | 'pink' | 'lime';
  stages: PipelineStage[];
  artifacts: Artifact[];
  validation: ValidationCheck[];
  gameplayFile: string;
  musicFile: string;
  voice: string;
  speed: number;
  karaokeMode: 'kf' | 'k';
  approval: ApprovalRecord | null;
  lastError: string | null;
}

export interface DashboardStats {
  inFlight: number;
  review: number;
  averageRender: string;
  passRate: string;
}

export interface RuntimeSettings {
  data_dir: string;
  ffmpeg_bin: string;
  ffprobe_bin: string;
  kokoro_voice: string;
  kokoro_speed: number;
  whisperx_model: string;
  whisperx_device: string;
  whisperx_compute_type: string;
  whisperx_language: string | null;
  alignment_confidence_threshold: number;
  karaoke_mode: 'kf' | 'k';
  stage_timeout_s: number;
}

export interface IntegrationAvailability {
  available: boolean;
  dependency: string;
  executable?: string | null;
  detail?: string | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  integrations: Record<string, IntegrationAvailability>;
  data_directory?: string;
  data_directory_writable?: boolean;
  job_count?: number;
}

export interface DashboardData {
  stats: DashboardStats;
  jobs: VideoJob[];
  settings: RuntimeSettings;
  health: HealthResponse | null;
}

export interface LintIssue {
  level: string;
  code: string;
  message: string;
}

export interface NormalizationResult {
  original: string;
  normalized: string;
  word_count: number;
  estimated_duration_s: number;
  hard_fail: boolean;
  issues: LintIssue[];
}

export interface PlacementProposal {
  asset_id: string;
  anchor_text: string;
  zone: 'top-left' | 'top-right' | 'middle';
  duration_s: number;
  animation?: 'pop-in' | 'bounce' | 'slide-up';
  reason?: string;
  scale?: number;
}
