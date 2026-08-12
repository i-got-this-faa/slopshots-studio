import type {
  DashboardData,
  PipelineStage,
  RuntimeSettings,
  StageName,
  VideoJob
} from './types';

// These records are deliberately incomplete sample content. The page only
// uses them after the API connection fails and labels them as disconnected
// sample data; artifact URLs stay empty so sample files can never be opened as
// if they were real backend outputs.

const stage = (
  id: StageName,
  name: string,
  detail: string,
  state: PipelineStage['state'],
  status: PipelineStage['status'],
  duration?: string
): PipelineStage => ({
  id,
  name,
  detail,
  state,
  status,
  duration,
  cacheHit: status === 'cached'
});

const commonStages = (active: StageName | null, completed: StageName[]): PipelineStage[] => {
  const definitions: Array<[StageName, string, string]> = [
    ['intake', 'Script intake', 'Normalize + lint'],
    ['tts', 'Kokoro TTS', 'Voice synthesis'],
    ['align', 'WhisperX align', 'Word timestamps'],
    ['placements', 'Overlay pass', 'Placement anchors'],
    ['subtitles', 'Subtitles', 'ASS karaoke cards'],
    ['timeline', 'Timeline', 'EDL assembly'],
    ['render', 'FFmpeg render', 'Draft encode'],
    ['validate', 'Validation gate', 'Format + content checks']
  ];

  return definitions.map(([id, name, detail]) => {
    if (completed.includes(id)) return stage(id, name, detail, 'complete', 'succeeded', id === 'render' ? '4m 12s' : 'done');
    if (id === active) return stage(id, name, detail, 'active', 'running', id === 'render' ? 'running' : 'running');
    return stage(id, name, detail, 'pending', 'pending');
  });
};

const artifacts = (kind: 'draft' | 'final' = 'draft') => [
  { name: kind === 'final' ? 'final.mp4' : 'draft.mp4', type: 'video' as const, size: '42.8 MB', meta: 'sample only', url: '' },
  { name: 'voice.wav', type: 'audio' as const, size: '9.4 MB', meta: 'sample only', url: '' },
  { name: 'subtitles.ass', type: 'text' as const, size: '18 KB', meta: 'sample only', url: '' },
  { name: 'words.json', type: 'data' as const, size: '61 KB', meta: 'sample only', url: '' },
  { name: 'cmd.sh', type: 'command' as const, size: '2 KB', meta: 'sample only', url: '' }
];

const baseJob = (
  id: string,
  title: string,
  status: VideoJob['status'],
  statusLabel: string,
  active: StageName | null,
  completed: StageName[],
  kind: 'draft' | 'final'
): VideoJob => ({
  id,
  title,
  slug: title.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
  status,
  backendStatus: status === 'review' ? 'awaiting_approval' : status === 'rendering' ? 'running' : status === 'approved' ? 'approved' : 'created',
  statusLabel,
  updated: 'sample data',
  duration: kind === 'final' ? '00:49' : '00:42',
  progress: Math.round((completed.length / 8) * 100),
  scriptWords: kind === 'final' ? 184 : 168,
  owner: 'sample',
  accent: id === 'job-002' ? 'cyan' : id === 'job-003' ? 'orange' : id === 'job-004' ? 'lime' : 'violet',
  stages: commonStages(active, completed),
  artifacts: artifacts(kind),
  validation: [{ label: 'Sample record', value: 'Not from the backend', state: 'warn' }],
  gameplayFile: '',
  musicFile: '',
  voice: 'af_heart',
  speed: 1,
  karaokeMode: 'kf',
  approval: null,
  lastError: null
});

export const demoJobs: VideoJob[] = [
  baseJob('job-001', 'The parry that broke the build', 'review', 'Sample review job', 'validate', ['intake', 'tts', 'align', 'placements', 'subtitles', 'timeline', 'render'], 'draft'),
  baseJob('job-002', 'Speedrun cooking, no resets', 'rendering', 'Sample running job', 'render', ['intake', 'tts', 'align', 'placements', 'subtitles', 'timeline'], 'draft'),
  baseJob('job-003', 'Patch notes nobody asked for', 'queued', 'Sample queued job', 'tts', ['intake'], 'draft'),
  baseJob('job-004', 'One HP and still greedy', 'approved', 'Sample approved job', null, ['intake', 'tts', 'align', 'placements', 'subtitles', 'timeline', 'render', 'validate'], 'final')
];

export const demoSettings: RuntimeSettings = {
  data_dir: 'sample data directory',
  ffmpeg_bin: 'ffmpeg',
  ffprobe_bin: 'ffprobe',
  kokoro_voice: 'af_heart',
  kokoro_speed: 1,
  whisperx_model: 'small',
  whisperx_device: 'cpu',
  whisperx_compute_type: 'int8',
  whisperx_language: null,
  alignment_confidence_threshold: 0.6,
  karaoke_mode: 'kf',
  stage_timeout_s: 3600
};

export const demoDashboard: DashboardData = {
  stats: { inFlight: 2, review: 1, averageRender: '—', passRate: '—' },
  jobs: demoJobs,
  settings: demoSettings,
  health: null
};
