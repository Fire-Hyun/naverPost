#!/usr/bin/env node

import * as path from 'path';
import * as fs from 'fs';
import { spawnSync } from 'child_process';
import { Command } from 'commander';
import * as dotenv from 'dotenv';
import type { Frame, Page } from 'playwright';

import * as log from '../utils/logger';
import { attachPageDebugCollectors } from '../utils/logger';
import { createDebugRunDir, ensureDebugRootDir } from '../common/debug_paths';
import { loadPostDirectory, PostDirectory } from '../utils/parser';
import {
  loadOrCreateSession,
  interactiveLogin,
  autoLogin,
  SessionOptions,
  preflightSessionForUpload,
  formatSessionPreflightFailure,
  recoverExpiredSession,
  isLoginRedirectUrl,
  SessionBlockedError,
  detectLoginState,
  ensureLoggedIn,
  clearSessionCooldown,
  getSessionCooldownStatus,
  formatInteractiveLoginGuide,
  resolveProfileDir,
  ensureProfileDir,
  getSessionBackendLabel,
} from '../naver/session';
import {
  EditorContext,
  getEditorFrame,
  getEditorFrameOrThrow,
  getLastEditorReadyProbeSummary,
  waitForEditorReady,
  inputTitle,
  writeTitleThenBodyViaKeyboard,
  insertBlocksSequentially,
  verifyImageReferencesInEditor,
  getEditorImageState,
  clickTempSave,
  selectorHealthcheck,
  EditorIframeNotFoundError,
} from '../naver/editor';
import { clickPublish, verifyPublished } from '../naver/publisher';
import { stabilizePageState, verifyTempSaveWithRetry } from '../naver/temp_save_verifier';
import { attach_place_in_editor } from '../naver/place';
import { getPlaceFromImages } from '../naver/exif';
import type { PostBlock } from '../utils/parser';
import { organizeTopics } from '../utils/topic_organizer';
import { placeImagesBySection } from '../utils/image_placer';
import { splitSectionIntoTextChunks } from '../utils/section_interleave';
import { buildRenderPlanItems, type RenderChunk, type ChunkAnchorPlacement } from '../utils/render_plan';
import { buildPostPlan, createPostPlanState } from '../utils/post_plan';
import {
  computeInsertBlocksTimeoutSeconds,
  DraftProgressWatchdog,
  buildImageUploadPlan,
  normalizeBlockSequenceForDraft,
  runDraftStage,
} from '../naver/temp_save_state_machine';
import { collectTimeoutDebugArtifacts } from '../naver/timeout_debug';

function parseBoolEnv(name: string, defaultValue: boolean): boolean {
  const raw = process.env[name];
  if (!raw) return defaultValue;
  return raw.toLowerCase() === 'true';
}

function resolvePostDirInput(inputDir: string): string {
  const raw = inputDir.trim();
  const direct = path.resolve(raw);
  if (fs.existsSync(direct)) return direct;

  const candidates = [
    path.resolve(process.cwd(), 'data', raw),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      log.info(`[dir] 자동 경로 해석: ${raw} -> ${candidate}`);
      return candidate;
    }
  }
  return direct;
}

function classifyExecutionFailure(error: unknown): { category: 'a' | 'b' | 'c' | 'd' | 'unknown'; reason: string } {
  if (error instanceof EditorIframeNotFoundError) {
    return { category: 'd', reason: 'selector_changed_or_editor_not_ready' };
  }
  if (error instanceof SessionBlockedError) {
    if (['CAPTCHA_DETECTED', 'TWO_FACTOR_REQUIRED', 'SECURITY_CONFIRM_REQUIRED', 'AGREEMENT_REQUIRED'].includes(error.reason)) {
      return { category: 'c', reason: error.reason };
    }
    return { category: 'b', reason: error.reason };
  }
  const message = String((error as any)?.message ?? error ?? '');
  if (/\[WSLG_UNAVAILABLE\]|\[ENV_NO_GUI\]|interactiveLogin.*headful|브라우저 모드:\s*headless/i.test(message)) {
    return { category: 'a', reason: 'gui_unavailable_or_headless_forced' };
  }
  if (/SESSION_PRECHECK_FAILED|SESSION_EXPIRED_OR_MISSING|세션|쿠키 무효|만료/i.test(message)) {
    return { category: 'b', reason: 'session_expired_or_invalid' };
  }
  if (/CAPTCHA|2FA|보안|추가 인증|약관|AGREEMENT_REQUIRED|TWO_FACTOR_REQUIRED|SECURITY_CONFIRM_REQUIRED/i.test(message)) {
    return { category: 'c', reason: 'security_challenge_or_2fa' };
  }
  if (/EDITOR_READY_TIMEOUT|iframe_not_found|selector|에디터 로딩 실패/i.test(message)) {
    return { category: 'd', reason: 'selector_changed_or_editor_not_ready' };
  }
  if (/VERIFICATION_FAILED_|VERIFICATION_FAILED|VERIFICATIONFAILED|text_block_fail|텍스트 블록 최종 실패/i.test(message)) {
    const match = message.match(/VERIFICATION_FAILED_[A-Z_]+/);
    return { category: 'd', reason: match?.[0]?.toLowerCase() ?? 'verification_failed' };
  }
  if (/INPUT_NOT_REFLECTED|FOCUS_FAILED|STALE_ELEMENT|EDITOR_AREA_NOT_FOUND/i.test(message)) {
    return { category: 'd', reason: 'editor_input_or_focus_failure' };
  }
  if (/IMAGE_LIST_EMPTY|IMAGE_FILE_NOT_FOUND|IMAGE_UPLOAD_UI_FAILED|IMAGE_UPLOAD_NO_INSERT|IMAGE_UPLOAD_STUCK|IMAGE_UPLOAD_DUPLICATED|DUP_TEXT_BY_RETRY|DUP_IMG_BY_RETRY/i.test(message)) {
    const matched = message.match(/IMAGE_[A-Z_]+/);
    return { category: 'd', reason: (matched?.[0] ?? 'image_upload_failure').toLowerCase() };
  }
  return { category: 'unknown', reason: 'unclassified' };
}

function buildSectionBlocks(
  sections: Array<{ title: string; paragraphs: string[] }>,
  placements: Array<{ imageIndex: number; sectionIndex: number; paragraphIndex: number }>,
): PostBlock[] {
  const nextChunkRef = { value: 1 };
  const chunksBySection = new Map<number, Array<{ chunkId: string; content: string }>>();
  const sectionImageCount = new Map<number, number>();
  const sectionCursor = new Map<number, number>();
  const anchorPlacements: ChunkAnchorPlacement[] = [];

  for (const placement of placements) {
    sectionImageCount.set(
      placement.sectionIndex,
      (sectionImageCount.get(placement.sectionIndex) ?? 0) + 1,
    );
  }

  for (let si = 0; si < sections.length; si++) {
    const section = sections[si];
    const desiredChunks = Math.max((sectionImageCount.get(si) ?? 0) + 1, 1);
    const chunks = splitSectionIntoTextChunks(section, {
      sentencesPerChunkMin: 1,
      sentencesPerChunkMax: 5,
      desiredTextChunks: desiredChunks,
      nextChunkNumberRef: nextChunkRef,
    });
    chunksBySection.set(si, chunks);
    sectionCursor.set(si, 0);
  }

  for (const placement of placements) {
    const chunks = chunksBySection.get(placement.sectionIndex) ?? [];
    if (chunks.length === 0) {
      anchorPlacements.push({ imageIndex: placement.imageIndex, chunkId: null });
      continue;
    }
    const cursor = sectionCursor.get(placement.sectionIndex) ?? 0;
    const anchorChunk = chunks[Math.min(cursor, chunks.length - 1)];
    anchorPlacements.push({ imageIndex: placement.imageIndex, chunkId: anchorChunk.chunkId });
    sectionCursor.set(placement.sectionIndex, cursor + 1);
  }

  const orderedChunks: RenderChunk[] = [];
  for (let si = 0; si < sections.length; si++) {
    const section = sections[si];
    const chunks = chunksBySection.get(si) ?? [];
    for (const chunk of chunks) {
      orderedChunks.push({
        chunkId: chunk.chunkId,
        sectionIndex: si,
        sectionTitle: section.title,
        content: chunk.content,
      });
    }
  }

  return buildRenderPlanItems(orderedChunks, anchorPlacements);
}

// ────────────────────────────────────────────
// 환경변수 로드
// ────────────────────────────────────────────
const envPath = path.resolve(process.cwd(), '.env');
if (fs.existsSync(envPath)) {
  dotenv.config({ path: envPath });
}

// ────────────────────────────────────────────
// 설정
// ────────────────────────────────────────────
function getConfig(overrides?: {
  profileDir?: string;
}) {
  const userDataDir = resolveProfileDir({
    profileDir: overrides?.profileDir,
    userDataDir: process.env.NAVER_USER_DATA_DIR ?? './.secrets/naver_user_data_dir',
  });
  const storageStatePath = process.env.NAVER_STORAGE_STATE_PATH
    ?? path.join(userDataDir, 'session_storage_state.json');
  return {
    blogId: process.env.NAVER_BLOG_ID ?? 'jun12310',
    writeUrl:
      process.env.NAVER_WRITE_URL ??
      `https://blog.naver.com/${process.env.NAVER_BLOG_ID ?? 'jun12310'}?Redirect=Write&`,
    profileDir: userDataDir,
    userDataDir,
    storageStatePath,
    headless: process.env.HEADLESS !== 'false',  // 기본 headless=true
    slowMo: parseInt(process.env.SLOW_MO ?? '0', 10),
    artifactsDir: process.env.ARTIFACTS_DIR ?? './artifacts',
    kakaoApiKey: process.env.KAKAO_REST_API_KEY,
    placeAttachRequired: (process.env.NAVER_PLACE_ATTACH_REQUIRED || 'false').toLowerCase() === 'true',
  };
}

