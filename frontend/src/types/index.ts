export interface SystemStatus {
  mode: string;
  allow_live_submit: boolean;
  active_revision: string;
  worker_online: boolean;
  worker_stale: boolean;
  last_worker_heartbeat_at: string | null;
  timestamp: string;
}

export interface Account {
  id: string;
  provider: 'kaggle' | 'wandb';
  name: string;
  slug: string;
  principal: string;
  description: string;
  enabled: boolean;
  is_default: boolean;
  revision: number;
  has_credential: boolean;
  test_result?: string | null;
  rotated_at?: string | null;
}

export interface HealthStatus {
  health: 'progressing' | 'running' | 'suspected_stall' | 'terminal' | 'pending' | 'unknown';
  provider_state: string;
  status_stale: boolean;
  last_progress_at: string | null;
  last_iteration: number | null;
  provider_observed_at: string | null;
  last_check_attempt_at: string | null;
  last_check_error: string | null;
}

export interface CurvePoint {
  step: number;
  sup?: number | null;
  cons?: number | null;
  lr?: number | null;
  t?: number | null;
  dice?: number | null;
  best?: number | null;
}

export interface Notebook {
  id: string;
  kernel: string;
  account_id: string;
  account_name: string;
  wandb_account_id: string | null;
  wandb_account_name: string | null;
  run_ref: string;
  attempt_id: string | null;
  submitted_version: string | null;
  remote_version: string | null;
  health: HealthStatus;
  latest_kaggle?: any;
  latest_wandb?: {
    fetched_at?: string;
    error?: string | null;
    data?: {
      state?: string;
      last_iteration?: number | null;
      last_telemetry_at?: string | null;
      live_metrics?: Record<string, any>;
      curves?: {
        train?: CurvePoint[];
        val?: CurvePoint[];
      };
      live_log_lines?: number;
      summary?: Record<string, any>;
    };
  };
  logs_summary: {
    availability: string;
    source: string;
    truncated: boolean;
    has_text: boolean;
    line_count: number;
    wandb_live_lines?: number;
    progress?: {
      epoch?: string;
      iteration?: number;
      loss?: number;
      recent_line?: string;
    };
  };
}

export interface NotebookLogs {
  availability: string;
  text: string;
  truncated: boolean;
  source: string;
  progress?: any;
  fetched_at?: string;
  wandb_live_text?: string;
  wandb_fetched_at?: string;
}

export interface Operation {
  id: string;
  kind: string;
  target: string;
  account_id: string;
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'unknown' | 'cancelled';
  error: string | null;
  enqueued_at: string;
  updated_at: string;
  dispatched_at: string | null;
}

export interface BuildPreview {
  id: string;
  account_id: string;
  created_at: string;
  options: any;
  manifest: any;
  notebook?: any;
}

