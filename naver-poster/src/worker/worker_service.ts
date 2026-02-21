import * as fs from 'fs';
import * as path from 'path';
import { spawn } from 'child_process';

import * as log from '../utils/logger';
import {
  loadSessionCooldown,
  isCooldownActive,
  getSessionCooldownPath,
} from '../naver/session';
import { FileJobQueue } from './job_queue';
import {
  buildBlogResultMarkdown,
  parseTelegramRequest,
  TelegramClient,
} from './telegram_client';
import { FailureReasonCode, WorkerJob } from './types';

const DEFAULT_QUEUE_PATH = './.secrets/worker_job_queue.json';
const DEFAULT_TELEGRAM_STATE_PATH = './.secrets/telegram_worker_state.json';

type UploadExecutionResult = {
  ok: boolean;
  reasonCode?: FailureReasonCode;
  detail: string;
  artifactsDir?: string;
  stdout: string;
  stderr: string;
  requestId?: string;
  accountId?: string;
  verifiedVia?: string;
};

type WorkerDependencies = {
  executeUploadJob: (job: WorkerJob) => Promise<UploadExecutionResult>;
  notifyAdmin: (message: string) => Promise<void>;
  notifyUser: (chatId: string, message: string) => Promise<void>;
};

export type WorkerConfig = {
  queuePath?: string;
  pollSec: number;
  headless: boolean;
  resume: boolean;
  telegramToken?: string;
  adminChatId?: string;
};

function classifyUploadFailure(text: string): FailureReasonCode {
  if (/DUP_RUN_DETECTED|DRAFT_NOT_EMPTY_ABORT|RUN_ID_MISMATCH_RETRY_BLOCKED/i.test(text)) {
    return 'DUP_RUN_DETECTED';
  }
  if (/SESSION_PRECHECK_FAILED|SESSION_EXPIRED|login_redirect|BLOCKED_LOGIN|로그인 필요/i.test(text)) {
    return 'SESSION_EXPIRED';
  }
  if (/CAPTCHA|2FA|SECURITY_CHALLENGE|기기 인증|보안 확인|약관 동의/i.test(text)) {
    return 'SECURITY_CHALLENGE';
  }
  if (/EDITOR_READY_TIMEOUT|iframe_not_found|selector|button_not_found/i.test(text)) {
    return 'SELECTOR_BROKEN';
  }
  if (/timeout|net::|econn|network|dns|socket/i.test(text)) {
    return 'NETWORK_ERROR';
  }
  return 'NETWORK_ERROR';
}

function readTelegramOffset(statePath: string): number {
  try {
    if (!fs.existsSync(statePath)) return 0;
    const parsed = JSON.parse(fs.readFileSync(statePath, 'utf-8')) as { offset?: number };
    return Number(parsed.offset ?? 0);
  } catch {
    return 0;
  }
}

function writeTelegramOffset(statePath: string, offset: number): void {
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify({ offset }, null, 2), 'utf-8');
}

function createJobId(): string {
  const ts = new Date().toISOString().replace(/[-:.TZ]/g, '');
  const random = Math.random().toString(36).slice(2, 8);
  return `job_${ts}_${random}`;
}

function defaultUploadExecutorFactory(projectRoot: string): (job: WorkerJob) => Promise<UploadExecutionResult> {
  return async (job: WorkerJob): Promise<UploadExecutionResult> => {
    const artifactsDir = path.resolve(projectRoot, 'artifacts/worker_runs', job.id);
    fs.mkdirSync(artifactsDir, { recursive: true });
    const args = [
      path.resolve(projectRoot, 'dist/cli/post_to_naver.js'),
      `--dir=${job.dirPath}`,
      '--headless',
      job.mode === 'publish' ? '--publish' : '--draft',
    ];

    const { stdout, stderr, exitCode } = await new Promise<{ stdout: string; stderr: string; exitCode: number }>((resolve) => {
      const child = spawn(process.execPath, args, {
        cwd: projectRoot,
        env: {
          ...process.env,
          HEADLESS: 'true',
          NAVER_JOB_KEY: job.messageId ? `telegram:${job.messageId}` : `worker:${job.id}`,
          NAVER_TELEGRAM_MESSAGE_ID: job.messageId ? String(job.messageId) : '',
          NAVER_RETRY_ATTEMPT: String(job.attempts),
        },
      });
      const out: string[] = [];
      const err: string[] = [];
      child.stdout.on('data', (chunk) => out.push(String(chunk)));
      child.stderr.on('data', (chunk) => err.push(String(chunk)));
      child.on('close', (code) => {
        resolve({
          stdout: out.join(''),
          stderr: err.join(''),
          exitCode: Number(code ?? 1),
        });
      });
    });

    fs.writeFileSync(path.join(artifactsDir, 'stdout.log'), stdout, 'utf-8');
    fs.writeFileSync(path.join(artifactsDir, 'stderr.log'), stderr, 'utf-8');
    const marker = 'NAVER_POST_RESULT_JSON:';
    const reportLine = stdout.split('\n').find((line) => line.includes(marker)) || '';
    let requestId = '';
    let accountId = '';
    let verifiedVia = '';
    if (reportLine) {
      try {
        const raw = reportLine.slice(reportLine.indexOf(marker) + marker.length).trim();
        const report = JSON.parse(raw) as {
          request_id?: string;
          account_id?: string;
          reason_code?: string;
          draft_summary?: { verified_via?: string };
        };
        requestId = report.request_id ?? '';
        accountId = report.account_id ?? '';
        verifiedVia = report.draft_summary?.verified_via ?? '';
      } catch {
        // ignore report parse errors
      }
    }

    if (exitCode === 0) {
      return {
        ok: true,
        detail: 'upload_success',
        artifactsDir,
        stdout,
        stderr,
        requestId: requestId || undefined,
        accountId: accountId || undefined,
        verifiedVia: verifiedVia || undefined,
      };
    }
    const merged = `${stdout}\n${stderr}`;
    const reasonCode = classifyUploadFailure(merged);
    return {
      ok: false,
      reasonCode,
      detail: `upload_failed exit=${exitCode} reason=${reasonCode}`,
      artifactsDir,
      stdout,
      stderr,
      requestId: requestId || undefined,
      accountId: accountId || undefined,
      verifiedVia: verifiedVia || undefined,
    };
  };
}