// ────────────────────────────────────────────
// 프로세스 워치독 (전체 파이프라인 타임아웃)
// ────────────────────────────────────────────
const PROCESS_WATCHDOG_SECONDS = Math.max(
  600,
  parseInt(process.env.NAVER_PROCESS_WATCHDOG_SECONDS ?? '900', 10),
);
const SILENCE_WATCHDOG_SECONDS = parseInt(process.env.NAVER_SILENCE_WATCHDOG_SECONDS ?? '60', 10);
const STEP_TIMEOUT_SECONDS = parseInt(process.env.NAVER_STEP_TIMEOUT_SECONDS ?? '30', 10);
const SESSION_PREFLIGHT_TIMEOUT_SECONDS = parseInt(
  process.env.NAVER_SESSION_PREFLIGHT_TIMEOUT_SECONDS ?? '90',
  10,
);
const DRAFT_CLICK_TIMEOUT_MS = parseInt(process.env.NAVER_DRAFT_CLICK_TIMEOUT_MS ?? '45000', 10);
const DRAFT_VERIFY_TIMEOUT_MS = parseInt(process.env.NAVER_DRAFT_VERIFY_TIMEOUT_MS ?? '45000', 10);
const TEMP_SAVE_STAGE_TIMEOUT_MS = Math.max(
  100,
  Math.min(30_000, parseInt(process.env.NAVER_TEMP_SAVE_STAGE_TIMEOUT_MS ?? '30000', 10)),
);
let watchdogTimer: ReturnType<typeof setTimeout> | null = null;
let silenceWatchdogTimer: ReturnType<typeof setInterval> | null = null;
let lastActivityTimestamp = Date.now();
let lastActivityLabel = 'init';
let currentStage = 'init';
let stageWatchdog: DraftProgressWatchdog | null = null;
const DEBUG_COLLECTION_TIMEOUT_MS = parseInt(
  process.env.NAVER_DEBUG_COLLECTION_TIMEOUT_MS ?? '8000',
  10,
);
const EDITOR_READY_ALLOW_RELOAD_RECOVERY =
  (process.env.NAVER_EDITOR_READY_ALLOW_RELOAD_RECOVERY ?? 'false').toLowerCase() === 'true';

function touchWatchdog(label: string): void {
  lastActivityTimestamp = Date.now();
  lastActivityLabel = label;
  stageWatchdog?.heartbeat(label);
}

function logTiming(step: string, startedAtMs: number): void {
  log.info(`[timing] step=${step} elapsed=${((Date.now() - startedAtMs) / 1000).toFixed(1)}s`);
}

function setCurrentStage(stage: string): void {
  currentStage = stage;
  touchWatchdog(stage);
}

async function runWithTimeout<T>(
  label: string,
  ms: number,
  fn: () => Promise<T>,
): Promise<T | null> {
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutHandle = setTimeout(() => {
      reject(new Error(`timeout:${label}:${ms}ms`));
    }, ms);
  });

  try {
    return (await Promise.race([fn(), timeoutPromise])) as T;
  } catch (error) {
    log.warn(`[debug] ${label} failed: ${error}`);
    return null;
  } finally {
    if (timeoutHandle) clearTimeout(timeoutHandle);
  }
}

async function collectTimeoutDebug(
  page: Page | null,
  frame: Frame | null,
  reason: string,
  loginProbe?: Record<string, unknown> | null,
  iframeProbe?: Record<string, unknown> | null,
  loginState?: Record<string, unknown> | null,
): Promise<string | null> {
  try {
    const result = await collectTimeoutDebugArtifacts({
      page,
      frame,
      reason,
      currentStage,
      lastActivityLabel,
      lastActivityAgeMs: Date.now() - lastActivityTimestamp,
      watchdogLimitSeconds: PROCESS_WATCHDOG_SECONDS,
      silenceWatchdogSeconds: SILENCE_WATCHDOG_SECONDS,
      editorReadyProbe: getLastEditorReadyProbeSummary(),
      loginProbe: loginProbe ?? null,
      iframeProbe: iframeProbe ?? null,
      loginState: loginState ?? null,
      debugRootDir: ensureDebugRootDir('navertimeoutdebug'),
    });
    log.error(`[watchdog] 디버그 아티팩트 저장: ${result.debugDir}`);
    return result.debugDir;
  } catch (e) {
    log.error(`[watchdog] 디버그 수집 실패: ${e}`);
    try {
      const fallbackDir = createDebugRunDir('navertimeoutdebug');
      const failReport = {
        reason,
        timestamp: new Date().toISOString(),
        capture_errors: [{ step: 'collect_timeout_debug', type: 'collect_timeout_debug_failed', message: String(e) }],
      };
      fs.writeFileSync(path.join(fallbackDir, 'timeout_report.json'), JSON.stringify(failReport, null, 2), 'utf-8');
      return fallbackDir;
    } catch {
      // ignore secondary failure
    }
    return null;
  }
}

async function collectTimeoutDebugSafe(
  page: Page | null,
  frame: Frame | null,
  reason: string,
  loginProbe?: Record<string, unknown> | null,
  iframeProbe?: Record<string, unknown> | null,
  loginState?: Record<string, unknown> | null,
): Promise<string | null> {
  return await runWithTimeout('collect_timeout_debug', DEBUG_COLLECTION_TIMEOUT_MS, () =>
    collectTimeoutDebug(page, frame, reason, loginProbe, iframeProbe, loginState),
  );
}

function startWatchdogs(pageRef: () => Page | null, frameRef: () => Frame | null): void {
  watchdogTimer = setTimeout(async () => {
    const elapsed = ((Date.now() - lastActivityTimestamp) / 1000).toFixed(1);
    log.error(
      `[watchdog] 프로세스 전체 타임아웃 (${PROCESS_WATCHDOG_SECONDS}s), stage=${currentStage}, last_activity=${lastActivityLabel}, activity_age=${elapsed}s`,
    );
    setTimeout(() => process.exit(1), DEBUG_COLLECTION_TIMEOUT_MS + 1000).unref();
    void collectTimeoutDebugSafe(pageRef(), frameRef(), `process_watchdog_${PROCESS_WATCHDOG_SECONDS}s`)
      .finally(() => process.exit(1));
  }, PROCESS_WATCHDOG_SECONDS * 1000);
  watchdogTimer.unref();

  silenceWatchdogTimer = setInterval(async () => {
    const silenceMs = Date.now() - lastActivityTimestamp;
    if (silenceMs < SILENCE_WATCHDOG_SECONDS * 1000) return;
    log.error(
      `[watchdog] 무응답 감지 (${SILENCE_WATCHDOG_SECONDS}s), stage=${currentStage}, last_activity=${lastActivityLabel}`,
    );
    setTimeout(() => process.exit(1), DEBUG_COLLECTION_TIMEOUT_MS + 1000).unref();
    void collectTimeoutDebugSafe(pageRef(), frameRef(), `silence_watchdog_${SILENCE_WATCHDOG_SECONDS}s`)
      .finally(() => process.exit(1));
  }, 5000);
  silenceWatchdogTimer.unref();

  stageWatchdog = new DraftProgressWatchdog(SILENCE_WATCHDOG_SECONDS * 1000, async (stage, silentMs) => {
    log.error(`[watchdog] stage progress watchdog timeout stage=${stage} silent_ms=${silentMs}`);
    setTimeout(() => process.exit(1), DEBUG_COLLECTION_TIMEOUT_MS + 1000).unref();
    void collectTimeoutDebugSafe(pageRef(), frameRef(), `stage_watchdog_${stage}_${silentMs}ms`)
      .finally(() => process.exit(1));
  });
  stageWatchdog.start();
}

function stopWatchdogs(): void {
  if (watchdogTimer) {
    clearTimeout(watchdogTimer);
    watchdogTimer = null;
  }
  if (silenceWatchdogTimer) {
    clearInterval(silenceWatchdogTimer);
    silenceWatchdogTimer = null;
  }
  if (stageWatchdog) {
    stageWatchdog.stop();
    stageWatchdog = null;
  }
  log.setLogActivityHook(null);
}

async function withStageTimeout<T>(
  stage: string,
  timeoutSeconds: number,
  pageRef: () => Page | null,
  frameRef: () => Frame | null,
  fn: () => Promise<T>,
): Promise<T> {
  const stageStarted = Date.now();
  setCurrentStage(stage);
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutHandle = setTimeout(() => {
      const error = new Error(`[STAGE_TIMEOUT] stage=${stage} exceeded ${timeoutSeconds}s`);
      void collectTimeoutDebugSafe(pageRef(), frameRef(), `stage_timeout_${stage}_${timeoutSeconds}s`);
      reject(error);
    }, timeoutSeconds * 1000);
  });

  try {
    const result = await Promise.race([fn(), timeoutPromise]);
    logTiming(stage, stageStarted);
    return result as T;
  } finally {
    if (timeoutHandle) clearTimeout(timeoutHandle);
  }
}

