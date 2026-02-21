export type UploadMode = 'draft' | 'publish';

export type WorkerJobStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'BLOCKED_LOGIN'
  | 'COMPLETED'
  | 'FAILED';

export type FailureReasonCode =
  | 'SESSION_EXPIRED'
  | 'SECURITY_CHALLENGE'
  | 'SELECTOR_BROKEN'
  | 'NETWORK_ERROR';

export interface WorkerJob {
  id: string;
  status: WorkerJobStatus;
  mode: UploadMode;
  dirPath: string;
  chatId: string;
  messageId?: number;
  createdAt: string;
  updatedAt: string;
  attempts: number;
  lastError?: string;
  reasonCode?: FailureReasonCode;
  artifactsDir?: string;
  /** CAPTCHA fallback(interactiveLogin) 시도 여부 — 동일 job에서 fallback 1회 제한 */
  captchaFallbackAttempted?: boolean;
}

export interface WorkerQueueState {
  version: number;
  jobs: WorkerJob[];
}

export type SessionValidationResult = {
  ok: boolean;
  reasonCode?: FailureReasonCode;
  detail: string;
  artifactsDir?: string;
};