export class WorkerService {
  private readonly config: WorkerConfig;
  private readonly queue: FileJobQueue;
  private readonly telegramClient: TelegramClient | null;
  private readonly statePath: string;
  private readonly deps: WorkerDependencies;
  private readonly projectRoot: string;

  constructor(config: WorkerConfig, deps?: Partial<WorkerDependencies>) {
    this.config = config;
    this.projectRoot = path.resolve(process.cwd());
    this.queue = new FileJobQueue(config.queuePath ?? DEFAULT_QUEUE_PATH);
    this.telegramClient = config.telegramToken ? new TelegramClient(config.telegramToken) : null;
    this.statePath = path.resolve(DEFAULT_TELEGRAM_STATE_PATH);

    const baseDeps: WorkerDependencies = {
      executeUploadJob: defaultUploadExecutorFactory(this.projectRoot),
      notifyAdmin: async (message: string) => {
        if (!this.telegramClient || !this.config.adminChatId) return;
        await this.telegramClient.sendMessage(this.config.adminChatId, message);
      },
      notifyUser: async (chatId: string, message: string) => {
        if (!this.telegramClient) return;
        await this.telegramClient.sendMessage(chatId, message);
      },
    };
    this.deps = { ...baseDeps, ...deps };
  }

  private async ingestTelegramUpdates(): Promise<void> {
    if (!this.telegramClient) return;
    const currentOffset = readTelegramOffset(this.statePath);
    const updates = await this.telegramClient.pollUpdates(currentOffset, this.config.pollSec);
    if (!updates.length) return;

    let maxOffset = currentOffset;
    for (const update of updates) {
      maxOffset = Math.max(maxOffset, update.update_id + 1);
      const message = update.message;
      if (!message) continue;
      const chatId = String(message.chat.id);
      const parsed = parseTelegramRequest(message.text ?? message.caption);
      const mode = parsed.mode === 'publish' ? 'publish' : 'draft';

      const jobId = createJobId();
      const dirPath = path.resolve('./data/telegram_jobs', jobId);
      const imagesDir = path.join(dirPath, 'images');
      fs.mkdirSync(imagesDir, { recursive: true });

      const photos = message.photo ?? [];
      const selectedPhoto = photos.length > 0 ? photos[photos.length - 1] : null;
      if (selectedPhoto) {
        const filePath = await this.telegramClient.getFilePath(selectedPhoto.file_id);
        await this.telegramClient.downloadFile(filePath, path.join(imagesDir, 'photo_1.jpg'));
      }

      const markdown = buildBlogResultMarkdown(parsed, selectedPhoto ? 1 : 0);
      fs.writeFileSync(path.join(dirPath, 'blog_result.md'), markdown, 'utf-8');
      fs.writeFileSync(path.join(dirPath, 'metadata.json'), JSON.stringify({
        store_name: parsed.storeName ?? null,
        source: 'telegram',
      }, null, 2), 'utf-8');

      const job = this.queue.enqueue({
        id: jobId,
        chatId,
        messageId: message.message_id,
        dirPath,
        mode: mode === 'publish' ? 'publish' : 'draft', // 기본 draft
      });
      await this.deps.notifyUser(chatId, `요청 접수됨: job=${job.id} mode=${job.mode} status=${job.status}`);
    }
    writeTelegramOffset(this.statePath, maxOffset);
  }