type PipelineStatus = 'success' | 'failed' | 'partial' | 'skipped' | 'warning';

interface PipelineStep {
  stage: string;
  status: PipelineStatus;
  message: string;
  started_at?: string;
  duration_ms?: number;
  data?: Record<string, unknown>;
}

interface PostingPipelineReport {
  schema_version: string;
  request_id?: string;
  account_id?: string;
  storage_state_path?: string;
  mode: 'draft' | 'publish' | 'dry_run';
  started_at: string;
  finished_at: string;
  duration_ms: number;
  directory: string;
  title: string;
  steps: {
    A: PipelineStep;
    B: PipelineStep;
    C: PipelineStep;
    D: PipelineStep;
    E: PipelineStep;
    F: PipelineStep;
    G: PipelineStep;
  };
  image_summary: {
    requested_count: number;
    uploaded_count: number;
    missing_count: number;
    editor_image_count: number;
    status: 'not_requested' | 'full' | 'partial' | 'none';
    sample_refs: string[];
  };
  draft_summary: {
    success: boolean;
    verified_via?: string;
    failure_reason?: string;
  };
  overall_status: 'SUCCESS_FULL' | 'SUCCESS_PARTIAL_IMAGES' | 'SUCCESS_TEXT_ONLY' | 'SUCCESS_WITH_IMAGE_VERIFY_WARNING' | 'FAILED';
}

function emitReport(report: PostingPipelineReport): void {
  log.info(`NAVER_POST_RESULT_JSON:${JSON.stringify(report)}`);
}

// ────────────────────────────────────────────
// 장소명 결정 로직
// ────────────────────────────────────────────
async function resolvePlaceInput(
  cliPlaceName: string | undefined,
  cliRegionHint: string | undefined,
  postDir: PostDirectory,
  kakaoApiKey: string | undefined
): Promise<{ storeName: string | null; regionHint?: string }> {
  const resolvedRegionHint = cliRegionHint || postDir.metadata?.regionHint;

  // 1) CLI 인자 우선
  if (cliPlaceName) {
    log.info(`장소명 (CLI 인자): "${cliPlaceName}"`);
    return { storeName: cliPlaceName, regionHint: resolvedRegionHint };
  }

  // 2) 메타데이터에서 상호명 추출
  if (postDir.metadata) {
    if (postDir.metadata.storeName) {
      log.info(`장소명 (메타데이터 store_name): "${postDir.metadata.storeName}"`);
      return { storeName: postDir.metadata.storeName, regionHint: resolvedRegionHint };
    }

    // 해시태그에서 상호명 추출
    const tags = postDir.metadata.hashtags ?? [];
    for (const tag of tags) {
      const names = tag.match(/#([가-힣A-Za-z0-9]+)/g);
      if (names && names.length > 0) {
        const name = names[0].replace('#', '');
        log.info(`장소명 (해시태그): "${name}"`);
        return { storeName: name, regionHint: resolvedRegionHint };
      }
    }

    // placeName 필드
    if (postDir.metadata.placeName) {
      log.info(`장소명 (메타데이터): "${postDir.metadata.placeName}"`);
      return { storeName: postDir.metadata.placeName, regionHint: resolvedRegionHint };
    }
  }

  // 3) 이미지 EXIF에서 GPS → 역지오코딩
  if (postDir.imagePaths.length > 0) {
    const placeInfo = await getPlaceFromImages(postDir.imagesDir, kakaoApiKey);
    if (placeInfo.address) {
      log.info(`장소명 (EXIF GPS): "${placeInfo.address}"`);
      return { storeName: placeInfo.address, regionHint: resolvedRegionHint };
    }
    if (placeInfo.coords) {
      log.info(`GPS 좌표만 발견: ${placeInfo.coords.latitude}, ${placeInfo.coords.longitude}`);
      log.warn('역지오코딩 API 키가 없어 주소 변환 불가');
    }
  }

  // 4) 디렉토리명에서 상호명 추출: 20260212(장어) → 장어
  const dirName = path.basename(postDir.dirPath);
  const match = dirName.match(/\(([^)]+)\)/);
  if (match) {
    const name = match[1];
    if (name !== '기타' && name.length >= 2) {
      log.info(`장소명 (디렉토리명): "${name}"`);
      return { storeName: name, regionHint: resolvedRegionHint };
    }
  }

  log.warn('장소명을 결정할 수 없습니다. --placeName 인자를 사용하세요.');
  return { storeName: null, regionHint: resolvedRegionHint };
}

