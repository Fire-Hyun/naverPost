import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

export type IdempotencyReasonCode =
  | 'DUP_RUN_DETECTED'
  | 'DRAFT_NOT_EMPTY_ABORT'
  | 'RUN_ID_MISMATCH_RETRY_BLOCKED';

export class IdempotencyError extends Error {
  readonly reasonCode: IdempotencyReasonCode;

  constructor(reasonCode: IdempotencyReasonCode, message: string) {
    super(message);
    this.reasonCode = reasonCode;
  }
}

type LockPayload = {
  job_key: string;
  run_id: string;
  lock_token: string;
  created_at: string;
  pid: number;
};

export type JobLockHandle = {
  keyHash: string;
  lockPath: string;
  lockToken: string;
};

export type JobRunState = {
  job_key: string;
  run_id: string;
  blog_result_path: string;
  content_hash: string;
  content_length: number;
  image_count: number;
  updated_at: string;
};

function getBaseDir(): string {
  return path.resolve(process.cwd(), process.env.NAVER_IDEMPOTENCY_DIR ?? '.secrets/idempotency');
}

function getLockDir(): string {
  return path.join(getBaseDir(), 'locks');
}

function getStateDir(): string {
  return path.join(getBaseDir(), 'state');
}

function ensureDirs(): void {
  fs.mkdirSync(getLockDir(), { recursive: true });
  fs.mkdirSync(getStateDir(), { recursive: true });
}

export function hashSha256(text: string): string {
  return crypto.createHash('sha256').update(text).digest('hex');
}

export function generateRunId(now: Date = new Date()): string {
  const pad = (v: number) => String(v).padStart(2, '0');
  const yyyy = now.getFullYear();
  const mm = pad(now.getMonth() + 1);
  const dd = pad(now.getDate());
  const hh = pad(now.getHours());
  const mi = pad(now.getMinutes());
  const ss = pad(now.getSeconds());
  const rand = crypto.randomBytes(3).toString('hex');
  return `${yyyy}${mm}${dd}_${hh}${mi}${ss}_${rand}`;
}

export function deriveJobKey(input: {
  explicitJobKey?: string;
  telegramMessageId?: number;
  dirPath: string;
  mode: 'draft' | 'publish' | 'dry_run';
}): string {
  if (input.explicitJobKey?.trim()) return input.explicitJobKey.trim();
  if (typeof input.telegramMessageId === 'number') return `telegram:${input.telegramMessageId}`;
  const raw = `${path.resolve(input.dirPath)}|${input.mode}`;
  return `hash:${hashSha256(raw).slice(0, 20)}`;
}

function getKeyHash(jobKey: string): string {
  return hashSha256(jobKey).slice(0, 32);
}

function getStaleTtlMs(): number {
  const parsed = parseInt(process.env.NAVER_JOB_LOCK_TTL_MS ?? '1800000', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1800000;
}

export function acquireJobLock(jobKey: string, runId: string): {
  ok: true;
  handle: JobLockHandle;
} | {
  ok: false;
  reasonCode: 'DUP_RUN_DETECTED';
  message: string;
} {
  ensureDirs();
  const keyHash = getKeyHash(jobKey);
  const lockPath = path.join(getLockDir(), `${keyHash}.lock`);
  const lockToken = `${runId}:${process.pid}:${Date.now()}`;
  const payload: LockPayload = {
    job_key: jobKey,
    run_id: runId,
    lock_token: lockToken,
    created_at: new Date().toISOString(),
    pid: process.pid,
  };

  const tryCreate = (): boolean => {
    try {
      const fd = fs.openSync(lockPath, 'wx');
      fs.writeFileSync(fd, JSON.stringify(payload, null, 2), 'utf-8');
      fs.closeSync(fd);
      return true;
    } catch {
      return false;
    }
  };

  if (tryCreate()) {
    return {
      ok: true,
      handle: { keyHash, lockPath, lockToken },
    };
  }

  try {
    const stat = fs.statSync(lockPath);
    const ageMs = Date.now() - stat.mtimeMs;
    if (ageMs > getStaleTtlMs()) {
      fs.unlinkSync(lockPath);
      if (tryCreate()) {
        return {
          ok: true,
          handle: { keyHash, lockPath, lockToken },
        };
      }
    }
  } catch {
    // ignore and fall through
  }

  return {
    ok: false,
    reasonCode: 'DUP_RUN_DETECTED',
    message: `job lock already exists: ${lockPath}`,
  };
}

export function releaseJobLock(handle: JobLockHandle | null): void {
  if (!handle) return;
  try {
    if (!fs.existsSync(handle.lockPath)) return;
    const raw = fs.readFileSync(handle.lockPath, 'utf-8');
    const parsed = JSON.parse(raw) as Partial<LockPayload>;
    if (parsed.lock_token === handle.lockToken) {
      fs.unlinkSync(handle.lockPath);
    }
  } catch {
    // ignore lock cleanup failure
  }
}

function getStatePath(jobKey: string): string {
  return path.join(getStateDir(), `${getKeyHash(jobKey)}.json`);
}

export function readJobRunState(jobKey: string): JobRunState | null {
  ensureDirs();
  const statePath = getStatePath(jobKey);
  if (!fs.existsSync(statePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(statePath, 'utf-8')) as JobRunState;
  } catch {
    return null;
  }
}

export function writeJobRunState(state: JobRunState): void {
  ensureDirs();
  fs.writeFileSync(getStatePath(state.job_key), JSON.stringify(state, null, 2), 'utf-8');
}

export function ensureRunIdComment(markdownPath: string, runId: string): {
  runIdInFile: string;
  updated: boolean;
  rawMarkdown: string;
} {
  const raw = fs.readFileSync(markdownPath, 'utf-8');
  const match = raw.match(/<!--\s*RUN_ID:\s*([A-Za-z0-9_\-]+)\s*-->/);
  if (match) {
    return {
      runIdInFile: match[1],
      updated: false,
      rawMarkdown: raw,
    };
  }
  const next = `<!-- RUN_ID: ${runId} -->\n${raw}`;
  fs.writeFileSync(markdownPath, next, 'utf-8');
  return {
    runIdInFile: runId,
    updated: true,
    rawMarkdown: next,
  };
}

export function stripRunIdComments(markdown: string): string {
  return markdown.replace(/^\s*<!--\s*RUN_ID:\s*[A-Za-z0-9_\-]+\s*-->\s*\n?/gm, '');
}

export function computeMarkdownBodyHash(markdown: string): string {
  return hashSha256(stripRunIdComments(markdown).trim());
}

export function ensureRetryConsistency(input: {
  retryAttempt: number;
  state: JobRunState | null;
  runId: string;
  contentHash: string;
}): void {
  if (input.retryAttempt <= 0) return;
  if (!input.state) {
    throw new IdempotencyError(
      'RUN_ID_MISMATCH_RETRY_BLOCKED',
      `retry attempt=${input.retryAttempt} but no prior run state`,
    );
  }
  if (input.state.run_id !== input.runId) {
    throw new IdempotencyError(
      'RUN_ID_MISMATCH_RETRY_BLOCKED',
      `retry run_id mismatch expected=${input.state.run_id} actual=${input.runId}`,
    );
  }
  if (input.state.content_hash !== input.contentHash) {
    throw new IdempotencyError(
      'RUN_ID_MISMATCH_RETRY_BLOCKED',
      `retry content hash mismatch expected=${input.state.content_hash} actual=${input.contentHash}`,
    );
  }
}