  private async blockJobForLogin(job: WorkerJob, reasonCode: FailureReasonCode, detail: string, artifactsDir?: string): Promise<void> {
    this.queue.updateJob(job.id, {
      status: 'BLOCKED_LOGIN',
      attempts: job.attempts + 1,
      reasonCode,
      lastError: detail,
      artifactsDir,
    });
    const guide = [
      '세션이 만료되었거나 보안확인이 필요합니다.',
      `job=${job.id} reason=${reasonCode}`,
      '해결:',
      '1) 서버에서 node dist/cli/post_to_naver.js --interactiveLogin 실행',
      '2) 로그인 완료 후 Enter',
      '3) 큐 재개: node dist/cli/worker.js --resume (또는 자동 재검사 대기)',
    ].join('\n');
    await this.deps.notifyAdmin(guide);
    await this.deps.notifyUser(job.chatId, `업로드 보류(BLOCKED_LOGIN): ${reasonCode}\n관리자 재로그인 후 자동 재시도됩니다.`);
  }

  async resumeBlockedJobsIfSessionReady(): Promise<number> {
    const blocked = this.queue.listByStatus('BLOCKED_LOGIN');
    if (!blocked.length) return 0;

    // 쿨다운 활성 중이면 resume 스킵
    const cooldownPath = getSessionCooldownPath();
    const cooldown = loadSessionCooldown(cooldownPath);
    if (isCooldownActive(cooldown)) {
      log.info(`[worker] resumeBlocked: cooldown 활성 until=${new Date(cooldown.cooldownUntilTs).toISOString()} → 스킵`);
      return 0;
    }

    // captchaFallbackAttempted=true 제외, 나머지만 PENDING 전환
    let resumed = 0;
    for (const job of blocked) {
      if (job.captchaFallbackAttempted) {
        log.info(`[worker] resumeBlocked: job=${job.id} captchaFallbackAttempted=true → 스킵`);
        continue;
      }
      this.queue.updateJob(job.id, {
        status: 'PENDING',
        lastError: undefined,
        reasonCode: undefined,
      });
      resumed++;
    }

    if (resumed > 0) {
      await this.deps.notifyAdmin(`세션 복구 감지: BLOCKED_LOGIN ${resumed}건을 PENDING으로 전환했습니다.`);
    }
    return resumed;
  }

  async processNextJob(): Promise<boolean> {
    const job = this.queue.getNextPending();
    if (!job) return false;
    this.queue.updateJob(job.id, { status: 'PROCESSING' });

    const execution = await this.deps.executeUploadJob(job);
    if (execution.ok) {
      this.queue.updateJob(job.id, {
        status: 'COMPLETED',
        attempts: job.attempts + 1,
        lastError: undefined,
        reasonCode: undefined,
        artifactsDir: execution.artifactsDir,
      });
      await this.deps.notifyUser(
        job.chatId,
        `업로드 성공: job=${job.id} mode=${job.mode} requestId=${execution.requestId ?? 'n/a'} accountId=${execution.accountId ?? 'n/a'} verifiedVia=${execution.verifiedVia ?? 'n/a'}`,
      );
      return true;
    }

    // CAPTCHA/보안 감지 → interactiveLogin fallback 없이 즉시 BLOCKED_LOGIN
    // 복구는 CLI 수동 실행: node dist/cli/post_to_naver.js --interactiveLogin
    if (execution.reasonCode === 'SECURITY_CHALLENGE') {
      log.error(`[worker] CAPTCHA/보안 감지: job=${job.id} → 즉시 BLOCKED_LOGIN (운영자 수동 개입 필요)`);
      await this.blockJobForLogin(
        job,
        'SECURITY_CHALLENGE',
        `CAPTCHA/보안 감지 — 수동 interactiveLogin 필요: node dist/cli/post_to_naver.js --interactiveLogin`,
        execution.artifactsDir,
      );
      return true;
    }

    if (execution.reasonCode === 'SESSION_EXPIRED') {
      await this.blockJobForLogin(job, execution.reasonCode, execution.detail, execution.artifactsDir);
      return true;
    }

    this.queue.updateJob(job.id, {
      status: 'FAILED',
      attempts: job.attempts + 1,
      reasonCode: execution.reasonCode,
      lastError: execution.detail,
      artifactsDir: execution.artifactsDir,
    });
    await this.deps.notifyUser(job.chatId, `업로드 실패: ${execution.reasonCode ?? 'UNKNOWN'} (${execution.detail})`);
    return true;
  }

  async runOnce(): Promise<void> {
    await this.ingestTelegramUpdates();
    if (this.config.resume) {
      await this.resumeBlockedJobsIfSessionReady();
    }
    await this.processNextJob();
  }

  async runLoop(): Promise<void> {
    if (!this.config.headless) {
      throw new Error('worker는 무인 운영 전용이며 headless=false를 허용하지 않습니다.');
    }
    log.info(`[worker] started headless=${this.config.headless} pollSec=${this.config.pollSec} resume=${this.config.resume}`);
    while (true) {
      try {
        await this.runOnce();
      } catch (error) {
        log.error(`[worker] loop error: ${error}`);
      }
      await new Promise((resolve) => setTimeout(resolve, Math.max(1000, this.config.pollSec * 1000)));
    }
  }
}