// ────────────────────────────────────────────
// 메인 포스팅 워크플로우
// ────────────────────────────────────────────
async function runPosting(options: {
  dir: string;
  placeName?: string;
  regionHint?: string;
  dryRun: boolean;
  publish: boolean;
  healthcheck: boolean;
  profileDir?: string;
}): Promise<PostingPipelineReport> {
  const config = getConfig({ profileDir: options.profileDir });
  const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const accountId = process.env.NAVER_ID?.trim() || config.blogId;
  process.env.NAVER_REQUEST_ID = requestId;
  process.env.NAVER_ACCOUNT_ID = accountId;
  const storageStateMtime = fs.existsSync(config.storageStatePath)
    ? fs.statSync(config.storageStatePath).mtime.toISOString()
    : 'missing';
  const startTime = Date.now();
  const TOTAL_STEPS = 7;
  const stepTimeoutSeconds = Math.max(10, STEP_TIMEOUT_SECONDS);
  let currentPage: Page | null = null;
  let currentFrame: Frame | null = null;

  log.setLogActivityHook((msg) => {
    if (!msg.startsWith('[watchdog]')) {
      touchWatchdog('log_activity');
    }
  });

  log.info('========================================');
  log.info(`  requestId: ${requestId}`);
  log.info(`  accountId: ${accountId}`);
  log.info(`  storageStatePath: ${config.storageStatePath}`);
  log.info(`  storageStateMtime: ${storageStateMtime}`);
  const headerMessage = options.publish ? '  네이버 블로그 발행 자동화' : '  네이버 블로그 임시저장 자동화';
  log.info(headerMessage);
  log.info(`  워치독: ${PROCESS_WATCHDOG_SECONDS}초`);
  log.info(`  무응답 워치독: ${SILENCE_WATCHDOG_SECONDS}초`);
  log.info(`  단계 타임아웃: ${stepTimeoutSeconds}초`);
  log.info(`  세션 사전검증 타임아웃: ${SESSION_PREFLIGHT_TIMEOUT_SECONDS}초`);
  log.info(`  임시저장 클릭 타임아웃: ${DRAFT_CLICK_TIMEOUT_MS}ms`);
  log.info(`  임시저장 검증 타임아웃: ${DRAFT_VERIFY_TIMEOUT_MS}ms`);
  log.info(`  임시저장 stage 하드 타임아웃: ${TEMP_SAVE_STAGE_TIMEOUT_MS}ms`);
  log.info('========================================');
  setCurrentStage('pipeline_start');

  const startedAtIso = new Date(startTime).toISOString();
  const defaultReport = (message: string): PostingPipelineReport => ({
    schema_version: '1.0',
    request_id: requestId,
    account_id: accountId,
    storage_state_path: config.storageStatePath,
    mode: options.publish ? 'publish' : options.dryRun ? 'dry_run' : 'draft',
    started_at: startedAtIso,
    finished_at: new Date().toISOString(),
    duration_ms: Date.now() - startTime,
    directory: path.basename(options.dir),
    title: '',
    steps: {
      A: { stage: 'Step A: telegram_image_receive_download', status: 'failed', message },
      B: { stage: 'Step B: image_preprocessing', status: 'failed', message },
      C: { stage: 'Step C: naver_image_upload', status: 'failed', message },
      D: { stage: 'Step D: attach_resource_id_capture', status: 'failed', message },
      E: { stage: 'Step E: body_insert_image_reference', status: 'failed', message },
      F: { stage: 'Step F: draft_save_call', status: 'failed', message },
      G: { stage: 'Step G: post_save_image_reference_verification', status: 'failed', message },
    },
    image_summary: {
      requested_count: 0,
      uploaded_count: 0,
      missing_count: 0,
      editor_image_count: 0,
      status: 'not_requested',
      sample_refs: [],
    },
    draft_summary: {
      success: false,
      failure_reason: message,
    },
    overall_status: 'FAILED',
  });

  // Step 1: 포스트 데이터 로드
  log.step(1, TOTAL_STEPS, '포스트 데이터 로드');
  let stepStart = Date.now();
  let postDir: PostDirectory;
  try {
    postDir = await withStageTimeout(
      'post_data_load',
      stepTimeoutSeconds,
      () => currentPage,
      () => currentFrame,
      async () => loadPostDirectory(options.dir),
    );
  } catch (e: any) {
    throw new Error(`포스트 로드 실패: ${e.message}`);
  }

  const report: PostingPipelineReport = defaultReport('초기화');
  report.title = postDir.parsed.title;
  report.image_summary.requested_count = postDir.imagePaths.length;
  report.steps.A = {
    stage: 'Step A: telegram_image_receive_download',
    status: postDir.imagePaths.length > 0 ? 'success' : 'skipped',
    message: postDir.imagePaths.length > 0
      ? `텔레그램 이미지 파일 존재 확인 (${postDir.imagePaths.length}개)`
      : '이미지 없음',
    started_at: new Date(stepStart).toISOString(),
    duration_ms: Date.now() - stepStart,
    data: {
      image_count: postDir.imagePaths.length,
      note: 'CLI 단계에서는 telegram file_id/download URL을 사용할 수 없어 로컬 파일 기준으로 검증',
    },
  };
  report.steps.B = {
    stage: 'Step B: image_preprocessing',
    status: 'success',
    message: '이미지 확장자/파일 크기 사전 점검 완료',
    started_at: new Date().toISOString(),
    duration_ms: 0,
  };

  // Step 2: 세션 로드 및 에디터 진입
  stepStart = Date.now();
  log.step(2, TOTAL_STEPS, '브라우저 세션 로드 및 에디터 진입');
  const sessionOpts: SessionOptions = {
    profileDir: config.profileDir,
    userDataDir: config.userDataDir,
    storageStatePath: config.storageStatePath,
    headless: config.headless,
    slowMo: config.slowMo,
  };

  log.info('[timing] step=browser_launch_start elapsed=0.0s');
  let session: Awaited<ReturnType<typeof loadOrCreateSession>>;
  try {
    session = await withStageTimeout(
      'browser_launch_and_session_load',
      stepTimeoutSeconds,
      () => currentPage,
      () => currentFrame,
      async () => loadOrCreateSession(sessionOpts, config.writeUrl),
    );
  } catch (e) {
    stopWatchdogs();
    throw e;
  }
  const { page, context } = session;
  currentPage = page;
  attachPageDebugCollectors(page);

  startWatchdogs(() => currentPage, () => currentFrame);
  log.info('[timing] step=browser_launch_complete elapsed=0.0s');

  try {
    const sessionPreflight = await withStageTimeout(
      'session_preflight',
      Math.max(stepTimeoutSeconds, SESSION_PREFLIGHT_TIMEOUT_SECONDS),
      () => currentPage,
      () => currentFrame,
      async () => preflightSessionForUpload(session, sessionOpts, config.writeUrl),
    );
    if (!sessionPreflight.ok) {
      throw new Error(`[SESSION_PRECHECK_FAILED] ${formatSessionPreflightFailure(sessionPreflight)}`);
    }

    // 에디터 iframe 획득
    let frame: Frame;
    try {
      frame = await withStageTimeout(
        'editor_iframe_get',
        stepTimeoutSeconds,
        () => currentPage,
        () => currentFrame,
        async () => getEditorFrameOrThrow(page, config.artifactsDir),
      );
    } catch (error) {
      if (error instanceof EditorIframeNotFoundError) {
        setCurrentStage('write_page_enter');
        const loginState = await detectLoginState(page).catch(() => ({
          state: 'unknown',
          signal: 'detect_error',
          url: page.url(),
        }));
        const debugDir = await collectTimeoutDebugSafe(
          currentPage,
          null,
          error.reason,
          null,
          error.iframeProbe,
          {
            state: loginState.state,
            signal: loginState.signal,
          },
        );
        error.debugDir = debugDir ?? null;
      }
      throw error;
    }
    currentFrame = frame;
    const ctx: EditorContext = { page, frame };
    let sessionRecoveryUsed = false;

    const runWithSessionRecovery = async <T>(stage: string, fn: () => Promise<T>): Promise<T> => {
      try {
        if (isLoginRedirectUrl(page.url())) {
          throw new Error(`[SESSION_REDIRECT] stage=${stage}`);
        }
        return await fn();
      } catch (error: any) {
        const msg = String(error?.message || error || '');
        const isSessionIssue = isLoginRedirectUrl(page.url()) ||
          /\[session_redirect\]|session|로그인|nidlogin|logins\.naver\.com/i.test(msg);
        if (!isSessionIssue || sessionRecoveryUsed) {
          throw error;
        }

        sessionRecoveryUsed = true;
        log.warn(`[session] redirect/session issue detected at stage=${stage}, attempting auto recovery`);
        const recovered = await withStageTimeout(
          'session_auto_recover',
          stepTimeoutSeconds,
          () => currentPage,
          () => currentFrame,
          async () => recoverExpiredSession(session, sessionOpts, config.writeUrl),
        );
        if (!recovered.ok) {
          throw new Error('[SESSION_RECOVERY_FAILED] 자동 세션 복구 실패');
        }

        const recoveredFrame = await withStageTimeout(
          'editor_iframe_reacquire',
          stepTimeoutSeconds,
          () => currentPage,
          () => currentFrame,
          async () => getEditorFrame(page, config.artifactsDir),
        );
        if (!recoveredFrame) {
          throw new Error('[SESSION_RECOVERY_FAILED] 복구 후 에디터 iframe 재획득 실패');
        }
        currentFrame = recoveredFrame;
        ctx.frame = recoveredFrame;
        const readyAfterRecover = await withStageTimeout(
          'editor_ready_after_recover',
          stepTimeoutSeconds,
          () => currentPage,
          () => currentFrame,
          async () => waitForEditorReady(recoveredFrame, config.artifactsDir, page),
        );
        if (!readyAfterRecover) {
          throw new Error('[SESSION_RECOVERY_FAILED] 복구 후 에디터 준비 실패');
        }
        return await fn();
      }
    };

    // 에디터 준비 대기 (time budget은 waitForEditorReady 단일 지점에서 관리)
    setCurrentStage('write_page_enter');
    const writePageReadyStarted = Date.now();
    const writePageBudgetMs = Math.max(5_000, stepTimeoutSeconds * 1000);
    const editorReady = await waitForEditorReady(frame!, config.artifactsDir, page, {
      timeBudgetMs: writePageBudgetMs,
      perSelectorTimeoutMs: 1_200,
      pollIntervalMs: 2_000,
      allowPageReloadRecovery: EDITOR_READY_ALLOW_RELOAD_RECOVERY,
      reacquireFrame: async () => {
        const refreshed = page.frame('mainFrame') ?? (await getEditorFrame(page, config.artifactsDir));
        if (refreshed) {
          currentFrame = refreshed;
          ctx.frame = refreshed;
        }
        return refreshed;
      },
    }).catch(async (error) => {
      const text = String((error as any)?.message || error || '');
      if (text.includes('[EDITOR_READY_TIMEOUT]')) {
        await collectTimeoutDebugSafe(currentPage, currentFrame, `stage_timeout_write_page_enter_${Math.floor(writePageBudgetMs / 1000)}s`);
      }
      throw error;
    });
    if (!editorReady) {
      throw new Error('에디터 로딩 실패. 스크린샷을 확인하세요.');
    }
    logTiming('write_page_enter', writePageReadyStarted);

    // 헬스체크 모드
    if (options.healthcheck) {
      const results = await selectorHealthcheck(frame!);
      const allOk = Object.values(results).every(Boolean);
      log.info(`\n헬스체크 결과: ${allOk ? 'ALL PASS' : 'SOME FAILED'}`);
      await context.close();
      if (session.browser) {
        await session.browser.close().catch(() => undefined);
      }
      stopWatchdogs();
      process.exit(allOk ? 0 : 1);
    }

    // Step 3: 제목 입력
    stepStart = Date.now();
    log.step(3, TOTAL_STEPS, '제목 입력');
    const titleOk = await runWithSessionRecovery('title_input', async () => withStageTimeout(
      'title_input',
      stepTimeoutSeconds,
      () => currentPage,
      () => currentFrame,
      async () => inputTitle(ctx, postDir.parsed.title, config.artifactsDir),
    ));
    if (!titleOk) {
      throw new Error('제목 입력 실패');
    }
    logTiming('title_input', stepStart);

    // Step 4: 본문/이미지 블록 순차 삽입
    stepStart = Date.now();
    log.step(4, TOTAL_STEPS, '본문/이미지 블록 순차 삽입');
    log.info('[timing] step=text_blocks_insert_start elapsed=0.0s');
    const bodyText = postDir.parsed.blocks
      .filter((block) => block.type === 'text')
      .map((block) => block.content)
      .join('\n\n')
      .trim();
    const hasBoldHeadingBlocks = postDir.parsed.blocks.some((block) => block.type === 'section_title');
    let sectionBlocks: PostBlock[] = [];

    if (hasBoldHeadingBlocks) {
      sectionBlocks = [...postDir.parsed.blocks];
      log.info('[outline] blog_result.md의 **소제목**을 감지하여 원본 블록 순서를 그대로 사용합니다.');
    } else {
      const topicOrganizeEnabled = parseBoolEnv('TOPIC_ORGANIZE', true);
      const imagePlaceEnabled = parseBoolEnv('IMAGE_PLACE', true);

      const organized = topicOrganizeEnabled
        ? organizeTopics(bodyText, { useDefaultOrder: true })
        : {
          sections: [{ title: '방문후기', paragraphs: bodyText ? [bodyText] : [] }],
          orderedText: bodyText,
          debugInfo: {
            paragraphCount: bodyText ? 1 : 0,
            sectionCount: bodyText ? 1 : 0,
            appliedDefaultOrder: false,
            outlineFixNote: 'topic-organize-disabled',
            movedConclusionParagraphs: 0,
          },
        };

      const sections = organized.sections.length > 0
        ? organized.sections
        : [{ title: '방문후기', paragraphs: [bodyText || ''] }];
      if (organized.debugInfo.outlineFixNote && organized.debugInfo.outlineFixNote !== 'no-outline-fix') {
        log.info(`[outline] ${organized.debugInfo.outlineFixNote}`);
      }

      const placements = imagePlaceEnabled
        ? await placeImagesBySection(sections, postDir.imagePaths, {
          threshold: Number(process.env.MATCH_THRESHOLD ?? '0.55'),
        })
        : postDir.imagePaths.map((_, idx) => ({
          imageIndex: idx + 1,
          sectionIndex: sections.length > 0 ? idx % sections.length : 0,
          paragraphIndex: 0,
        }));

      sectionBlocks = buildSectionBlocks(sections, placements);
    }

    const { normalizedBlocks, syntheticTextInserted } = normalizeBlockSequenceForDraft(sectionBlocks);
    const sectionTitleAsText = (process.env.NAVER_SECTION_TITLE_AS_TEXT ?? 'false').toLowerCase() === 'true';
    let blockSequence: PostBlock[] = normalizedBlocks.map((block): PostBlock => {
      if (sectionTitleAsText && block.type === 'section_title') {
        return { type: 'text', content: block.content };
      }
      return block;
    });
    if (syntheticTextInserted) {
      log.warn('이미지-only 블록 감지: 임시저장 안정화를 위해 안내 텍스트 블록을 자동 삽입했습니다.');
    }
    if (sectionTitleAsText) {
      log.warn('[outline] NAVER_SECTION_TITLE_AS_TEXT=true: section_title를 일반 text로 변환합니다 (인용구2 비활성화).');
    }

    if (!blockSequence.length) {
      throw new Error('삽입할 본문 블록이 없습니다.');
    }

    let bootstrappedFirstTextBlock = false;
    const firstTextIndex = blockSequence.findIndex((block) => block.type === 'text' && block.content.trim().length > 0);
    if (firstTextIndex === 0) {
      const firstBlock = blockSequence[0];
      if (firstBlock.type !== 'text') {
        throw new Error('내부 오류: 첫 본문 블록 타입이 text가 아닙니다.');
      }
      const firstBody = firstBlock.content;
      log.info('[title-body] 제목 입력 직후 Enter 기반 본문 진입을 수행합니다.');
      const titleBodyOk = await runWithSessionRecovery('title_body_enter', async () => withStageTimeout(
        'title_body_enter',
        Math.min(stepTimeoutSeconds, 10),
        () => currentPage,
        () => currentFrame,
        async () => writeTitleThenBodyViaKeyboard(ctx, postDir.parsed.title, firstBody),
      ));
      if (!titleBodyOk) {
        throw new Error('제목→본문 Enter 전환 실패');
      }
      blockSequence = blockSequence.slice(1);
      bootstrappedFirstTextBlock = true;
      log.info('[title-body] 첫 본문 블록을 Enter 기반으로 입력 완료');
    }

    let effectiveImagePaths = [...postDir.imagePaths];
    if (!options.publish) {
      const draftMaxImages = Math.max(0, parseInt(process.env.NAVER_DRAFT_TEST_MAX_IMAGES ?? '0', 10));
      if (draftMaxImages > 0 && effectiveImagePaths.length > draftMaxImages) {
        effectiveImagePaths = effectiveImagePaths.slice(0, draftMaxImages);
        blockSequence = blockSequence.filter((block) =>
          block.type !== 'image' || block.index <= effectiveImagePaths.length,
        );
        log.info(`[draft] 테스트 모드 이미지 제한 적용: ${postDir.imagePaths.length} -> ${effectiveImagePaths.length}`);
      }
    }

    const uploadPlan = buildImageUploadPlan(effectiveImagePaths);
    for (const [idx, img] of uploadPlan.entries()) {
      log.info(
        `[image-plan] index=${idx + 1} exists=${img.exists} size_bytes=${img.sizeBytes} too_large=${img.tooLarge} path=${img.filePath}`,
      );
    }

    const blockInsertTimeoutSeconds = computeInsertBlocksTimeoutSeconds(
      blockSequence.map((block) => ({ type: block.type })),
      {
        fallbackSeconds: stepTimeoutSeconds,
        minSeconds: Math.max(30, stepTimeoutSeconds),
        maxSeconds: Math.max(600, parseInt(process.env.NAVER_INSERT_BLOCKS_TIMEOUT_MAX_SECONDS ?? '600', 10)),
      },
    );
    const textBlockCount = blockSequence.filter((block) => block.type === 'text' || block.type === 'section_title').length;
    const imageBlockCount = blockSequence.filter((block) => block.type === 'image').length;
    const postPlan = buildPostPlan(blockSequence, effectiveImagePaths);
    const postPlanState = createPostPlanState();
    log.info(`[plan] blocks=${postPlan.blocks.length} text=${textBlockCount} image=${imageBlockCount}`);
    for (const block of postPlan.blocks) {
      const summary = block.type === 'image'
        ? `imageIndex=${block.imageIndex ?? -1} path=${block.imagePath ?? ''}`
        : `textHashBlock=${block.blockId.slice(-8)}`;
      log.info(`[plan] sourceIndex=${block.sourceIndex} type=${block.type} blockId=${block.blockId} ${summary}`);
    }
    log.info(
      `[timing] step=text_blocks_insert_timeout_budget seconds=${blockInsertTimeoutSeconds} text_blocks=${textBlockCount} image_blocks=${imageBlockCount}`,
    );

    // 에디터 클린 상태 기준값 캡처 (DUPLICATED 오탐 방지용 — 이전 세션 잔류 이미지 감지)
    const editorBaselineState = await getEditorImageState(ctx.frame).catch(() => ({ count: 0, refs: [] as string[] }));
    if (editorBaselineState.count > 0) {
      log.warn(`[baseline] 에디터 잔존 이미지 감지: ${editorBaselineState.count}개 (이전 세션 잔류, EDITOR_NOT_CLEAN 기준값으로 기록)`);
    }

    const blockInsertResult = blockSequence.length === 0
      ? {
        success: true,
        expected_image_count: 0,
        uploaded_image_count: 0,
        missing_image_count: 0,
        marker_residue_count: 0,
        marker_samples: [],
        upload_attempts: [],
        sample_image_refs: [],
        duplicate_skip_count: 0,
        message: bootstrappedFirstTextBlock
          ? '첫 텍스트 블록을 title→body Enter 경로로 입력 완료'
          : '삽입할 블록 없음',
      }
      : await runWithSessionRecovery('text_blocks_insert', async () => withStageTimeout(
        'text_blocks_insert',
        blockInsertTimeoutSeconds,
        () => currentPage,
        () => currentFrame,
        async () => insertBlocksSequentially(
          ctx,
          postPlan,
          effectiveImagePaths,
          config.artifactsDir,
          { state: postPlanState },
        ),
      ));
    if (!blockInsertResult.success) {
      const reasonCode = blockInsertResult.reason_code ? ` reason=${blockInsertResult.reason_code}` : '';
      const debugPath = blockInsertResult.debug_path ? ` debugPath=${blockInsertResult.debug_path}` : '';
      throw new Error(`블록 순차 삽입 실패: ${blockInsertResult.message}${reasonCode}${debugPath}`);
    }

    const step4Duration = Date.now() - stepStart;
    log.info(`[timing] step=text_blocks_insert_complete elapsed=${(step4Duration / 1000).toFixed(1)}s`);

    report.steps.C = {
      stage: 'Step C: naver_image_upload',
      status: blockInsertResult.expected_image_count === 0
        ? 'skipped'
        : (blockInsertResult.missing_image_count > 0 ? 'partial' : 'success'),
      message: blockInsertResult.expected_image_count === 0
        ? '이미지 없음'
        : `블록 삽입 시점 이미지 업로드 완료 (${blockInsertResult.uploaded_image_count}/${blockInsertResult.expected_image_count})`,
      data: {
        expected_count: blockInsertResult.expected_image_count,
        uploaded_count: blockInsertResult.uploaded_image_count,
        missing_count: blockInsertResult.missing_image_count,
        duplicate_skip_count: blockInsertResult.duplicate_skip_count,
        reason_code: blockInsertResult.reason_code,
        debug_path: blockInsertResult.debug_path,
        attempts: blockInsertResult.upload_attempts,
      },
    };
    report.steps.D = {
      stage: 'Step D: attach_resource_id_capture',
      status: blockInsertResult.uploaded_image_count > 0 ? 'success' : 'skipped',
      message: blockInsertResult.uploaded_image_count > 0
        ? '이미지 리소스 참조 확보'
        : '이미지 없음',
      data: {
        image_refs: blockInsertResult.sample_image_refs,
        ref_count: blockInsertResult.sample_image_refs.length,
      },
    };
    report.steps.E = {
      stage: 'Step E: body_insert_image_reference',
      status: blockInsertResult.marker_residue_count === 0 ? 'success' : 'failed',
      message: blockInsertResult.marker_residue_count === 0
        ? '이미지 블록 순차 삽입 완료 (마커 잔존 없음)'
        : `이미지 마커 잔존 감지 (${blockInsertResult.marker_residue_count})`,
      data: {
        marker_residue_count: blockInsertResult.marker_residue_count,
        marker_samples: blockInsertResult.marker_samples,
      },
    };

    // Step 5: 장소 첨부
    stepStart = Date.now();
    log.step(5, TOTAL_STEPS, '장소 첨부');
    const placeInput = await withStageTimeout(
      'place_resolve',
      stepTimeoutSeconds,
      () => currentPage,
      () => currentFrame,
      async () => resolvePlaceInput(
        options.placeName,
        options.regionHint,
        postDir,
        config.kakaoApiKey,
      ),
    );
    const resolvedStoreName = placeInput.storeName;
    if (!resolvedStoreName) {
      if (config.placeAttachRequired) {
        throw new Error('장소 첨부 실패: store_name(상호명)을 결정할 수 없습니다.');
      }
      log.warn('장소명을 결정할 수 없어 장소 첨부를 건너뜁니다.');
    } else {
      const placeResult = await runWithSessionRecovery('place_attach', async () => withStageTimeout(
        'place_attach',
        stepTimeoutSeconds,
        () => currentPage,
        () => currentFrame,
        async () => attach_place_in_editor(
          ctx,
          resolvedStoreName,
          { region_hint: placeInput.regionHint, category_hint: postDir.metadata?.category },
          config.artifactsDir,
        ),
      ));
      if (!placeResult.success) {
        const reason = placeResult.error ?? '알 수 없는 오류';
        const reasonCode = placeResult.reason_code ? ` (${placeResult.reason_code})` : '';
        const debugSuffix = placeResult.debug_path ? ` debugPath=${placeResult.debug_path}` : '';
        if (config.placeAttachRequired) {
          throw new Error(`장소 첨부 실패${reasonCode}: ${reason}${debugSuffix}`);
        }
        log.warn(`장소 첨부 실패(비치명)${reasonCode}: ${reason}${debugSuffix}`);
      } else {
        log.success(`장소 카드 삽입 완료: ${placeResult.selected_place?.title ?? resolvedStoreName}`);
      }
    }
    logTiming('place_attach_complete', stepStart);

    // Step 7: 발행 또는 임시저장
    stepStart = Date.now();
    const action = options.publish ? '발행' : '임시저장';
    const draftSaveEnabled = parseBoolEnv('NAVER_DRAFT_SAVE', true);
    log.step(7, TOTAL_STEPS, action);

    let postSaveImageCheck: Awaited<ReturnType<typeof verifyImageReferencesInEditor>> = {
      success: true,
      image_count: 0,
      refs: [],
      message: '초기화',
    };

    if (!options.publish && !draftSaveEnabled) {
      log.warn('NAVER_DRAFT_SAVE=false 설정으로 임시저장 단계를 건너뜁니다.');
      report.steps.F = { stage: 'Step F: draft_save_call', status: 'skipped', message: 'NAVER_DRAFT_SAVE=false' };
      report.steps.G = { stage: 'Step G: post_save_image_reference_verification', status: 'skipped', message: 'NAVER_DRAFT_SAVE=false' };
    } else if (options.dryRun) {
      log.info(`=== DRY RUN 모드 - ${action} 직전에서 중단 ===`);
      log.info('현재 에디터 상태를 확인하세요.');
      log.info('종료하려면 Enter를 누르세요...');
      await new Promise<void>((resolve) => {
        process.stdin.once('data', () => resolve());
      });
      report.steps.F = { stage: 'Step F: draft_save_call', status: 'skipped', message: 'dry-run 모드' };
      report.steps.G = { stage: 'Step G: post_save_image_reference_verification', status: 'skipped', message: 'dry-run 모드' };
    } else if (options.publish) {
      // 직접 발행 모드
      const publishOk = await withStageTimeout(
        'publish_click',
        stepTimeoutSeconds,
        () => currentPage,
        () => currentFrame,
        async () => clickPublish(ctx, config.artifactsDir),
      );
      if (!publishOk) {
        throw new Error('발행 버튼 클릭 실패');
      }

      // 발행 확인
      log.info('발행 완료 확인 중...');
      await ctx.page.waitForTimeout(3000); // 발행 처리 대기
      const publishVerified = await verifyPublished(ctx, postDir.parsed.title);
      if (!publishVerified) {
        log.warn('발행 완료 확인에 실패했지만 발행 버튼은 클릭됨');
      } else {
        log.success('발행 완료 확인');
      }
      report.steps.F = {
        stage: 'Step F: draft_save_call',
        status: 'success',
        message: 'publish 모드에서는 임시저장 대신 발행 수행',
      };
      report.steps.G = {
        stage: 'Step G: post_save_image_reference_verification',
        status: 'skipped',
        message: 'publish 모드에서는 draft 검증 생략',
      };
    } else {
      // 임시저장 모드
      const loginEnsured = await withStageTimeout(
        'ensure_logged_in_before_draft',
        stepTimeoutSeconds,
        () => currentPage,
        () => currentFrame,
        async () => ensureLoggedIn(session, sessionOpts, config.writeUrl, 'passive'),
      );
      if (!loginEnsured.ok) {
        throw new Error('임시저장 직전 세션 검증 실패');
      }
      log.info(`[session] pre_draft_login_check ok=true auto_login_attempted=${loginEnsured.autoLoginAttempted} signal=${loginEnsured.signal}`);

      const draftClickTimeoutMs = Math.min(DRAFT_CLICK_TIMEOUT_MS, TEMP_SAVE_STAGE_TIMEOUT_MS);
      const draftVerifyTimeoutMs = Math.min(DRAFT_VERIFY_TIMEOUT_MS, TEMP_SAVE_STAGE_TIMEOUT_MS);

      log.info('[timing] step=draft_click_start elapsed=0.0s');
      let draftClickStarted = Date.now();
      const draftClickStage = await runDraftStage(
        'clickTempSave',
        draftClickTimeoutMs,
        (stage) => setCurrentStage(stage),
        async () => runWithSessionRecovery('draft_click', async () => clickTempSave(ctx, config.artifactsDir, {
          expectedTitle: postDir.parsed.title,
        })),
        {
          timeoutReasonCode: 'STAGE_TIMEOUT_TEMP_SAVE',
          onTimeout: async () => {
            const debugPath = await collectTimeoutDebugSafe(
              currentPage,
              currentFrame,
              `stage_timeout_temp_save_${Math.floor(draftClickTimeoutMs / 1000)}s`,
            );
            await session.context.close().catch(() => undefined);
            return debugPath;
          },
        },
      );
      if (!draftClickStage.success) {
        if (draftClickStage.timedOut) {
          const detail = `${draftClickStage.reason_code ?? 'STAGE_TIMEOUT_TEMP_SAVE'}${draftClickStage.debug_path ? ` debugPath=${draftClickStage.debug_path}` : ''}`;
          report.steps.F = {
            stage: 'Step F: draft_save_call',
            status: 'failed',
            message: `임시저장 클릭 단계 타임아웃 (${detail})`,
            data: {
              reason_code: draftClickStage.reason_code ?? 'STAGE_TIMEOUT_TEMP_SAVE',
              debug_path: draftClickStage.debug_path,
            },
          };
          throw new Error(`임시저장 클릭 단계 타임아웃 (${detail})`);
        }
        throw new Error(draftClickStage.error || '임시저장 클릭 단계 실패');
      }
      let saveOk = Boolean(draftClickStage.data?.success);
      let saveErr = draftClickStage.data?.error;
      if (!saveOk) {
        log.warn('임시저장 버튼 1차 클릭 실패, 상태 안정화 후 1회 재시도');
        await withStageTimeout(
          'draft_stabilize',
          stepTimeoutSeconds,
          () => currentPage,
          () => currentFrame,
          async () => stabilizePageState(ctx, config.artifactsDir),
        );
        draftClickStarted = Date.now();
        const draftRetryStage = await runDraftStage(
          'clickTempSave',
          draftClickTimeoutMs,
          (stage) => setCurrentStage(`${stage}_retry`),
          async () => runWithSessionRecovery('draft_click_retry', async () => clickTempSave(ctx, config.artifactsDir, {
            expectedTitle: postDir.parsed.title,
          })),
          {
            timeoutReasonCode: 'STAGE_TIMEOUT_TEMP_SAVE',
            onTimeout: async () => {
              const debugPath = await collectTimeoutDebugSafe(
                currentPage,
                currentFrame,
                `stage_timeout_temp_save_retry_${Math.floor(draftClickTimeoutMs / 1000)}s`,
              );
              await session.context.close().catch(() => undefined);
              return debugPath;
            },
          },
        );
        if (!draftRetryStage.success) {
          if (draftRetryStage.timedOut) {
            const detail = `${draftRetryStage.reason_code ?? 'STAGE_TIMEOUT_TEMP_SAVE'}${draftRetryStage.debug_path ? ` debugPath=${draftRetryStage.debug_path}` : ''}`;
            report.steps.F = {
              stage: 'Step F: draft_save_call',
              status: 'failed',
              message: `임시저장 재시도 클릭 단계 타임아웃 (${detail})`,
              data: {
                reason_code: draftRetryStage.reason_code ?? 'STAGE_TIMEOUT_TEMP_SAVE',
                debug_path: draftRetryStage.debug_path,
              },
            };
            throw new Error(`임시저장 재시도 클릭 단계 타임아웃 (${detail})`);
          }
          throw new Error(draftRetryStage.error || '임시저장 재시도 클릭 단계 실패');
        }
        saveOk = Boolean(draftRetryStage.data?.success);
        saveErr = draftRetryStage.data?.error ?? saveErr;
      }
      if (!saveOk) {
        report.steps.F = {
          stage: 'Step F: draft_save_call',
          status: 'failed',
          message: saveErr ? `임시저장 버튼 클릭 실패 (${saveErr})` : '임시저장 버튼 클릭 실패',
        };
        throw new Error(saveErr ? `임시저장 버튼 클릭 실패 (${saveErr})` : '임시저장 버튼 클릭 실패');
      }
      logTiming('draft_click_complete', draftClickStarted);

      log.info('[timing] step=draft_verify_start elapsed=0.0s');
      const draftVerifyStarted = Date.now();
      const verifyStage = await runDraftStage(
        'waitTempSaveSuccess',
        draftVerifyTimeoutMs,
        (stage) => setCurrentStage(stage),
        async () => runWithSessionRecovery('draft_verify', async () => verifyTempSaveWithRetry(
          ctx,
          config.artifactsDir,
          postDir.parsed.title,
          bodyText,
          1,
          async () => (await clickTempSave(ctx, config.artifactsDir, {
            expectedTitle: postDir.parsed.title,
          })).success,
        )),
        {
          timeoutReasonCode: 'DRAFT_VERIFY_TIMEOUT',
          onTimeout: async () => {
            const debugPath = await collectTimeoutDebugSafe(
              currentPage,
              currentFrame,
              `draft_verify_timeout_${Math.floor(draftVerifyTimeoutMs / 1000)}s`,
            );
            await session.context.close().catch(() => undefined);
            return debugPath;
          },
        },
      );
      if (!verifyStage.success || !verifyStage.data) {
        if (verifyStage.timedOut) {
          const reasonCode = verifyStage.reason_code ?? 'DRAFT_VERIFY_TIMEOUT';
          const debugPath = verifyStage.debug_path ? ` debugPath=${verifyStage.debug_path}` : '';
          report.steps.F = {
            stage: 'Step F: draft_save_call',
            status: 'failed',
            message: `임시저장 성공 대기 단계 타임아웃 (${reasonCode}${debugPath})`,
            data: {
              reason_code: reasonCode,
              debug_path: verifyStage.debug_path,
            },
          };
          throw new Error(`임시저장 성공 대기 단계 실패 (${reasonCode}${debugPath})`);
        }
        throw new Error(verifyStage.error || '임시저장 성공 대기 단계 실패');
      }
      const verification = verifyStage.data;
      if (!verification.success) {
        log.error(`임시저장 검증 실패 상세: ${JSON.stringify({
          verified_via: verification.verified_via,
          reason_code: verification.reason_code,
          error_message: verification.error_message,
          debug_path: verification.debug_path,
          screenshots: verification.screenshots,
        })}`);
        const verifyDetail = verification.reason_code
          ? `${verification.reason_code}${verification.debug_path ? ` debugPath=${verification.debug_path}` : ''}`
          : 'UI assertion 미통과';
        report.steps.F = {
          stage: 'Step F: draft_save_call',
          status: 'failed',
          message: `임시저장 검증 실패 (${verifyDetail})`,
          data: {
            verified_via: verification.verified_via,
            reason_code: verification.reason_code,
            debug_path: verification.debug_path,
            error_message: verification.error_message,
          },
        };
        throw new Error(`임시저장 검증 실패 (${verifyDetail})`);
      }
      logTiming('draft_verify_complete', draftVerifyStarted);
      log.success(`임시저장 검증 통과 (${verification.verified_via})`);
      report.steps.F = {
        stage: 'Step F: draft_save_call',
        status: 'success',
        message: `임시저장 검증 통과 (${verification.verified_via})`,
        data: {
          verified_via: verification.verified_via,
          draft_title: verification.draft_title,
          draft_edit_url: verification.draft_edit_url,
          draft_id: verification.draft_id,
        },
      };

      const expectedInsertedImages = blockInsertResult.expected_image_count;
      postSaveImageCheck = await verifyImageReferencesInEditor(ctx.frame, expectedInsertedImages, {
        page: ctx.page,
        requestId,
        accountId,
        expectedPaths: effectiveImagePaths,
        baselineCount: editorBaselineState.count,
      });
      // IMAGE_VERIFY_POSTSAVE_FAILED: 임시저장은 성공했으나 DOM에서 이미지 참조 확인 불가 → 경고로 처리
      const isPostSaveVerifyWarning = !postSaveImageCheck.success
        && postSaveImageCheck.reason_code === 'IMAGE_VERIFY_POSTSAVE_FAILED';
      report.steps.G = {
        stage: 'Step G: post_save_image_reference_verification',
        status: postSaveImageCheck.success ? 'success' : (isPostSaveVerifyWarning ? 'warning' : 'failed'),
        message: postSaveImageCheck.message,
        data: {
          image_count: postSaveImageCheck.image_count,
          refs: postSaveImageCheck.refs,
          reason_code: postSaveImageCheck.reason_code,
          debug_path: postSaveImageCheck.debug_path,
        },
      };
      if (!postSaveImageCheck.success && !isPostSaveVerifyWarning) {
        const reasonCode = postSaveImageCheck.reason_code || 'IMAGE_UPLOAD_NO_INSERT';
        const debugPath = postSaveImageCheck.debug_path ? ` debugPath=${postSaveImageCheck.debug_path}` : '';
        throw new Error(`${reasonCode}: 임시저장 후 본문 이미지 삽입 검증 실패 (${postSaveImageCheck.image_count}/${expectedInsertedImages})${debugPath}`);
      }
      if (isPostSaveVerifyWarning) {
        log.warn(`[Step G] 이미지 참조 DOM 검증 경고 (임시저장은 성공): ${postSaveImageCheck.message}`);
      }
    }

    logTiming('save_or_publish_complete', stepStart);

    // Step G가 'warning' 또는 'skipped'이면 Step D 업로드 카운트를 사용 (DOM 검증 신뢰 불가)
    const observedImageCount = (report.steps.G.status === 'skipped' || report.steps.G.status === 'warning')
      ? blockInsertResult.uploaded_image_count
      : postSaveImageCheck.image_count;
    report.image_summary = {
      requested_count: postDir.imagePaths.length,
      uploaded_count: Math.min(observedImageCount, effectiveImagePaths.length),
      missing_count: Math.max(effectiveImagePaths.length - observedImageCount, 0),
      editor_image_count: observedImageCount,
      status: effectiveImagePaths.length === 0
        ? 'not_requested'
        : observedImageCount >= effectiveImagePaths.length
          ? 'full'
          : (observedImageCount > 0 ? 'partial' : 'none'),
      sample_refs: blockInsertResult.sample_image_refs,
    };
    report.draft_summary = {
      success: options.publish || options.dryRun || report.steps.F.status === 'success',
      verified_via: String((report.steps.F.data?.verified_via as string | undefined) ?? ''),
    };
    report.finished_at = new Date().toISOString();
    report.duration_ms = Date.now() - startTime;
    const strictImageEnforced = !options.publish && !options.dryRun && report.steps.G.status !== 'skipped' && report.steps.G.status !== 'warning';
    if (!report.draft_summary.success) {
      report.overall_status = 'FAILED';
    } else if (report.steps.G.status === 'warning') {
      // 임시저장 성공, Step D 업로드 성공, Step G DOM 검증만 경고
      report.overall_status = 'SUCCESS_WITH_IMAGE_VERIFY_WARNING';
    } else if (report.image_summary.status === 'full' || report.image_summary.status === 'not_requested') {
      report.overall_status = 'SUCCESS_FULL';
    } else if (!strictImageEnforced && report.image_summary.status === 'partial') {
      report.overall_status = 'SUCCESS_PARTIAL_IMAGES';
    } else if (!strictImageEnforced) {
      report.overall_status = 'SUCCESS_TEXT_ONLY';
    } else {
      report.overall_status = 'FAILED';
    }

    // 완료 보고
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    log.info('');
    log.info('========================================');
    const completionMessage = options.dryRun ? 'DRY RUN 완료' :
                             options.publish ? '발행 성공' : '임시저장 성공';
    log.success(completionMessage);
    log.info('========================================');
    log.info(`  디렉토리: ${path.basename(options.dir)}`);
    log.info(`  제목:     ${postDir.parsed.title}`);
    log.info(`  본문:     ${bodyText.length}자`);
    log.info(`  이미지:   ${postDir.imagePaths.length}장`);
    log.info(`  장소:     ${placeInput.storeName}`);
    log.info(`  소요시간: ${elapsed}초`);
    if (!options.publish && !options.dryRun) {
      const draftEditUrl = String((report.steps.F.data?.draft_edit_url as string | undefined) ?? '');
      const draftId = String((report.steps.F.data?.draft_id as string | undefined) ?? '');
      log.info('  확인경로: 네이버 블로그 관리 > 글관리 > 임시저장 글');
      if (draftEditUrl) {
        log.info(`  draft URL: ${draftEditUrl}`);
      }
      if (draftId) {
        log.info(`  draft ID:  ${draftId}`);
      }
    }
    log.info('========================================');
    log.info('[timing] step=process_exit_prepare elapsed=0.0s');
    emitReport(report);
    return report;
  } catch (e: any) {
    if (e instanceof SessionBlockedError) {
      await collectTimeoutDebugSafe(currentPage, currentFrame, e.reason, e.loginProbe);
    }
    if (e instanceof EditorIframeNotFoundError) {
      if (!e.debugDir) {
        const loginState = currentPage ? await detectLoginState(currentPage).catch(() => ({
          state: 'unknown',
          signal: 'detect_error',
          url: currentPage.url(),
        })) : { state: 'unknown', signal: 'no_page' };
        const debugDir = await collectTimeoutDebugSafe(
          currentPage,
          null,
          e.reason,
          null,
          e.iframeProbe,
          { state: loginState.state, signal: loginState.signal },
        );
        e.debugDir = debugDir ?? null;
      }
      log.error(`[editor] iframe not found reason=${e.reason} debugDir=${e.debugDir ?? 'n/a'}`);
    }
    report.finished_at = new Date().toISOString();
    report.duration_ms = Date.now() - startTime;
    report.steps.F = report.steps.F.status === 'failed'
      ? report.steps.F
      : {
          stage: 'Step F: draft_save_call',
          status: 'failed',
          message: e?.message ? String(e.message) : '임시저장 단계에서 오류 발생',
        };
    report.steps.G = report.steps.G.status === 'failed'
      ? report.steps.G
      : {
          stage: 'Step G: post_save_image_reference_verification',
          status: 'failed',
          message: '임시저장 실패로 사후 검증 생략',
        };
    report.draft_summary = {
      success: false,
      failure_reason: e?.message ? String(e.message) : '알 수 없는 오류',
    };
    report.overall_status = 'FAILED';
    emitReport(report);
    throw e;

  } finally {
    log.info('[timing] step=process_exit_finally elapsed=0.0s');
    stopWatchdogs();
    // 브라우저 종료 (세션은 userDataDir에 유지)
    await context.close();
    if (session.browser) {
      await session.browser.close().catch(() => undefined);
    }
  }
}

