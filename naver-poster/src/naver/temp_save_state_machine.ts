import * as fs from 'fs';
import * as path from 'path';

export type DraftStageName =
  | 'openWriter'
  | 'ensureLoggedIn'
  | 'attachPlace'
  | 'insertBlocks'
  | 'clickTempSave'
  | 'waitTempSaveSuccess'
  | 'verifyDraftSaved';

export type DraftStageResult<T = unknown> = {
  stage: DraftStageName;
  startedAt: number;
  elapsedMs: number;
  success: boolean;
  timedOut?: boolean;
  reason_code?: string;
  debug_path?: string;
  data?: T;
  error?: string;
};

export class DraftStageTimeoutError extends Error {
  readonly stage: DraftStageName;
  readonly timeoutMs: number;

  constructor(stage: DraftStageName, timeoutMs: number) {
    super(`[STAGE_TIMEOUT] stage=${stage} timeout=${timeoutMs}ms`);
    this.stage = stage;
    this.timeoutMs = timeoutMs;
  }
}

export class DraftProgressWatchdog {
  private readonly silenceMs: number;
  private readonly onTimeout: (stage: string, silenceMs: number) => Promise<void> | void;
  private timer: ReturnType<typeof setInterval> | null = null;
  private lastHeartbeatAt: number = Date.now();
  private lastStage: string = 'init';
  private fired = false;

  constructor(
    silenceMs: number,
    onTimeout: (stage: string, silenceMs: number) => Promise<void> | void,
  ) {
    this.silenceMs = silenceMs;
    this.onTimeout = onTimeout;
  }

  heartbeat(stage: string): void {
    this.lastHeartbeatAt = Date.now();
    this.lastStage = stage;
  }

  start(): void {
    if (this.timer) return;
    this.heartbeat('watchdog_start');
    const tickMs = Math.max(50, Math.min(1000, Math.floor(this.silenceMs / 4)));
    this.timer = setInterval(async () => {
      if (this.fired) return;
      const silentFor = Date.now() - this.lastHeartbeatAt;
      if (silentFor < this.silenceMs) return;
      this.fired = true;
      await this.onTimeout(this.lastStage, silentFor);
    }, tickMs);
    this.timer.unref();
  }

  stop(): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null;
  }
}

export async function runDraftStage<T>(
  stage: DraftStageName,
  timeoutMs: number,
  heartbeat: (stage: string) => void,
  fn: () => Promise<T>,
  options?: {
    timeoutReasonCode?: string;
    onTimeout?: () => Promise<string | null | undefined> | string | null | undefined;
  },
): Promise<DraftStageResult<T>> {
  const startedAt = Date.now();
  heartbeat(stage);
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutHandle = setTimeout(() => {
      reject(new DraftStageTimeoutError(stage, timeoutMs));
    }, timeoutMs);
  });

  try {
    const data = await Promise.race([fn(), timeoutPromise]);
    return {
      stage,
      startedAt,
      elapsedMs: Date.now() - startedAt,
      success: true,
      data: data as T,
    };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    const timedOut = error instanceof DraftStageTimeoutError;
    let debugPath: string | undefined;
    if (timedOut && options?.onTimeout) {
      try {
        const value = await options.onTimeout();
        if (value) debugPath = value;
      } catch {
        // ignore timeout cleanup failure
      }
    }
    return {
      stage,
      startedAt,
      elapsedMs: Date.now() - startedAt,
      success: false,
      timedOut,
      reason_code: timedOut ? (options?.timeoutReasonCode ?? 'STAGE_TIMEOUT') : undefined,
      debug_path: debugPath,
      error: text,
    };
  } finally {
    if (timeoutHandle) clearTimeout(timeoutHandle);
  }
}

export function normalizeBlockSequenceForDraft<T extends { type: string }>(
  blocks: T[],
): { normalizedBlocks: T[]; syntheticTextInserted: boolean } {
  const normalizedBlocks = [...blocks];
  const hasText = normalizedBlocks.some((b) => b.type === 'text' || b.type === 'section_title');
  const hasImage = normalizedBlocks.some((b) => b.type === 'image');

  if (!hasText && hasImage) {
    normalizedBlocks.unshift({
      type: 'text',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      content: '사진과 함께 기록한 방문 메모입니다.',
    } as any);
    return { normalizedBlocks, syntheticTextInserted: true };
  }
  return { normalizedBlocks, syntheticTextInserted: false };
}

export type ImageFileInfo = {
  filePath: string;
  exists: boolean;
  sizeBytes: number;
  tooLarge: boolean;
};

export function buildImageUploadPlan(
  imagePaths: string[],
  largeThresholdBytes: number = 5 * 1024 * 1024,
): ImageFileInfo[] {
  return imagePaths.map((p) => {
    const abs = path.resolve(p);
    const exists = fs.existsSync(abs);
    const sizeBytes = exists ? fs.statSync(abs).size : 0;
    return {
      filePath: abs,
      exists,
      sizeBytes,
      tooLarge: sizeBytes > largeThresholdBytes,
    };
  });
}

export function isTempSaveSuccessSignal(rawText: string): boolean {
  const text = (rawText || '').replace(/\s+/g, ' ').trim();
  if (!text) return false;
  const patterns = [
    /임시\s*저장\s*완료/i,
    /임시\s*저장됨/i,
    /저장\s*완료/i,
    /저장되었습니다/i,
    /자동저장/i,
    /저장됨/i,
  ];
  return patterns.some((p) => p.test(text));
}

type TimeoutBudgetOptions = {
  fallbackSeconds?: number;
  minSeconds?: number;
  maxSeconds?: number;
  perTextBlockSeconds?: number;
  perImageBlockSeconds?: number;
};

/**
 * Insert-block 단계는 콘텐츠 볼륨(텍스트/이미지 개수)에 따라 소요 시간이 크게 달라진다.
 * 전체를 고정 30초로 제한하면 정상 업로드도 false timeout이 발생할 수 있어 동적 예산을 계산한다.
 */
export function computeInsertBlocksTimeoutSeconds(
  blocks: Array<{ type: string }>,
  options: TimeoutBudgetOptions = {},
): number {
  const fallbackSeconds = options.fallbackSeconds ?? 30;
  const minSeconds = options.minSeconds ?? 30;
  const maxSeconds = options.maxSeconds ?? 600;

  const imageUploadTimeoutMs = parseInt(process.env.NAVER_IMAGE_UPLOAD_TIMEOUT_MS ?? '20000', 10);
  const derivedPerImage = Math.ceil(imageUploadTimeoutMs / 1000) + 20;
  const perImageBlockSeconds = options.perImageBlockSeconds ?? Math.max(35, derivedPerImage);
  const perTextBlockSeconds = options.perTextBlockSeconds ?? 12;
  const baseSeconds = 20;

  if (!Array.isArray(blocks) || blocks.length === 0) {
    return Math.max(minSeconds, Math.min(maxSeconds, fallbackSeconds));
  }

  const textCount = blocks.filter((b) => b.type === 'text' || b.type === 'section_title').length;
  const imageCount = blocks.filter((b) => b.type === 'image').length;
  const computed = Math.ceil(baseSeconds + textCount * perTextBlockSeconds + imageCount * perImageBlockSeconds);
  const budget = Math.max(fallbackSeconds, computed);
  return Math.max(minSeconds, Math.min(maxSeconds, budget));
}