// ────────────────────────────────────────────
// CLI 정의
// ────────────────────────────────────────────
const program = new Command();

program
  .name('naver-post')
  .description('네이버 블로그 포스팅 자동화 도구 (임시저장/발행)')
  .version('1.0.0');

program
  .option('--dir <path>', '포스팅 데이터 디렉토리 (blog_result.md + images/)')
  .option('--placeName <name>', '장소 검색에 사용할 상호명')
  .option('--regionHint <text>', '장소 검색에 사용할 지역 힌트 (예: 제주, 강남)')
  .option('--interactiveLogin', '인터랙티브 로그인 모드')
  .option('--autoLogin', '자동 로그인 모드 (환경변수 NAVER_ID, NAVER_PW 사용)', false)
  .option('--profileDir <path>', 'Playwright persistent 프로필 디렉토리 지정 (WSL 로컬 경로 권장)')
  .option('--initProfileDir', '프로필 디렉토리 생성/권한 확인만 수행 후 종료', false)
  .option('--printSessionBackend', '현재 세션 백엔드 한 줄 출력 후 계속 진행', false)
  .option('--clearCooldown', '세션 쿨다운 상태를 초기화', false)
  .option('--dryRun', '드라이런 모드 (임시저장 직전까지만 수행)', false)
  .option('--draft', '임시저장 테스트 모드 (절대 발행하지 않음)', false)
  .option('--publish', '직접 발행 모드 (임시저장 대신 바로 발행)', false)
  .option('--healthcheck', '셀렉터 헬스체크 모드', false)
  .option('--verifyFlow', '수정 후 필수 체크리스트 게이트 실행', false)
  .option('--headless', '헤드리스 모드 (기본: true, --no-headless로 headed 모드)')
  .action(async (opts) => {
    try {
      const config = getConfig({ profileDir: opts.profileDir });
      if (opts.printSessionBackend) {
        const backend = getSessionBackendLabel({
          profileDir: config.profileDir,
          userDataDir: config.userDataDir,
          storageStatePath: config.storageStatePath,
        });
        log.info(`backend=${backend}`);
      }
      if (opts.initProfileDir) {
        const ensured = ensureProfileDir(config.profileDir);
        log.info(`[session] profile_dir_exists=${ensured.exists} created=${ensured.created} path=${ensured.path}`);
        process.exit(0);
      }

      if (opts.verifyFlow) {
        const verifyScript = path.resolve(process.cwd(), 'test_scripts/verify_flow.js');
        const result = spawnSync(process.execPath, [verifyScript], {
          stdio: 'inherit',
          env: { ...process.env },
        });
        process.exit(Number(result.status ?? 1));
      }

      // 인터랙티브 로그인 모드
      if (opts.interactiveLogin) {
        await interactiveLogin({
          profileDir: config.profileDir,
          userDataDir: config.userDataDir,
          storageStatePath: config.storageStatePath,
          headless: false,
        });
        process.exit(0);
      }

      // 자동 로그인 모드
      if (opts.autoLogin) {
        const success = await autoLogin({
          profileDir: config.profileDir,
          userDataDir: config.userDataDir,
          storageStatePath: config.storageStatePath,
          headless: opts.headless || config.headless,
        });
        process.exit(success ? 0 : 1);
      }

      if (opts.clearCooldown) {
        const target = clearSessionCooldown(config.userDataDir);
        log.info(`[session] cooldown cleared: ${target}`);
        process.exit(0);
      }

      // 헬스체크 모드 (--dir 없이도 동작)
      if (opts.healthcheck && !opts.dir) {
        const sessionOpts: SessionOptions = {
          profileDir: config.profileDir,
          userDataDir: config.userDataDir,
          storageStatePath: config.storageStatePath,
          headless: opts.headless || config.headless,
        };
        const session = await loadOrCreateSession(sessionOpts, config.writeUrl);
        const hcFrame = await getEditorFrame(session.page, config.artifactsDir);
        if (!hcFrame) {
          log.fatal('에디터 iframe을 찾을 수 없습니다');
        }
        await waitForEditorReady(hcFrame!, config.artifactsDir, session.page);
        const results = await selectorHealthcheck(hcFrame!);
        await session.context.close();
        if (session.browser) {
          await session.browser.close().catch(() => undefined);
        }
        const allOk = Object.values(results).every(Boolean);
        process.exit(allOk ? 0 : 1);
      }

      // 일반 포스팅 모드 - dir 필수
      if (!opts.dir) {
        log.error('--dir 옵션이 필요합니다.');
        log.info('사용법: naver-post --dir="/path/to/post/dir" [--placeName="상호명"] [--regionHint="제주"] [--draft|--publish]');
        log.info('로그인: naver-post --interactiveLogin');
        log.info('자동로그인: NAVER_ID="아이디" NAVER_PW="비밀번호" naver-post --autoLogin');
        log.info('임시저장: naver-post --dir="20260214(하이디라오 제주도점)" --draft');
        log.info('발행:   naver-post --dir="/path/to/post/dir" --publish');
        process.exit(1);
      }
      if (opts.publish && opts.draft) {
        log.error('--draft 와 --publish는 동시에 사용할 수 없습니다.');
        process.exit(1);
      }

      if (opts.headless) {
        process.env.HEADLESS = 'true';
      }

      const cooldown = getSessionCooldownStatus(config.userDataDir);
      if (cooldown.active) {
        log.error(`[session] cooldown active reason=${cooldown.state.lastReason ?? 'unknown'} until=${new Date(cooldown.state.cooldownUntilTs).toISOString()}`);
        log.info(formatInteractiveLoginGuide(cooldown.state.cooldownUntilTs));
        process.exit(1);
      }

      const resolvedDir = resolvePostDirInput(opts.dir);
      const publishMode = Boolean(opts.publish);
      const draftMode = Boolean(opts.draft || !publishMode);
      if (draftMode && publishMode) {
        log.error('모드 해석 오류: draft/publish가 동시에 활성화되었습니다.');
        process.exit(1);
      }

      await runPosting({
        dir: resolvedDir,
        placeName: opts.placeName,
        regionHint: opts.regionHint,
        dryRun: opts.dryRun,
        publish: publishMode,
        healthcheck: opts.healthcheck,
        profileDir: opts.profileDir,
      });

      process.exit(0);
    } catch (e: any) {
      const diagnosis = classifyExecutionFailure(e);
      log.error(`[diagnostic] category=${diagnosis.category} reason=${diagnosis.reason}`);
      if (diagnosis.category === 'a') {
        log.info('[diagnostic] a) GUI 불가(WSLg 미작동) 또는 interactiveLogin headless 문제');
      } else if (diagnosis.category === 'b') {
        log.info('[diagnostic] b) 세션 만료/쿠키 무효');
      } else if (diagnosis.category === 'c') {
        log.info('[diagnostic] c) 보안확인/캡차/2FA 리디렉트');
      } else if (diagnosis.category === 'd') {
        log.info('[diagnostic] d) 셀렉터 변경/에디터 로딩 실패');
      }
      if (e instanceof SessionBlockedError) {
        if (!e.debugDir) {
          await collectTimeoutDebugSafe(null, null, e.reason, e.loginProbe);
        }
        log.error(`[session] blocked reason=${e.reason} debugDir=${e.debugDir ?? 'n/a'}`);
        log.info(formatInteractiveLoginGuide());
      }
      if (e instanceof EditorIframeNotFoundError) {
        if (!e.debugDir) {
          await collectTimeoutDebugSafe(null, null, e.reason, null, e.iframeProbe, { state: 'unknown', signal: 'cli_catch' });
        }
        log.error(`[editor] iframe_not_found reason=${e.reason} debugDir=${e.debugDir ?? 'n/a'}`);
      }
      log.error(`실행 실패: ${e.message}`);
      if (e.stack) log.error(e.stack);
      process.exit(1);
    }
  });

program.parse(process.argv);
