import { Page, Frame } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';
import * as log from '../utils/logger';
import { captureFailure, captureEditorDebug } from '../utils/logger';
import { PostBlock } from '../utils/parser';
import { PostPlan, PostPlanState, createPostPlanState, getImageId } from '../utils/post_plan';
import { createDebugRunDir } from '../common/debug_paths';
import { DraftSaver } from './draft_saver';
import { NAVER_SELECTORS } from './selectors';

/**
 * 에디터 컨텍스트: page(키보드/스크린샷)와 frame(요소 접근)을 분리.
 * 네이버 에디터는 iframe#mainFrame 안에 있다.
 */
export interface EditorContext {
  page: Page;
  frame: Frame;
}

export type EditorIframeProbe = {
  expectedFrameUrlPatternMatched: boolean;
  frameCount: number;
  triedSelectors: string[];
  lastSeenFrameUrls: string[];
};

export class EditorIframeNotFoundError extends Error {
  readonly reason: string;
  readonly iframeProbe: EditorIframeProbe;
  debugDir: string | null;

  constructor(reason: string, iframeProbe: EditorIframeProbe, debugDir: string | null = null) {
    super('[EDITOR_IFRAME_NOT_FOUND] 에디터 iframe을 찾을 수 없습니다');
    this.name = 'EditorIframeNotFoundError';
    this.reason = reason;
    this.iframeProbe = iframeProbe;
    this.debugDir = debugDir;
  }
}

export interface ImageUploadItemTrace {
  image_path: string;
  file_name: string;
  extension: string;
  mime_type: string;
  exists: boolean;
  size_bytes: number;
}

export interface UploadNetworkTrace {
  url: string;
  status: number;
  ok: boolean;
  elapsed_ms: number;
}

export type ImageUploadReasonCode =
  | 'IMAGE_LIST_EMPTY'
  | 'IMAGE_FILE_NOT_FOUND'
  | 'IMAGE_UPLOAD_UI_FAILED'
  | 'IMAGE_UPLOAD_NO_INSERT'
  | 'IMAGE_UPLOAD_STUCK'
  | 'IMAGE_UPLOAD_DUPLICATED'
  /** Step G 사후 검증 실패 (경고): draft 저장은 성공했으나 에디터 DOM에서 이미지 참조를 확인할 수 없음 */
  | 'IMAGE_VERIFY_POSTSAVE_FAILED'
  /** 에디터 클린 상태 아님: 업로드 전 에디터에 잔존 이미지 감지 */
  | 'EDITOR_NOT_CLEAN';

export interface ImageUploadSignalsObserved {
  toast: boolean;
  response2xx: boolean;
  domInserted: boolean;
  spinnerGone: boolean;
}

export interface ImageUploadAttemptTrace {
  attempt: number;
  started_at: string;
  duration_ms: number;
  success: boolean;
  message: string;
  network_traces: UploadNetworkTrace[];
  editor_image_count: number;
  transient_failure: boolean;
  reason_code?: ImageUploadReasonCode;
  debug_path?: string;
  upload_signals?: ImageUploadSignalsObserved;
}

export interface ImageUploadResult {
  success: boolean;
  partial: boolean;
  expected_count: number;
  uploaded_count: number;
  missing_count: number;
  editor_image_count: number;
  message: string;
  traces: ImageUploadItemTrace[];
  attempts: ImageUploadAttemptTrace[];
  sample_image_refs: string[];
  reason_code?: ImageUploadReasonCode;
  debug_path?: string;
}

export interface BlockInsertResult {
  success: boolean;
  expected_image_count: number;
  uploaded_image_count: number;
  missing_image_count: number;
  marker_residue_count: number;
  marker_samples: string[];
  upload_attempts: ImageUploadAttemptTrace[];
  sample_image_refs: string[];
  message: string;
  duplicate_skip_count: number;
  reason_code?: string;
  debug_path?: string;
}

export interface TempSaveClickResult {
  success: boolean;
  error?: string;
  via?: 'toast' | 'spinner_cycle' | 'status_text' | 'network_2xx' | 'dialog';
  retries?: number;
  draftId?: string;
  draftEditUrl?: string;
}

export const TITLE_TO_BODY_ENTER_SEQUENCE = ['Enter', 'Enter'] as const;

type EditorReadyProbeSnapshot = {
  attempt: number;
  elapsedMs: number;
  frameUrl: string;
  probes: {
    frameFound: boolean;
    frameAttached: boolean;
    editorRootFound: boolean;
    contentEditableFound: boolean;
    toolbarReady: boolean;
    focusOk: boolean;
    sessionBlocked: boolean;
    spinnerVisible: boolean;
    spinnerCycleDone: boolean;
  };
  recoveryAttempted: boolean;
};

let lastEditorReadyProbeSummary: {
  success: boolean;
  reason?: string;
  attempts: number;
  budgetMs: number;
  elapsedMs: number;
  recoveryAttempted: boolean;
  recoveryCount: number;
  lastSnapshot?: EditorReadyProbeSnapshot;
} | null = null;

export function getLastEditorReadyProbeSummary(): Record<string, unknown> | null {
  return lastEditorReadyProbeSummary ? { ...lastEditorReadyProbeSummary } : null;
}

// ────────────────────────────────────────────
// 텍스트 블록 입력 실패 원인 분류
// ────────────────────────────────────────────
export enum TextInputFailureReason {
  EDITOR_AREA_NOT_FOUND = 'EDITOR_AREA_NOT_FOUND',
  FOCUS_FAILED = 'FOCUS_FAILED',
  INPUT_NOT_REFLECTED = 'INPUT_NOT_REFLECTED',
  VERIFICATION_FAILED = 'VERIFICATION_FAILED',
  VERIFICATION_FAILED_TEXT_NOT_FOUND = 'VERIFICATION_FAILED_TEXT_NOT_FOUND',
  VERIFICATION_FAILED_TEXT_MISMATCH = 'VERIFICATION_FAILED_TEXT_MISMATCH',
  VERIFICATION_FAILED_FOCUS_LOST = 'VERIFICATION_FAILED_FOCUS_LOST',
  VERIFICATION_FAILED_FRAME_CHANGED = 'VERIFICATION_FAILED_FRAME_CHANGED',
  VERIFICATION_FAILED_EDITOR_BLOCK_NOT_CREATED = 'VERIFICATION_FAILED_EDITOR_BLOCK_NOT_CREATED',
  OVERLAY_BLOCKING = 'OVERLAY_BLOCKING',
  CONTENT_ENCODING_ERROR = 'CONTENT_ENCODING_ERROR',
  STALE_ELEMENT = 'STALE_ELEMENT',
  UNKNOWN = 'UNKNOWN',
}

type TextInputAttempt = {
  strategy: 'strategy1_sendkeys' | 'strategy2_js_input' | 'strategy3_paste';
  chunkIndex: number;
  chunkLength: number;
  success: boolean;
  reason?: TextInputFailureReason;
  elapsedMs: number;
};

export interface DebugFixturePayload {
  failed_block_index: number;
  failure_reason: string;
  total_blocks: number;
  title?: string;
  blocks: Array<{
    index: number;
    type: PostBlock['type'];
    content?: string;
    content_length?: number;
    content_hash?: string;
    image_index?: number;
    marker?: string;
  }>;
  image_paths: string[];
  attempts?: TextInputAttempt[];
  timestamp: string;
}

// ────────────────────────────────────────────
// 유틸리티
// ────────────────────────────────────────────
function extToMime(extension: string): string {
  switch (extension.toLowerCase()) {
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.png':
      return 'image/png';
    case '.gif':
      return 'image/gif';
    case '.webp':
      return 'image/webp';
    case '.bmp':
      return 'image/bmp';
    default:
      return 'application/octet-stream';
  }
}

function computeBackoffMs(attempt: number): number {
  const base = 700;
  const exp = Math.min(4, attempt - 1);
  const jitter = Math.floor(Math.random() * 250);
  return base * (2 ** exp) + jitter;
}

const SINGLE_IMAGE_UPLOAD_TIMEOUT_MS = parseInt(process.env.NAVER_IMAGE_UPLOAD_TIMEOUT_MS ?? '20000', 10);
const TEMP_SAVE_SIGNAL_TIMEOUT_MS = parseInt(process.env.NAVER_TEMP_SAVE_SIGNAL_TIMEOUT_MS ?? '30000', 10);

/** 텍스트에서 입력 검증용 샘플 문자열을 추출 */
export function extractVerificationSample(text: string): string {
  // 제어문자/이모지를 제외한 일반 텍스트에서 6~12자 샘플 추출
  const cleaned = text.replace(/[\u200B-\u200D\uFEFF\u0000-\u001F]/g, '').trim();
  if (cleaned.length === 0) return '';
  // 중간 부분에서 샘플 추출 (시작/끝은 줄바꿈 등 문제 가능)
  const start = Math.floor(cleaned.length * 0.3);
  const len = Math.min(12, cleaned.length - start);
  return cleaned.slice(start, start + len);
}

/** 텍스트를 150~300자 청크로 분할 (줄바꿈 경계 우선) */
export function splitIntoChunks(text: string, maxChunkSize: number = 250): string[] {
  const lines = text.split('\n');
  const chunks: string[] = [];
  let current = '';

  for (const line of lines) {
    if (!line) {
      const candidateEmpty = current ? `${current}\n` : '\n';
      if (candidateEmpty.length > maxChunkSize && current) {
        chunks.push(current);
        current = '\n';
      } else {
        current = candidateEmpty;
      }
      continue;
    }

    if (line.length > maxChunkSize) {
      if (current) {
        chunks.push(current);
        current = '';
      }
      for (let i = 0; i < line.length; i += maxChunkSize) {
        chunks.push(line.slice(i, i + maxChunkSize));
      }
      continue;
    }

    const candidate = current ? current + '\n' + line : line;
    if (candidate.length > maxChunkSize && current) {
      chunks.push(current);
      current = line;
    } else {
      current = candidate;
    }
  }
  if (current) {
    chunks.push(current);
  }
  return chunks;
}

/** 에디터에 제어문자/특수 유니코드를 필터링한 안전한 텍스트로 변환 */
export function sanitizeForEditor(text: string): string {
  return text
    // zero-width 문자 제거
    .replace(/[\u200B-\u200D\uFEFF]/g, '')
    // NULL/제어문자 제거 (줄바꿈/탭은 유지)
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
    // 연속 3줄 이상 빈 줄 → 2줄로
    .replace(/\n{3,}/g, '\n\n');
}

export function normalizeForVerification(text: string): string {
  return text
    .replace(/\[\[(?:QUOTE2|QUOTE2_INLINE):[^\]]+\]\]/g, ' ')
    .replace(/[*_`~]/g, ' ')
    .replace(/[\u200B-\u200D\uFEFF\u0000-\u001F\u007F]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

type VerificationAnchors = {
  start: string;
  middle: string;
  end: string;
};

export function buildVerificationAnchors(text: string): VerificationAnchors {
  const normalized = normalizeForVerification(text);
  if (!normalized) {
    return { start: '', middle: '', end: '' };
  }
  const width = Math.min(40, normalized.length);
  const start = normalized.slice(0, width);
  const end = normalized.slice(Math.max(0, normalized.length - width));
  const midStart = Math.max(0, Math.floor((normalized.length - width) / 2));
  const middle = normalized.slice(midStart, midStart + width);
  return { start, middle, end };
}

export function evaluateVerificationAgainstObserved(
  expectedRaw: string,
  observedRaw: string,
): {
  ok: boolean;
  matchedAnchors: number;
  anchors: VerificationAnchors;
  normalizedExpected: string;
  normalizedObserved: string;
} {
  const normalizedExpected = normalizeForVerification(expectedRaw);
  const normalizedObserved = normalizeForVerification(observedRaw);
  const anchors = buildVerificationAnchors(normalizedExpected);
  const anchorValues = [anchors.start, anchors.middle, anchors.end].filter((v) => v.length >= 8);
  const matchedAnchors = anchorValues.filter((v) => normalizedObserved.includes(v)).length;
  const ok = normalizedExpected.length === 0 || matchedAnchors >= Math.min(2, anchorValues.length || 1);
  return { ok, matchedAnchors, anchors, normalizedExpected, normalizedObserved };
}

function sampleHash(text: string, size: number = 40): string {
  return text.slice(0, size).replace(/\n/g, '\\n');
}

function hasSuspiciousControlChars(text: string): boolean {
  return /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(text);
}

async function isEditorOverlayBlocking(frame: Frame): Promise<boolean> {
  try {
    return await frame.evaluate(() => {
      const selectors = [
        '.se-popup-dim',
        '.se-popup-dim-transparent',
        '.se-popup',
        '[role="dialog"]',
        '.ui-dialog',
        '.layer_popup',
        '.se-loading',
        '[class*="spinner"]',
        '[class*="loading"]',
      ];
      return selectors.some((sel) => {
        const el = document.querySelector<HTMLElement>(sel);
        return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
      });
    });
  } catch {
    return false;
  }
}

async function getBodyEditableCount(frame: Frame): Promise<number> {
  try {
    return await frame.evaluate(() => {
      const paragraphs = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text .se-text-paragraph, .se-section-text .se-text-paragraph, .se-component.se-text [contenteditable="true"]',
        ),
      ).filter((el) => !el.closest('.se-documentTitle'));
      return paragraphs.length;
    });
  } catch {
    return 0;
  }
}

async function getEditorDomSignature(frame: Frame): Promise<string> {
  try {
    return await frame.evaluate(() => {
      const nodes = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component-text .se-text-paragraph[contenteditable="true"], .se-components-content [contenteditable="true"], .se-main-container [contenteditable="true"], .se-content [contenteditable="true"]',
        ),
      )
        .filter((el) => !el.closest('.se-documentTitle'))
        .slice(-6);
      const parts = nodes.map((el) => {
        const text = (el.innerText || el.textContent || '').slice(0, 24).replace(/\s+/g, ' ');
        return `${el.tagName}.${el.className}:${text}`;
      });
      return `${nodes.length}|${parts.join('|')}`;
    });
  } catch {
    return 'ERR';
  }
}

async function getEditorRuntimeState(frame: Frame): Promise<{
  activeTag: string;
  activeClass: string;
  overlay: boolean;
  editableCount: number;
}> {
  try {
    return await frame.evaluate(() => {
      const ae = document.activeElement as HTMLElement | null;
      const overlaySelectors = ['.se-popup-dim', '.se-popup', '[role="dialog"]', '.se-loading', '[class*="spinner"]'];
      const overlay = overlaySelectors.some((sel) => {
        const el = document.querySelector<HTMLElement>(sel);
        return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
      });
      const editableCount = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"]'))
        .filter((el) => !el.closest('.se-documentTitle')).length;
      return {
        activeTag: ae?.tagName || 'NONE',
        activeClass: ae?.className || '',
        overlay,
        editableCount,
      };
    });
  } catch {
    return { activeTag: 'ERR', activeClass: '', overlay: false, editableCount: -1 };
  }
}

export async function getEditorImageState(frame: Frame): Promise<{ count: number; refs: string[] }> {
  try {
    return await frame.evaluate(() => {
      const refs = Array.from(
        new Set(
          Array.from(document.querySelectorAll<HTMLImageElement>('img'))
            .map((img) => img.getAttribute('src') || '')
            .filter((src) => src.includes('blogfiles') || src.includes('postfiles')),
        ),
      );
      const componentCount = document.querySelectorAll('.se-component-image, .se-image-resource').length;
      return {
        count: Math.max(refs.length, componentCount),
        refs: refs.slice(0, 10),
      };
    });
  } catch {
    return { count: 0, refs: [] };
  }
}

function buildImageDebugDir(imageIndex: number): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return path.join('/tmp/naver_editor_debug', `${stamp}_image_fail_${imageIndex}`);
}

async function saveImageFailureDebug(
  ctx: EditorContext,
  payload: Record<string, unknown>,
  imageIndex: number,
): Promise<string> {
  const debugDir = buildImageDebugDir(imageIndex);
  try {
    fs.mkdirSync(debugDir, { recursive: true });
    await ctx.page.screenshot({ path: path.join(debugDir, 'page.png'), fullPage: true }).catch(() => undefined);
    const html = await ctx.page.content().catch(() => '');
    if (html) {
      fs.writeFileSync(path.join(debugDir, 'editor.html'), html, 'utf-8');
    }
    fs.writeFileSync(
      path.join(debugDir, 'image_debug.json'),
      JSON.stringify({
        requestId: process.env.NAVER_REQUEST_ID || null,
        accountId: process.env.NAVER_ACCOUNT_ID || null,
        cwd: process.cwd(),
        url: ctx.page.url(),
        frame_urls: ctx.page.frames().map((f) => f.url()),
        captured_at: new Date().toISOString(),
        ...payload,
      }, null, 2),
      'utf-8',
    );
  } catch {
    // ignore debug artifact failures
  }
  return debugDir;
}

async function waitForEditorImageIncrement(
  frame: Frame,
  beforeCount: number,
  timeoutMs: number,
): Promise<{ increased: boolean; state: { count: number; refs: string[] } }> {
  const deadline = Date.now() + timeoutMs;
  let latest = await getEditorImageState(frame);
  if (latest.count > beforeCount) {
    return { increased: true, state: latest };
  }

  while (Date.now() <= deadline) {
    await frame.waitForTimeout(250);
    latest = await getEditorImageState(frame);
    if (latest.count > beforeCount) {
      return { increased: true, state: latest };
    }
  }

  return { increased: false, state: latest };
}

/**
 * 주어진 frame이 stale하거나 이미지 count=0일 때, page의 모든 frame을 순회하여
 * 에디터 DOM을 포함한 frame을 찾고 이미지 상태를 반환한다.
 */
async function findEditorFrameState(page: Page): Promise<{ count: number; refs: string[] }> {
  const editorSelectors = ['.se-content-area', '.se-viewer', '[class*="se-editor"]', '#smarteditor_editor'];
  for (const f of page.frames()) {
    for (const sel of editorSelectors) {
      try {
        const el = await f.$(sel);
        if (!el) continue;
        const state = await getEditorImageState(f);
        if (state.count > 0) return state;
      } catch {
        // stale frame → skip
      }
    }
  }
  return { count: 0, refs: [] };
}

async function clickUploadConfirmIfPresent(frame: Frame, page: Page): Promise<boolean> {
  const clicked = await frame.evaluate(() => {
    const dialogSelectors = ['.se-popup', '.se-popup-content', '[role="dialog"]', '.ui-dialog', '.layer_popup'];
    const dialogs = dialogSelectors
      .flatMap((sel) => Array.from(document.querySelectorAll<HTMLElement>(sel)))
      .filter((el) => el.offsetWidth > 0 && el.offsetHeight > 0);
    const scope = dialogs.length > 0 ? dialogs : [document.body as unknown as HTMLElement];

    const candidates: HTMLElement[] = [];
    for (const root of scope) {
      candidates.push(...Array.from(root.querySelectorAll<HTMLElement>('button, [role="button"], a')));
    }

    for (const el of candidates) {
      const text = (el.textContent || '').replace(/\s+/g, '');
      if (!text) continue;
      const isConfirm = ['등록', '완료', '확인', '업로드', '추가', '적용'].some((k) => text.includes(k));
      if (!isConfirm) continue;
      if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
      el.click();
      return true;
    }
    return false;
  });

  if (clicked) {
    await page.waitForTimeout(800);
    log.info('업로드 확인/등록 버튼 클릭');
    return true;
  }
  return false;
}

// ────────────────────────────────────────────
// iframe 프레임 획득
// ────────────────────────────────────────────
export async function getEditorFrame(page: Page, artifactsDir: string): Promise<Frame | null> {
  log.info('에디터 iframe 탐색 중...');

  // mainFrame iframe 대기
  try {
    await page.waitForSelector('iframe#mainFrame', { timeout: 15_000 });
  } catch {
    log.warn('iframe#mainFrame 셀렉터 대기 실패, frame name으로 재시도');
  }

  // Frame 객체 획득
  const frame = page.frame('mainFrame');
  if (frame) {
    log.success('에디터 iframe 획득 완료 (name=mainFrame)');
    return frame;
  }

  // fallback: 모든 프레임 탐색
  for (const f of page.frames()) {
    const url = f.url();
    if (url.includes('PostWriteForm') || url.includes('SmartEditor')) {
      log.success(`에디터 iframe 획득 완료 (url=${url.slice(0, 60)})`);
      return f;
    }
  }

  log.error('에디터 iframe을 찾을 수 없습니다');
  await captureFailure(page, 'iframe_not_found', artifactsDir);
  return null;
}

function sanitizeFrameUrl(raw: string): string {
  try {
    const u = new URL(raw);
    return `${u.origin}${u.pathname}`;
  } catch {
    return raw.split('?')[0].slice(0, 160);
  }
}

export function probeEditorIframe(page: Page): EditorIframeProbe {
  const triedSelectors = [
    'iframe#mainFrame',
    'iframe[id*="mainFrame"]',
    'iframe[src*="PostWriteForm"]',
    'iframe[src*="SmartEditor"]',
  ];
  const frames = page.frames();
  const urls = frames
    .map((f) => {
      try {
        return sanitizeFrameUrl(f.url());
      } catch {
        return '';
      }
    })
    .filter(Boolean)
    .slice(-8);
  const expectedFrameUrlPatternMatched = urls.some((u) => /PostWriteForm|SmartEditor|Redirect=Write/i.test(u));
  return {
    expectedFrameUrlPatternMatched,
    frameCount: frames.length,
    triedSelectors,
    lastSeenFrameUrls: urls,
  };
}

export async function getEditorFrameOrThrow(page: Page, artifactsDir: string): Promise<Frame> {
  const frame = await getEditorFrame(page, artifactsDir);
  if (frame) return frame;
  const probe = probeEditorIframe(page);
  throw new EditorIframeNotFoundError('EDITOR_IFRAME_NOT_FOUND', probe);
}

// ────────────────────────────────────────────
// 팝업/안내 레이어 닫기
// ────────────────────────────────────────────
export async function dismissPopups(frame: Frame): Promise<void> {
  const popupSelectors = [
    '.se-popup-button-close',
    '.se-help-panel-close-button',
    '.se-help-panel .se-help-panel-close-button',
    '[class*="help"] button[class*="close"]',
    '.btn_close',
    '[class*="guide"] button[class*="close"]',
    '[class*="tooltip"] button[class*="close"]',
    '.layer_popup .btn_close',
    '.se-popup-alert .se-popup-button-confirm',
    '.se-popup-alert button',
    '.se-popup-confirm button',
    '.se-popup-button-ok',
    '.se-popup-button-confirm',
  ];

  for (const sel of popupSelectors) {
    try {
      const elements = await frame.$$(sel);
      for (const el of elements) {
        if (await el.isVisible()) {
          await el.click();
          await frame.waitForTimeout(300);
          log.info(`팝업 닫기: ${sel}`);
        }
      }
    } catch {
      // 무시
    }
  }

  // "도움말" 텍스트 옆 X 버튼도 시도
  try {
    const closeButtons = await frame.$$('button');
    for (const btn of closeButtons) {
      const ariaLabel = await btn.getAttribute('aria-label');
      if (ariaLabel && (ariaLabel.includes('닫기') || ariaLabel.includes('close'))) {
        if (await btn.isVisible()) {
          const parent = await btn.evaluateHandle((el) => el.closest('[class*="help"], [class*="guide"], [class*="panel"]'));
          if (parent) {
            await btn.click();
            await frame.waitForTimeout(300);
            log.info('도움말/가이드 패널 닫기');
            break;
          }
        }
      }
    }
  } catch {
    // 무시
  }
}

// ────────────────────────────────────────────
// 오버레이/로딩 상태 확인 및 해제
// ────────────────────────────────────────────
async function ensureEditorClear(frame: Frame, page: Page): Promise<void> {
  // 1) 로딩 스피너 대기
  try {
    const spinnerSelectors = ['.se-loading', '[class*="spinner"]', '[class*="loading"]'];
    for (const sel of spinnerSelectors) {
      const spinner = await frame.$(sel);
      if (spinner && await spinner.isVisible()) {
        log.info(`로딩 스피너 감지됨 (${sel}), 사라질 때까지 대기...`);
        await frame.waitForSelector(sel, { state: 'hidden', timeout: 10_000 }).catch(() => {});
      }
    }
  } catch {
    // 무시
  }

  // 2) 팝업/알림 닫기
  await dismissPopups(frame);

  // 3) 오버레이 dim 제거
  try {
    await frame.evaluate(() => {
      document.querySelectorAll<HTMLElement>(
        '.se-popup-dim, .se-popup-dim-transparent, [class*="dimmed"]'
      ).forEach(el => {
        if (el.offsetWidth > 0 && el.offsetHeight > 0) {
          el.style.display = 'none';
          el.style.pointerEvents = 'none';
        }
      });
    });
  } catch {
    // 무시
  }

  // 4) Escape 키로 혹시 남아있는 팝업 닫기
  await page.keyboard.press('Escape').catch(() => {});
  await frame.waitForTimeout(200);
}

// ────────────────────────────────────────────
// 에디터 로딩 대기 (iframe 내부)
// ────────────────────────────────────────────
export async function waitForEditorReady(
  frame: Frame,
  artifactsDir: string,
  page: Page,
  options?: {
    timeBudgetMs?: number;
    perSelectorTimeoutMs?: number;
    pollIntervalMs?: number;
    reacquireFrame?: () => Promise<Frame | null>;
    allowPageReloadRecovery?: boolean;
  },
): Promise<boolean> {
  log.info('에디터 내부 로딩 대기 중...');
  const timeBudgetMs = options?.timeBudgetMs ?? 45_000;
  const perSelectorTimeoutMs = options?.perSelectorTimeoutMs ?? 700;
  const pollIntervalMs = options?.pollIntervalMs ?? 2_000;
  const allowPageReloadRecovery = options?.allowPageReloadRecovery ?? false;
  const deadline = Date.now() + timeBudgetMs;
  const recoveryThresholdMs = Math.floor(timeBudgetMs * 0.5);
  let activeFrame = frame;
  let attempt = 0;
  let spinnerSeenEver = false;
  let recoveryUsed = false;
  let recoveryCount = 0;

  const reacquireEditorFrame = async (): Promise<Frame | null> => {
    if (options?.reacquireFrame) {
      return await options.reacquireFrame();
    }
    try {
      const iframe = await page.$('iframe#mainFrame, iframe[id*="mainFrame"], iframe[src*="PostWriteForm"], iframe[src*="SmartEditor"]');
      if (iframe) {
        const byHandle = await iframe.contentFrame();
        if (byHandle) return byHandle;
      }
    } catch {
      // ignore
    }
    const byName = page.frame('mainFrame');
    if (byName) return byName;
    for (const f of page.frames()) {
      const url = f.url();
      if (url.includes('PostWriteForm') || url.includes('SmartEditor')) return f;
    }
    return null;
  };

  const probeReadyState = async (targetFrame: Frame): Promise<{
    editorRootFound: boolean;
    contentEditableFound: boolean;
    toolbarReady: boolean;
    focusOk: boolean;
    spinnerVisible: boolean;
  }> => {
    const frameUrl = (() => {
      try {
        return targetFrame.url();
      } catch {
        return '';
      }
    })();
    try {
      const state = await targetFrame.evaluate(() => {
        const isVisible = (el: Element | null): boolean => {
          if (!(el instanceof HTMLElement)) return false;
          const rect = el.getBoundingClientRect();
          if (rect.width <= 2 || rect.height <= 2) return false;
          const style = window.getComputedStyle(el);
          return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        };
        const editorRoot = document.querySelector('.se-component, .se-content, .se-main-container, .se-document');
        const editorRootFound = isVisible(editorRoot) || Boolean(editorRoot);
        const editables = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"]'));
        const contentEditableFound = editables.some((el) => {
          if (el.closest('.se-documentTitle')) return false;
          return isVisible(el);
        });
        const toolbarReady = Array.from(
          document.querySelectorAll<HTMLElement>('.se-toolbar button, .se-tool button, .se-toolbar [role="button"], [class*="toolbar"] button'),
        ).some((el) => isVisible(el));
        const activeEl = document.activeElement as HTMLElement | null;
        const focusOk = Boolean(
          activeEl
          && (
            activeEl.closest('.se-component, .se-content, .se-main-container, .se-document')
            || activeEl.isContentEditable
          ),
        );
        const spinnerVisible = Array.from(
          document.querySelectorAll<HTMLElement>('.se-loading, [class*="spinner"], [class*="loading"], [class*="save_ing"]'),
        ).some((el) => isVisible(el));
        return {
          editorRootFound,
          contentEditableFound,
          toolbarReady,
          focusOk,
          spinnerVisible,
        };
      });
      return {
        editorRootFound: state.editorRootFound,
        contentEditableFound: state.contentEditableFound,
        toolbarReady: state.toolbarReady,
        focusOk: state.focusOk,
        spinnerVisible: state.spinnerVisible,
      };
    } catch {
      return {
        editorRootFound: /PostWriteForm|SmartEditor/i.test(frameUrl),
        contentEditableFound: false,
        toolbarReady: false,
        focusOk: false,
        spinnerVisible: false,
      };
    }
  };

  const runRecovery = async (): Promise<void> => {
    recoveryUsed = true;
    recoveryCount += 1;
    log.warn('[editor-ready-recovery] 프레임/포커스 재획득 시도');
    const refreshed = await reacquireEditorFrame();
    if (refreshed) {
      activeFrame = refreshed;
    }
    const focusSelectors = [
      '.se-content [contenteditable="true"]',
      '.se-component [contenteditable="true"]',
      '.se-main-container [contenteditable="true"]',
      '[contenteditable="true"]',
    ];
    for (const sel of focusSelectors) {
      try {
        const loc = activeFrame.locator(sel).first();
        if (await loc.count()) {
          await loc.click({ timeout: Math.min(800, perSelectorTimeoutMs), force: true });
          break;
        }
      } catch {
        // 다음 selector 시도
      }
    }
    if (allowPageReloadRecovery) {
      try {
        await page.reload({ waitUntil: 'domcontentloaded', timeout: Math.max(5_000, perSelectorTimeoutMs * 5) });
        const reloadedFrame = await reacquireEditorFrame();
        if (reloadedFrame) activeFrame = reloadedFrame;
      } catch (error) {
        log.warn(`[editor-ready-recovery] reload 실패: ${error}`);
      }
    }
  };

  while (Date.now() < deadline) {
    attempt += 1;
    const sessionBlocked = await probeSessionExpired(page);
    if (sessionBlocked) {
      lastEditorReadyProbeSummary = {
        success: false,
        reason: 'session_blocked',
        attempts: attempt,
        budgetMs: timeBudgetMs,
        elapsedMs: timeBudgetMs - Math.max(0, deadline - Date.now()),
        recoveryAttempted: recoveryUsed,
        recoveryCount,
      };
      throw new Error('[SESSION_BLOCKED] 로그인/인증/권한 차단 감지');
    }

    const maybeFrame = await reacquireEditorFrame();
    const frameFound = Boolean(maybeFrame ?? activeFrame);
    if (maybeFrame) {
      activeFrame = maybeFrame;
    }

    const frameAttached = !activeFrame.isDetached();
    const frameUrl = (() => {
      try {
        return activeFrame.url();
      } catch {
        return '';
      }
    })();

    let snapshot: EditorReadyProbeSnapshot = {
      attempt,
      elapsedMs: timeBudgetMs - Math.max(0, deadline - Date.now()),
      frameUrl,
      probes: {
        frameFound,
        frameAttached,
        editorRootFound: false,
        contentEditableFound: false,
        toolbarReady: false,
        focusOk: false,
        sessionBlocked,
        spinnerVisible: false,
        spinnerCycleDone: false,
      },
      recoveryAttempted: recoveryUsed,
    };

    let ready = false;
    if (frameAttached) {
      const probe = await probeReadyState(activeFrame);
      if (probe.spinnerVisible) spinnerSeenEver = true;
      const spinnerCycleDone = spinnerSeenEver && !probe.spinnerVisible;
      snapshot = {
        ...snapshot,
        probes: {
          ...snapshot.probes,
          editorRootFound: probe.editorRootFound,
          contentEditableFound: probe.contentEditableFound,
          toolbarReady: probe.toolbarReady,
          focusOk: probe.focusOk,
          spinnerVisible: probe.spinnerVisible,
          spinnerCycleDone,
        },
      };
      // 일부 에디터 버전은 초기 진입 시 contenteditable이 지연 노출되므로
      // editor root + toolbar가 준비되면 일단 진행하고 입력 단계에서 재검증한다.
      const editorInteractionReady =
        probe.contentEditableFound || (probe.editorRootFound && probe.toolbarReady);
      ready = frameFound && frameAttached && editorInteractionReady;
      lastEditorReadyProbeSummary = {
        success: ready,
        attempts: attempt,
        budgetMs: timeBudgetMs,
        elapsedMs: snapshot.elapsedMs,
        recoveryAttempted: recoveryUsed,
        recoveryCount,
        lastSnapshot: snapshot,
      };

      log.info(
        `[editor-ready-probe] attempt=${snapshot.attempt} frame_found=${snapshot.probes.frameFound} attached=${snapshot.probes.frameAttached} ` +
          `editor_root=${snapshot.probes.editorRootFound} editable=${snapshot.probes.contentEditableFound} ` +
          `toolbar=${snapshot.probes.toolbarReady} focus=${snapshot.probes.focusOk} spinner_cycle=${snapshot.probes.spinnerCycleDone}`,
      );

      if (ready) {
        log.success('에디터 로딩 완료 (multi-signal)');
        await activeFrame.waitForTimeout(200).catch(() => undefined);
        await dismissPopups(activeFrame);
        return true;
      }
    } else {
      lastEditorReadyProbeSummary = {
        success: false,
        reason: 'frame_detached',
        attempts: attempt,
        budgetMs: timeBudgetMs,
        elapsedMs: snapshot.elapsedMs,
        recoveryAttempted: recoveryUsed,
        recoveryCount,
        lastSnapshot: snapshot,
      };
    }

    const elapsed = timeBudgetMs - Math.max(0, deadline - Date.now());
    if (!ready && !recoveryUsed && elapsed >= recoveryThresholdMs) {
      await runRecovery();
    }
    const remain = deadline - Date.now();
    if (remain <= 0) break;
    await page.waitForTimeout(Math.min(pollIntervalMs, Math.max(250, remain), perSelectorTimeoutMs)).catch(() => undefined);
  }

  const probeSummary = lastEditorReadyProbeSummary
    ? JSON.stringify(lastEditorReadyProbeSummary)
    : '{"summary":"none"}';
  log.error(`[editor-ready-timeout] frame_attached=${!activeFrame.isDetached()} summary=${probeSummary}`);
  await captureFailure(page, 'editor_not_ready', artifactsDir);
  throw new Error(`[EDITOR_READY_TIMEOUT] budgetMs=${timeBudgetMs} summary=${probeSummary}`);
}

// ────────────────────────────────────────────
// 제목 입력
// ────────────────────────────────────────────
export async function inputTitle(
  ctx: EditorContext,
  title: string,
  artifactsDir: string
): Promise<boolean> {
  const normalizedTitle = title.trim();
  log.info(`제목 입력: "${normalizedTitle}"`);
  const { page, frame } = ctx;

  await dismissPopups(frame);
  await frame.waitForTimeout(500);

  const targetSelectors = [
    '.se-documentTitle [contenteditable="true"]',
    '.se-documentTitle .se-text-paragraph',
    '[placeholder="제목"]',
    '.se-documentTitle [role="textbox"]',
  ];

  const strategies: Array<() => Promise<boolean>> = [
    async () => {
      for (const selector of targetSelectors) {
        const locator = frame.locator(selector).first();
        if (await locator.count() === 0) continue;

        try {
          await locator.click({ force: true });
          await page.keyboard.press('Control+A');
          await page.keyboard.press('Backspace');
          await page.keyboard.insertText(normalizedTitle);
          await frame.waitForTimeout(250);

          const titleAreaText = await frame.evaluate(() => {
            const root = document.querySelector('.se-documentTitle');
            return (root?.textContent || '').replace(/\s+/g, ' ').trim();
          });

          if (titleAreaText.includes(normalizedTitle.slice(0, Math.min(8, normalizedTitle.length)))) {
            log.info(`제목 read-back 확인: "${titleAreaText}"`);
            return true;
          }
        } catch {
          // 다음 selector 시도
        }
      }
      return false;
    },
  ];

  for (const [i, strategy] of strategies.entries()) {
    try {
      if (await strategy()) {
        log.success(`제목 입력 완료 (전략 ${i + 1})`);
        return true;
      }
    } catch (e) {
      log.warn(`제목 입력 전략 ${i + 1} 실패: ${e}`);
    }
  }

  log.error('제목 입력 실패');
  await captureFailure(page, 'title_input_failed', artifactsDir);
  return false;
}

// ────────────────────────────────────────────
// 본문 입력 (기존 호환)
// ────────────────────────────────────────────
export async function inputBody(
  ctx: EditorContext,
  body: string,
  artifactsDir: string
): Promise<boolean> {
  log.info(`본문 입력 시작 (${body.length}자)`);
  const { page, frame } = ctx;

  const typeBodyLines = async () => {
    const lines = body.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].trim().length > 0) {
        await page.keyboard.insertText(lines[i]);
      }
      if (i < lines.length - 1) {
        await page.keyboard.press('Enter');
      }
    }
  };

  const strategies = [
    async () => {
      const titleLocator = frame.locator('.se-documentTitle [contenteditable="true"], .se-documentTitle .se-text-paragraph').first();
      if (await titleLocator.count() === 0) return false;
      await titleLocator.click({ force: true });
      await page.keyboard.press('End');
      await page.keyboard.press('Enter');
      await typeBodyLines();
      await frame.waitForTimeout(400);
      return true;
    },
    async () => {
      const selectors = [
        '.se-components-content .se-text-paragraph[contenteditable="true"]',
        '.se-component-text .se-text-paragraph[contenteditable="true"]',
        '.se-main-container [contenteditable="true"]',
        '.se-content [contenteditable="true"]',
      ];
      for (const selector of selectors) {
        const candidates = await frame.$$(selector);
        for (const candidate of candidates) {
          if (!(await candidate.isVisible())) continue;
          if (await candidate.evaluate((el) => !!el.closest('.se-documentTitle'))) continue;
          await candidate.click({ force: true });
          await typeBodyLines();
          await frame.waitForTimeout(300);
          return true;
        }
      }
      return false;
    },
  ];

  for (const [i, strategy] of strategies.entries()) {
    try {
      if (await strategy()) {
        log.success(`본문 입력 완료 (전략 ${i + 1})`);
        return true;
      }
    } catch (e) {
      log.warn(`본문 입력 전략 ${i + 1} 실패: ${e}`);
    }
  }

  log.error('본문 입력 실패');
  await captureFailure(page, 'body_input_failed', artifactsDir);
  return false;
}

async function captureTitleBodyKeyboardDebug(
  ctx: EditorContext,
  title: string,
  body: string,
  reason: string,
): Promise<string | undefined> {
  try {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const debugDir = path.join('/tmp/naver_editor_debug', `${ts}_title_to_body_enter_fail`);
    fs.mkdirSync(debugDir, { recursive: true });
    await ctx.page.screenshot({ path: path.join(debugDir, 'page.png'), fullPage: true }).catch(() => undefined);
    const frameList = ctx.page.frames().map((f) => ({ name: f.name(), url: f.url() }));
    const probe = await ctx.frame.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      const titleEl = document.querySelector<HTMLElement>('.se-documentTitle');
      const bodyEditable = document.querySelector<HTMLElement>(
        '.se-components-content [contenteditable="true"], .se-main-container [contenteditable="true"], .se-content [contenteditable="true"]',
      );
      return {
        activeElement: active
          ? { tag: active.tagName, className: active.className, contentEditable: active.contentEditable }
          : null,
        titleText: (titleEl?.textContent || '').replace(/\s+/g, ' ').trim(),
        bodyEditableTag: bodyEditable?.tagName || null,
      };
    }).catch(() => null);
    fs.writeFileSync(path.join(debugDir, 'title_body_debug.json'), JSON.stringify({
      at: new Date().toISOString(),
      reason,
      frameList,
      pageUrl: ctx.page.url(),
      frameUrl: ctx.frame.url(),
      titleSample: title.slice(0, 120),
      bodySample: extractVerificationSample(body),
      probe,
    }, null, 2), 'utf-8');
    return debugDir;
  } catch {
    return undefined;
  }
}

async function resolveEditableFrameForBody(ctx: EditorContext): Promise<Frame | null> {
  const candidates = [ctx.frame, ...ctx.page.frames()];
  for (const frame of candidates) {
    const ok = await frame.evaluate(() => {
      const editables = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"]'))
        .filter((el) => !el.closest('.se-documentTitle'));
      return editables.length > 0;
    }).catch(() => false);
    if (ok) return frame;
  }
  return null;
}

export async function writeTitleThenBodyViaKeyboard(
  ctx: EditorContext,
  title: string,
  body: string,
): Promise<boolean> {
  const normalizedTitle = title.trim();
  const normalizedBody = sanitizeForEditor(body.trim());
  if (!normalizedTitle) return false;

  try {
    return await withTimeout(async () => {
      const { page } = ctx;
      let frame = ctx.frame;
      await dismissPopups(frame).catch(() => undefined);

      const titleSelectors = [
        '.se-documentTitle [contenteditable="true"]',
        '.se-documentTitle .se-text-paragraph',
        '[placeholder="제목"]',
        '.se-documentTitle [role="textbox"]',
      ];
      let titleFocused = false;
      for (const selector of titleSelectors) {
        const loc = frame.locator(selector).first();
        if ((await loc.count()) === 0) continue;
        try {
          await loc.click({ force: true });
          await page.keyboard.press('Control+A');
          await page.keyboard.press('Backspace');
          await page.keyboard.type(normalizedTitle, { delay: 0 });
          titleFocused = true;
          break;
        } catch {
          // try next selector
        }
      }
      if (!titleFocused) {
        const debugPath = await captureTitleBodyKeyboardDebug(ctx, normalizedTitle, normalizedBody, 'title_focus_failed');
        log.error(`[title-body] title focus failed debugPath=${debugPath ?? 'n/a'}`);
        return false;
      }

      const titleConfirmed = await frame.evaluate((needle) => {
        const text = (document.querySelector('.se-documentTitle')?.textContent || '').replace(/\s+/g, ' ').trim();
        return text.includes(needle.slice(0, Math.min(10, needle.length)));
      }, normalizedTitle).catch(() => false);
      if (!titleConfirmed) {
        const debugPath = await captureTitleBodyKeyboardDebug(ctx, normalizedTitle, normalizedBody, 'title_verify_failed');
        log.error(`[title-body] title verify failed debugPath=${debugPath ?? 'n/a'}`);
        return false;
      }

      for (const key of TITLE_TO_BODY_ENTER_SEQUENCE) {
        await page.keyboard.press(key).catch(() => undefined);
        await frame.waitForTimeout(150 + Math.floor(Math.random() * 251)).catch(() => undefined);
      }

      const editableFrame = await resolveEditableFrameForBody(ctx);
      if (editableFrame) {
        frame = editableFrame;
        ctx.frame = editableFrame;
      }

      let focusInBody = await verifyFocusInBody(frame);
      if (!focusInBody) {
        const clicked = await frame.evaluate(() => {
          const nodes = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"]'))
            .filter((el) => !el.closest('.se-documentTitle'));
          const target = nodes.find((el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 20 && rect.height > 12 && style.display !== 'none' && style.visibility !== 'hidden';
          }) || nodes[0];
          if (!target) return false;
          target.click();
          target.focus();
          return true;
        }).catch(() => false);
        if (clicked) {
          await frame.waitForTimeout(120).catch(() => undefined);
          focusInBody = await verifyFocusInBody(frame);
        }
      }

      if (!focusInBody) {
        const debugPath = await captureTitleBodyKeyboardDebug(ctx, normalizedTitle, normalizedBody, 'body_focus_failed');
        log.error(`[title-body] body focus failed debugPath=${debugPath ?? 'n/a'}`);
        return false;
      }

      if (normalizedBody.length > 0) {
        const lines = normalizedBody.split('\n');
        for (let i = 0; i < lines.length; i++) {
          if (lines[i].length > 0) {
            await page.keyboard.type(lines[i], { delay: 0 }).catch(() => undefined);
          }
          if (i < lines.length - 1) {
            await page.keyboard.press('Enter').catch(() => undefined);
          }
        }
      }

      const bodySample = extractVerificationSample(normalizedBody).slice(0, 30);
      const bodySeen = bodySample ? await verifyTextInEditorWithRetry(frame, bodySample, 2_000) : true;
      const activeEditable = await frame.evaluate(() => {
        const active = document.activeElement as HTMLElement | null;
        if (!active) return false;
        if (active.contentEditable === 'true' && !active.closest('.se-documentTitle')) return true;
        return !!active.closest('.se-components-content, .se-main-container, .se-content');
      }).catch(() => false);

      const ok = titleConfirmed && (bodySeen || activeEditable);
      if (!ok) {
        const debugPath = await captureTitleBodyKeyboardDebug(ctx, normalizedTitle, normalizedBody, 'body_verify_failed');
        log.error(`[title-body] body verify failed debugPath=${debugPath ?? 'n/a'}`);
      }
      return ok;
    }, 10_000, 'writeTitleThenBodyViaKeyboard timeout');
  } catch (error) {
    const debugPath = await captureTitleBodyKeyboardDebug(ctx, normalizedTitle, normalizedBody, String(error));
    log.error(`[title-body] keyboard flow timeout/error debugPath=${debugPath ?? 'n/a'} error=${error}`);
    return false;
  }
}

// ────────────────────────────────────────────
// 본문 끝으로 포커스 이동 (매번 element를 새로 탐색)
// ────────────────────────────────────────────
async function focusBodyEnd(ctx: EditorContext): Promise<boolean> {
  const { frame, page } = ctx;

  // 매번 element를 새로 탐색 (stale element 방지)
  const focused = await frame.evaluate(() => {
    const candidates = Array.from(
      document.querySelectorAll<HTMLElement>(
        '.se-component.se-text .se-text-paragraph, ' +
        '.se-section-text .se-text-paragraph, ' +
        '.se-component-text .se-text-paragraph[contenteditable="true"], ' +
        '.se-components-content [contenteditable="true"], ' +
        '.se-main-container [contenteditable="true"], ' +
        '.se-content [contenteditable="true"]',
      ),
    ).filter((el) => {
      if (el.closest('.se-documentTitle')) return false;
      if (el.id && el.id.startsWith('input_buffer')) return false;
      const rect = el.getBoundingClientRect();
      if (rect.width < 40 || rect.height < 16) return false;
      return true;
    });

    const target = candidates[candidates.length - 1];
    if (!target) return false;

    // scrollIntoView: 에디터 영역이 뷰포트 밖이면 입력이 안 될 수 있음
    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    target.click();
    target.focus();
    const selection = window.getSelection();
    if (!selection) return false;
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  });

  if (!focused) {
    const fallback = frame.locator(
      '.se-components-content [contenteditable="true"], .se-main-container [contenteditable="true"]'
    ).first();
    if ((await fallback.count()) === 0) return false;
    await fallback.click({ force: true });
  }

  await page.keyboard.press('End').catch(() => undefined);
  return true;
}

async function getUsableBodyEditableCount(frame: Frame): Promise<number> {
  try {
    return await frame.evaluate(() => {
      return Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text .se-text-paragraph, .se-section-text .se-text-paragraph, .se-component.se-text [contenteditable="true"]',
        ),
      )
        .filter((el) => {
          if (el.closest('.se-documentTitle')) return false;
          if (el.id && el.id.startsWith('input_buffer')) return false;
          const rect = el.getBoundingClientRect();
          return rect.width >= 40 && rect.height >= 16;
        })
        .length;
    });
  } catch {
    return 0;
  }
}

async function ensureBodyEditableReady(ctx: EditorContext): Promise<boolean> {
  const { frame, page } = ctx;
  let count = await getUsableBodyEditableCount(frame);
  if (count > 0) return true;

  const titleSelectors = [
    '.se-documentTitle [contenteditable="true"]',
    '.se-documentTitle .se-text-paragraph',
    '[placeholder="제목"]',
  ];
  for (const sel of titleSelectors) {
    const title = frame.locator(sel).first();
    if ((await title.count()) === 0) continue;
    try {
      await title.click({ force: true });
      await page.keyboard.press('End');
      await page.keyboard.press('Enter');
      await frame.waitForTimeout(250);
      count = await getUsableBodyEditableCount(frame);
      if (count > 0) return true;
    } catch {
      // 다음 셀렉터 시도
    }
  }

  // 제목 엔터로 본문이 생성되지 않으면 본문 영역 직접 클릭 후 엔터
  try {
    const contentRoot = frame.locator('.se-content, .se-main-container, .se-components').first();
    if ((await contentRoot.count()) > 0) {
      await contentRoot.click({ force: true, position: { x: 40, y: 120 } });
      await page.keyboard.press('Enter');
      await frame.waitForTimeout(250);
      count = await getUsableBodyEditableCount(frame);
      if (count > 0) return true;
    }
  } catch {
    // 무시
  }

  return false;
}

// ────────────────────────────────────────────
// activeElement가 에디터 본문 영역인지 확인
// ────────────────────────────────────────────
async function verifyFocusInBody(frame: Frame): Promise<boolean> {
  return frame.evaluate(() => {
    const ae = document.activeElement;
    if (!ae) return false;
    if (ae.tagName === 'IFRAME' && (ae as HTMLIFrameElement).id?.startsWith('input_buffer')) {
      const selection = window.getSelection();
      const node = selection?.anchorNode;
      const element = node instanceof HTMLElement ? node : node?.parentElement;
      if (!element) return false;
      if (element.closest('.se-documentTitle')) return false;
      return !!element.closest('.se-component.se-text, .se-section-text, .se-content');
    }
    const active = ae as HTMLElement;
    if (active.contentEditable === 'true' && !active.closest('.se-documentTitle')) {
      // 에디터 버전에 따라 본문 editable이 se-content 하위가 아닌 경우가 있어 contenteditable 자체를 우선 신뢰
      return true;
    }
    if (active.closest('.se-documentTitle')) return false;
    return !!(active.closest('.se-components-content') || active.closest('.se-main-container') || active.closest('.se-content'));
  });
}

// ────────────────────────────────────────────
// 에디터 본문에 텍스트가 존재하는지 검증
// ────────────────────────────────────────────
async function verifyTextInEditor(frame: Frame, sample: string): Promise<boolean> {
  if (!sample || sample.length < 2) return true;
  try {
    return await frame.evaluate((sampleText) => {
      const bodyAreas = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text, .se-section-text, .se-components-content, .se-main-container, .se-content'
        )
      ).filter(el => !el.closest('.se-documentTitle'));

      for (const area of bodyAreas) {
        const text = (area.innerText || area.textContent || '').replace(/\s+/g, ' ');
        if (text.includes(sampleText)) return true;
      }
      return false;
    }, sample);
  } catch {
    return false;
  }
}

async function getEditorPlainText(frame: Frame): Promise<string> {
  try {
    return await frame.evaluate(() => {
      const bodyAreas = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text, .se-section-text, .se-components-content, .se-main-container, .se-content',
        ),
      ).filter((el) => !el.closest('.se-documentTitle'));
      return bodyAreas.map((area) => area.innerText || area.textContent || '').join('\n');
    });
  } catch {
    return '';
  }
}

async function collectBlockContextHtml(frame: Frame): Promise<string[]> {
  try {
    return await frame.evaluate(() => {
      const nodes = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text, .se-section-text, .se-component, .se-main-container [contenteditable="true"]',
        ),
      )
        .filter((el) => !el.closest('.se-documentTitle'))
        .slice(-3);
      return nodes.map((node) => node.outerHTML.slice(0, 1200));
    });
  } catch {
    return [];
  }
}

async function getActiveElementSnapshot(frame: Frame): Promise<{
  tagName: string;
  className: string;
  isContentEditable: boolean;
  selectionCollapsed: boolean;
}> {
  try {
    return await frame.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      const selection = window.getSelection();
      return {
        tagName: active?.tagName ?? 'NONE',
        className: active?.className ?? '',
        isContentEditable: Boolean(active?.isContentEditable || active?.getAttribute('contenteditable') === 'true'),
        selectionCollapsed: selection ? selection.isCollapsed : true,
      };
    });
  } catch {
    return {
      tagName: 'ERR',
      className: '',
      isContentEditable: false,
      selectionCollapsed: true,
    };
  }
}

async function diagnoseVerificationFailure(
  frame: Frame,
  expectedText: string,
): Promise<{
  reason: TextInputFailureReason;
  expectedAnchors: VerificationAnchors;
  matchedAnchors: number;
  normalizedExpected: string;
  normalizedObserved: string;
  observedTextSample: string;
}> {
  const focusInBody = await verifyFocusInBody(frame);
  if (!focusInBody) {
    return {
      reason: TextInputFailureReason.VERIFICATION_FAILED_FOCUS_LOST,
      expectedAnchors: buildVerificationAnchors(expectedText),
      matchedAnchors: 0,
      normalizedExpected: normalizeForVerification(expectedText),
      normalizedObserved: '',
      observedTextSample: '',
    };
  }

  const observedRaw = await getEditorPlainText(frame);
  const compared = evaluateVerificationAgainstObserved(expectedText, observedRaw);
  const observedTextSample = compared.normalizedObserved.slice(0, 1024);
  if (compared.normalizedObserved.length === 0) {
    return {
      reason: TextInputFailureReason.VERIFICATION_FAILED_EDITOR_BLOCK_NOT_CREATED,
      expectedAnchors: compared.anchors,
      matchedAnchors: compared.matchedAnchors,
      normalizedExpected: compared.normalizedExpected,
      normalizedObserved: compared.normalizedObserved,
      observedTextSample,
    };
  }
  if (compared.matchedAnchors === 0) {
    return {
      reason: TextInputFailureReason.VERIFICATION_FAILED_TEXT_NOT_FOUND,
      expectedAnchors: compared.anchors,
      matchedAnchors: compared.matchedAnchors,
      normalizedExpected: compared.normalizedExpected,
      normalizedObserved: compared.normalizedObserved,
      observedTextSample,
    };
  }
  return {
    reason: TextInputFailureReason.VERIFICATION_FAILED_TEXT_MISMATCH,
    expectedAnchors: compared.anchors,
    matchedAnchors: compared.matchedAnchors,
    normalizedExpected: compared.normalizedExpected,
    normalizedObserved: compared.normalizedObserved,
    observedTextSample,
  };
}

async function verifyTextInEditorWithRetry(
  frame: Frame,
  sample: string,
  timeoutMs: number = 1800,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() <= deadline) {
    if (await verifyTextInEditor(frame, sample)) return true;
    await frame.waitForTimeout(120);
  }
  return false;
}

async function getBodyTextLength(frame: Frame): Promise<number> {
  try {
    return await frame.evaluate(() => {
      const areas = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text, .se-section-text, .se-components-content, .se-main-container, .se-content',
        ),
      ).filter((el) => !el.closest('.se-documentTitle'));
      const text = areas.map((el) => el.innerText || el.textContent || '').join('\n');
      return text.replace(/\s+/g, ' ').trim().length;
    });
  } catch {
    return 0;
  }
}

async function verifyChunkApplied(
  frame: Frame,
  sample: string,
  beforeLen: number,
  chunk: string,
): Promise<boolean> {
  const observedRaw = await getEditorPlainText(frame);
  const compared = evaluateVerificationAgainstObserved(sample, observedRaw);
  if (compared.ok) return true;
  const retryOk = await verifyTextInEditorWithRetry(frame, extractVerificationSample(sample));
  if (retryOk) return true;
  const afterLen = await getBodyTextLength(frame);
  const minGrowth = Math.max(8, Math.floor(chunk.replace(/\s+/g, '').length * 0.35));
  return afterLen >= beforeLen + minGrowth;
}

type TextBlockInputResult = {
  success: boolean;
  failureReason?: TextInputFailureReason;
  attempts: TextInputAttempt[];
  debugDir?: string;
};

export function buildDebugFixture(
  blocks: PostBlock[],
  imagePaths: string[],
  failedIdx: number,
  reason: string,
  attempts?: TextInputAttempt[],
): DebugFixturePayload {
  return {
    failed_block_index: failedIdx,
    failure_reason: reason,
    total_blocks: blocks.length,
    blocks: blocks.map((b, i) => ({
      index: i,
      type: b.type,
      content: b.type === 'text' || b.type === 'section_title' ? b.content : undefined,
      content_length: b.type === 'text' || b.type === 'section_title' ? b.content.length : undefined,
      content_hash: b.type === 'text' || b.type === 'section_title' ? sampleHash(b.content, 80) : undefined,
      image_index: b.type === 'image' ? b.index : undefined,
      marker: b.type === 'image' ? b.marker : undefined,
    })),
    image_paths: imagePaths.map((p) => path.resolve(p)),
    attempts,
    timestamp: new Date().toISOString(),
  };
}

function saveDebugFixture(debugDir: string, payload: DebugFixturePayload): void {
  fs.mkdirSync(debugDir, { recursive: true });
  const fixturePath = path.join(debugDir, 'debug_fixture.json');
  fs.writeFileSync(fixturePath, JSON.stringify(payload, null, 2), 'utf-8');
  log.info(`[debug] fixture 저장: ${fixturePath}`);
}

type BlockVerificationDebugPayload = {
  stageName: string;
  blockIndex: number;
  attempt: number;
  elapsedMs: number;
  expectedProbe: {
    textHash: string;
    anchors: VerificationAnchors;
  };
  observed: {
    activeElement: {
      tagName: string;
      isContentEditable: boolean;
      className: string;
    };
    selectionCollapsed: boolean;
    editorFrameUrl: string;
    editorHtmlSnippet: string[];
    plainTextSnapshot: string;
    plainTextHash: string;
  };
  inputMethod: string;
  sanitizedLength: number;
  originalLength: number;
  reasonCode: TextInputFailureReason;
};

function buildBlockVerificationDebugDir(blockIndex?: number): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const suffix = typeof blockIndex === 'number' ? `block${blockIndex + 1}` : 'blockx';
  return path.join('/tmp/naver_editor_debug', `${stamp}_${suffix}_verification_fail`);
}

async function writeFrameList(page: Page, outputPath: string): Promise<void> {
  const lines = page.frames().map((f, i) => `[${i}] ${f.url()}`);
  fs.writeFileSync(outputPath, lines.join('\n'), 'utf-8');
}

async function captureBlockVerificationDebug(
  ctx: EditorContext,
  payload: BlockVerificationDebugPayload,
): Promise<string> {
  const debugDir = buildBlockVerificationDebugDir(payload.blockIndex - 1);
  fs.mkdirSync(debugDir, { recursive: true });
  try {
    await ctx.page.screenshot({ path: path.join(debugDir, 'page.png'), fullPage: true });
  } catch {
    // ignore
  }
  try {
    const html = await ctx.frame.content();
    fs.writeFileSync(path.join(debugDir, 'editor.html'), html, 'utf-8');
  } catch {
    // ignore
  }
  try {
    await writeFrameList(ctx.page, path.join(debugDir, 'frame_list.txt'));
  } catch {
    // ignore
  }
  fs.writeFileSync(path.join(debugDir, 'block_debug.json'), JSON.stringify(payload, null, 2), 'utf-8');
  return debugDir;
}

async function runSendKeysStrategy(
  ctx: EditorContext,
  frame: Frame,
  page: Page,
  chunks: string[],
  attempts: TextInputAttempt[],
): Promise<{ ok: boolean; reason?: TextInputFailureReason }> {
  for (let ci = 0; ci < chunks.length; ci++) {
    const started = Date.now();
    const chunk = chunks[ci];
    const chunkSample = extractVerificationSample(chunk);
    const beforeSignature = await getEditorDomSignature(frame);
    const beforeLen = await getBodyTextLength(frame);

    if (await isEditorOverlayBlocking(frame)) {
      attempts.push({
        strategy: 'strategy1_sendkeys',
        chunkIndex: ci,
        chunkLength: chunk.length,
        success: false,
        reason: TextInputFailureReason.OVERLAY_BLOCKING,
        elapsedMs: Date.now() - started,
      });
      return { ok: false, reason: TextInputFailureReason.OVERLAY_BLOCKING };
    }

    const focused = await focusBodyEnd(ctx);
    if (!focused || !(await verifyFocusInBody(frame))) {
      attempts.push({
        strategy: 'strategy1_sendkeys',
        chunkIndex: ci,
        chunkLength: chunk.length,
        success: false,
        reason: TextInputFailureReason.FOCUS_FAILED,
        elapsedMs: Date.now() - started,
      });
      return { ok: false, reason: TextInputFailureReason.FOCUS_FAILED };
    }

    const lines = chunk.split('\n');
    for (let li = 0; li < lines.length; li++) {
      if (lines[li].length > 0) {
        await page.keyboard.insertText(lines[li]);
      }
      if (li < lines.length - 1) {
        await page.keyboard.press('Enter');
      }
    }
    if (ci < chunks.length - 1) {
      await page.keyboard.press('Enter');
    }
    await frame.waitForTimeout(120);

    const verified = chunkSample ? await verifyChunkApplied(frame, chunk, beforeLen, chunk) : true;
    const afterSignature = await getEditorDomSignature(frame);
    if (!verified) {
      const stale = beforeSignature !== afterSignature;
      let reason: TextInputFailureReason = stale
        ? TextInputFailureReason.VERIFICATION_FAILED_FRAME_CHANGED
        : TextInputFailureReason.VERIFICATION_FAILED_TEXT_NOT_FOUND;
      if (!(await verifyFocusInBody(frame))) {
        reason = TextInputFailureReason.VERIFICATION_FAILED_FOCUS_LOST;
      }
      attempts.push({
        strategy: 'strategy1_sendkeys',
        chunkIndex: ci,
        chunkLength: chunk.length,
        success: false,
        reason,
        elapsedMs: Date.now() - started,
      });
      return { ok: false, reason };
    }

    attempts.push({
      strategy: 'strategy1_sendkeys',
      chunkIndex: ci,
      chunkLength: chunk.length,
      success: true,
      elapsedMs: Date.now() - started,
    });
  }
  return { ok: true };
}

async function runJsInputStrategy(
  ctx: EditorContext,
  frame: Frame,
  page: Page,
  chunks: string[],
  attempts: TextInputAttempt[],
): Promise<{ ok: boolean; reason?: TextInputFailureReason }> {
  for (let ci = 0; ci < chunks.length; ci++) {
    const started = Date.now();
    const chunk = chunks[ci];
    const chunkSample = extractVerificationSample(chunk);
    const beforeSignature = await getEditorDomSignature(frame);
    const beforeLen = await getBodyTextLength(frame);

  const result = await frame.evaluate((text) => {
      const candidates = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component.se-text .se-text-paragraph, .se-section-text .se-text-paragraph, ' +
          '.se-component-text .se-text-paragraph[contenteditable="true"], .se-components-content [contenteditable="true"], .se-main-container [contenteditable="true"], .se-content [contenteditable="true"]',
        ),
      ).filter((el) => !el.closest('.se-documentTitle'));
      if (candidates.length === 0) return { ok: false, reason: 'editor_not_found' };

      const target = candidates[candidates.length - 1];
      target.scrollIntoView({ block: 'center', behavior: 'instant' });
      target.focus();

      const selection = window.getSelection();
      if (selection) {
        const range = document.createRange();
        range.selectNodeContents(target);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
      }

      const inserted = document.execCommand('insertText', false, text);
      target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
      target.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Process' }));
      return { ok: inserted, reason: inserted ? 'ok' : 'exec_command_failed' };
    }, chunk);

    await frame.waitForTimeout(150);
    const verified = chunkSample ? await verifyChunkApplied(frame, chunk, beforeLen, chunk) : true;
    if (!result.ok || !verified) {
      const afterSignature = await getEditorDomSignature(frame);
      let reason: TextInputFailureReason;
      if (!result.ok) {
        reason = TextInputFailureReason.INPUT_NOT_REFLECTED;
      } else if (!(await verifyFocusInBody(frame))) {
        reason = TextInputFailureReason.VERIFICATION_FAILED_FOCUS_LOST;
      } else if (beforeSignature !== afterSignature) {
        reason = TextInputFailureReason.VERIFICATION_FAILED_FRAME_CHANGED;
      } else {
        reason = TextInputFailureReason.VERIFICATION_FAILED_TEXT_MISMATCH;
      }
      attempts.push({
        strategy: 'strategy2_js_input',
        chunkIndex: ci,
        chunkLength: chunk.length,
        success: false,
        reason,
        elapsedMs: Date.now() - started,
      });
      return { ok: false, reason };
    }

    if (ci < chunks.length - 1) {
      await page.keyboard.press('Enter').catch(() => undefined);
    }

    attempts.push({
      strategy: 'strategy2_js_input',
      chunkIndex: ci,
      chunkLength: chunk.length,
      success: true,
      elapsedMs: Date.now() - started,
    });
  }
  return { ok: true };
}

async function runPasteStrategy(
  ctx: EditorContext,
  frame: Frame,
  page: Page,
  chunks: string[],
  attempts: TextInputAttempt[],
): Promise<{ ok: boolean; reason?: TextInputFailureReason }> {
  for (let ci = 0; ci < chunks.length; ci++) {
    const started = Date.now();
    const chunk = chunks[ci];
    const chunkSample = extractVerificationSample(chunk);
    const beforeLen = await getBodyTextLength(frame);

    if (!(await focusBodyEnd(ctx)) || !(await verifyFocusInBody(frame))) {
      attempts.push({
        strategy: 'strategy3_paste',
        chunkIndex: ci,
        chunkLength: chunk.length,
        success: false,
        reason: TextInputFailureReason.FOCUS_FAILED,
        elapsedMs: Date.now() - started,
      });
      return { ok: false, reason: TextInputFailureReason.FOCUS_FAILED };
    }

    const pasted = await frame.evaluate((text) => {
      const active = document.activeElement as HTMLElement | null;
      if (!active || active.contentEditable !== 'true') return false;
      const dt = new DataTransfer();
      dt.setData('text/plain', text);
      const evt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
      const dispatched = active.dispatchEvent(evt);
      if (!dispatched) return false;
      if (document.queryCommandSupported?.('insertText')) {
        document.execCommand('insertText', false, text);
      }
      return true;
    }, chunk).catch(() => false);

    if (!pasted) {
      await page.evaluate((text) => navigator.clipboard.writeText(text), chunk).catch(() => undefined);
      await page.keyboard.press('Control+v').catch(() => undefined);
    }
    await frame.waitForTimeout(150);
    const verified = chunkSample ? await verifyChunkApplied(frame, chunk, beforeLen, chunk) : true;
    if (!verified) {
      let reason = TextInputFailureReason.VERIFICATION_FAILED_TEXT_NOT_FOUND;
      if (!(await verifyFocusInBody(frame))) {
        reason = TextInputFailureReason.VERIFICATION_FAILED_FOCUS_LOST;
      }
      attempts.push({
        strategy: 'strategy3_paste',
        chunkIndex: ci,
        chunkLength: chunk.length,
        success: false,
        reason,
        elapsedMs: Date.now() - started,
      });
      return { ok: false, reason };
    }

    if (ci < chunks.length - 1) {
      await page.keyboard.press('Enter').catch(() => undefined);
    }
    attempts.push({
      strategy: 'strategy3_paste',
      chunkIndex: ci,
      chunkLength: chunk.length,
      success: true,
      elapsedMs: Date.now() - started,
    });
  }

  return { ok: true };
}

// ────────────────────────────────────────────
// [핵심] 텍스트 블록 입력 - 근본 재작성
// ────────────────────────────────────────────
const BLOCK2_INPUT_TIMEOUT_MS = 22_000;

export async function insertTextBlock(
  ctx: EditorContext,
  content: string,
  artifactsDir: string,
  blockIndex?: number,
  options: { appendNewline?: boolean } = {},
): Promise<TextBlockInputResult> {
  const attemptTextBlockInput = async (): Promise<TextBlockInputResult> => {
    const trimmed = content.trim();
    const sanitized = sanitizeForEditor(trimmed);
    const attempts: TextInputAttempt[] = [];
    if (!sanitized) {
      if (trimmed && hasSuspiciousControlChars(trimmed)) {
        return { success: false, failureReason: TextInputFailureReason.CONTENT_ENCODING_ERROR, attempts };
      }
      return { success: true, attempts };
    }

    const { page, frame } = ctx;
    const appendNewline = options.appendNewline ?? true;
    const blockNumber = (blockIndex ?? 0) + 1;
    const isBlockTwo = blockNumber === 2;
    const blockLabel = blockIndex !== undefined ? `[block#${blockNumber}]` : '';
    const textHash = sampleHash(sanitized, 24);
    const startTime = Date.now();
    const chunks = splitIntoChunks(sanitized, isBlockTwo ? 360 : 250);
    const beforeAllLen = await getBodyTextLength(frame);
    const expectedAnchors = buildVerificationAnchors(sanitized);

    log.info(`${blockLabel} 텍스트 블록 입력 시작 (${sanitized.length}자, chunks=${chunks.length}, hash="${textHash}...")`);

    if (trimmed !== sanitized) {
      log.warn(`${blockLabel} 입력 텍스트 정규화 적용 (원본 ${trimmed.length}자 -> ${sanitized.length}자)`);
    }

    await ensureEditorClear(frame, page);
    const bodyReady = await ensureBodyEditableReady(ctx);
    if (!bodyReady) {
      const debugDir = await captureEditorDebug(page, frame, `text_block_fail_${blockIndex ?? 'x'}`, {
        blockIndex,
        textLength: sanitized.length,
        textHash,
        failureReason: TextInputFailureReason.EDITOR_AREA_NOT_FOUND,
        stage: 'ensure_body_ready',
      });
      return {
        success: false,
        failureReason: TextInputFailureReason.EDITOR_AREA_NOT_FOUND,
        attempts,
        debugDir,
      };
    }

    if (await isEditorOverlayBlocking(frame)) {
      const debugDir = await captureEditorDebug(page, frame, `text_block_fail_${blockIndex ?? 'x'}`, {
        blockIndex,
        textLength: sanitized.length,
        textHash,
        failureReason: TextInputFailureReason.OVERLAY_BLOCKING,
        stage: 'pre_input',
      });
      return {
        success: false,
        failureReason: TextInputFailureReason.OVERLAY_BLOCKING,
        attempts,
        debugDir,
      };
    }

    const editableCount = await getBodyEditableCount(frame);
    if (editableCount === 0) {
      const debugDir = await captureEditorDebug(page, frame, `text_block_fail_${blockIndex ?? 'x'}`, {
        blockIndex,
        textLength: sanitized.length,
        textHash,
        failureReason: TextInputFailureReason.EDITOR_AREA_NOT_FOUND,
        stage: 'pre_input',
      });
      return {
        success: false,
        failureReason: TextInputFailureReason.EDITOR_AREA_NOT_FOUND,
        attempts,
        debugDir,
      };
    }

    const strategies: Array<() => Promise<{ ok: boolean; reason?: TextInputFailureReason }>> = [
      () => runSendKeysStrategy(ctx, frame, page, chunks, attempts),
      () => runJsInputStrategy(ctx, frame, page, chunks, attempts),
      () => runPasteStrategy(ctx, frame, page, chunks, attempts),
    ];

    let finalReason: TextInputFailureReason = TextInputFailureReason.UNKNOWN;
    for (const [idx, strategy] of strategies.entries()) {
      try {
        log.info(`${blockLabel} 텍스트 입력 전략 ${idx + 1} 시작`);
        const result = await strategy();
        if (result.ok) {
          const observedRaw = await getEditorPlainText(frame);
          const verified = evaluateVerificationAgainstObserved(sanitized, observedRaw);
          if (!verified.ok) {
            const diagnosed = await diagnoseVerificationFailure(frame, sanitized);
            finalReason = diagnosed.reason;
            log.warn(
              `${blockLabel} 전략 ${idx + 1} 완료 후 검증 실패 (anchors=${diagnosed.matchedAnchors}/3 reason=${diagnosed.reason})`,
            );
          } else {
            if (appendNewline) {
              await page.keyboard.press('Enter').catch(() => undefined);
            }
            log.success(`${blockLabel} 텍스트 블록 입력 완료 (전략${idx + 1}, ${Date.now() - startTime}ms)`);
            return { success: true, attempts };
          }
        } else if (result.reason) {
          finalReason = result.reason;
        }
      } catch (e) {
        finalReason = TextInputFailureReason.STALE_ELEMENT;
        log.warn(`${blockLabel} 전략 ${idx + 1} 예외: ${e}`);
      }
      await ensureEditorClear(frame, page);
      await focusBodyEnd(ctx).catch(() => undefined);
    }

    if (finalReason === TextInputFailureReason.UNKNOWN) {
      if (await isEditorOverlayBlocking(frame)) {
        finalReason = TextInputFailureReason.OVERLAY_BLOCKING;
      } else if (!(await verifyFocusInBody(frame))) {
        finalReason = TextInputFailureReason.VERIFICATION_FAILED_FOCUS_LOST;
      } else {
        finalReason = TextInputFailureReason.VERIFICATION_FAILED_TEXT_NOT_FOUND;
      }
    }

    const elapsed = Date.now() - startTime;
    const active = await getActiveElementSnapshot(frame);
    const observedRaw = await getEditorPlainText(frame);
    const diagnosed = await diagnoseVerificationFailure(frame, sanitized);
    const editorHtmlSnippet = await collectBlockContextHtml(frame);
    const debugPayload: BlockVerificationDebugPayload = {
      stageName: 'insert_text_block',
      blockIndex: blockNumber,
      attempt: Math.max(1, attempts.filter((a) => !a.success).length + 1),
      elapsedMs: elapsed,
      expectedProbe: {
        textHash,
        anchors: expectedAnchors,
      },
      observed: {
        activeElement: {
          tagName: active.tagName,
          isContentEditable: active.isContentEditable,
          className: active.className,
        },
        selectionCollapsed: active.selectionCollapsed,
        editorFrameUrl: frame.url(),
        editorHtmlSnippet,
        plainTextSnapshot: normalizeForVerification(observedRaw).slice(0, 2048),
        plainTextHash: sampleHash(normalizeForVerification(observedRaw), 120),
      },
      inputMethod: attempts.map((a) => a.strategy).join(' -> '),
      sanitizedLength: sanitized.length,
      originalLength: trimmed.length,
      reasonCode: finalReason,
    };
    const verificationDebugDir = await captureBlockVerificationDebug(ctx, debugPayload);
    log.error(`${blockLabel} 텍스트 블록 입력 실패 (${debugPayload.reasonCode}, ${elapsed}ms, debug=${verificationDebugDir})`);

    const debugDir = await captureEditorDebug(page, frame, `text_block_fail_${blockIndex ?? 'x'}`, {
      blockIndex,
      textLength: sanitized.length,
      textHash,
      failureReason: debugPayload.reasonCode,
      attempts,
      elapsed,
      verificationDebugDir,
      expectedAnchors,
      observedSample: diagnosed.observedTextSample,
    });
    return {
      success: false,
      failureReason: debugPayload.reasonCode,
      attempts,
      debugDir: verificationDebugDir || debugDir,
    };
  };

  const blockNumber = (blockIndex ?? 0) + 1;
  if (blockNumber !== 2) {
    return attemptTextBlockInput();
  }
  try {
    return await withTimeout(
      () => attemptTextBlockInput(),
      BLOCK2_INPUT_TIMEOUT_MS,
      'block2 text input timeout',
    );
  } catch (error) {
    const reason = TextInputFailureReason.VERIFICATION_FAILED_TEXT_NOT_FOUND;
    const debugDir = await captureBlockVerificationDebug(ctx, {
      stageName: 'insert_text_block_timeout',
      blockIndex: blockNumber,
      attempt: 2,
      elapsedMs: BLOCK2_INPUT_TIMEOUT_MS,
      expectedProbe: {
        textHash: sampleHash(content, 24),
        anchors: buildVerificationAnchors(content),
      },
      observed: {
        activeElement: {
          tagName: 'TIMEOUT',
          isContentEditable: false,
          className: '',
        },
        selectionCollapsed: true,
        editorFrameUrl: ctx.frame.url(),
        editorHtmlSnippet: [],
        plainTextSnapshot: String(error).slice(0, 2048),
        plainTextHash: sampleHash(String(error), 120),
      },
      inputMethod: 'timeout_guard',
      sanitizedLength: sanitizeForEditor(content).length,
      originalLength: content.length,
      reasonCode: reason,
    });
    return { success: false, failureReason: reason, attempts: [], debugDir };
  }
}

async function scanImageMarkerResidues(frame: Frame): Promise<{ count: number; samples: string[] }> {
  try {
    return await frame.evaluate(() => {
      const text = (document.body.innerText || '').replace(/\s+/g, ' ');
      const pattern = /\[사진\d+\]|\(사진\d+\)|\(사진\)/g;
      const matches = text.match(pattern) || [];
      return {
        count: matches.length,
        samples: Array.from(new Set(matches)).slice(0, 10),
      };
    });
  } catch {
    return { count: 0, samples: [] };
  }
}

type Quote2SectionResult = {
  success: boolean;
  reason?: string;
  debugPath?: string;
};

const QUOTE2_KEYBOARD_TIMEOUT_MS = 12_000;
export const QUOTE2_KEYBOARD_EXIT_SEQUENCE = ['ArrowDown', 'ArrowDown', 'Enter'] as const;
const QUOTE2_STRICT_VERIFY = (process.env.NAVER_QUOTE2_STRICT_VERIFY ?? 'false').toLowerCase() === 'true';

function randomBetween(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

async function withTimeout<T>(fn: () => Promise<T>, timeoutMs: number, label: string): Promise<T> {
  let handle: ReturnType<typeof setTimeout> | null = null;
  const timeoutPromise = new Promise<never>((_, reject) => {
    handle = setTimeout(() => reject(new Error(label)), timeoutMs);
  });
  try {
    return await Promise.race([fn(), timeoutPromise]) as T;
  } finally {
    if (handle) clearTimeout(handle);
  }
}

async function resolveToolbarFrame(ctx: EditorContext): Promise<Frame | null> {
  const candidates = Array.from(new Set([ctx.page.frame('mainFrame'), ...ctx.page.frames()].filter(Boolean) as Frame[]));
  let best: { frame: Frame; score: number } | null = null;
  for (const frame of candidates) {
    const score = await frame.evaluate(() => {
      const urlScore = /(blog|editor|write|postwriteform|redirect=write)/i.test(location.href) ? 2 : 0;
      const toolbar = document.querySelectorAll('.se-toolbar, [class*="toolbar"]').length > 0 ? 3 : 0;
      const editable = document.querySelectorAll('[contenteditable="true"], .se-text-paragraph').length > 0 ? 4 : 0;
      return urlScore + toolbar + editable;
    }).catch(() => -1);
    if (score < 0) continue;
    if (!best || score > best.score) {
      best = { frame, score };
    }
  }
  if (!best) return null;
  ctx.frame = best.frame;
  return best.frame;
}

async function captureQuote2KeyboardDebug(
  ctx: EditorContext,
  attempts: Array<Record<string, unknown>>,
  debugReason: string,
): Promise<string | undefined> {
  try {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const debugDir = path.join('/tmp/naver_editor_debug', `${ts}_section_title_quote2_keyboard_fail`);
    fs.mkdirSync(debugDir, { recursive: true });
    await ctx.page.screenshot({ path: path.join(debugDir, 'page.png'), fullPage: true }).catch(() => undefined);

    const frameList = ctx.page.frames().map((f) => ({ name: f.name(), url: f.url() }));
    const probe = await ctx.frame.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      const toolbar = document.querySelector<HTMLElement>('.se-toolbar, [class*="toolbar"]');
      const menu = document.querySelector<HTMLElement>('[role="menu"], [class*="dropdown"], [class*="layer"], [class*="menu"]');
      const sel = window.getSelection();
      return {
        activeElement: active ? { tag: active.tagName, className: active.className } : null,
        toolbarHTML: toolbar?.outerHTML?.slice(0, 6000) || null,
        menuHTML: menu?.outerHTML?.slice(0, 6000) || null,
        selection: sel ? { isCollapsed: sel.isCollapsed, rangeCount: sel.rangeCount } : null,
      };
    }).catch(() => null);

    fs.writeFileSync(path.join(debugDir, 'quote2_debug.json'), JSON.stringify({
      reason: debugReason,
      at: new Date().toISOString(),
      frameList,
      probe,
      attempts,
      pageUrl: ctx.page.url(),
      frameUrl: ctx.frame.url(),
    }, null, 2), 'utf-8');
    return debugDir;
  } catch {
    return undefined;
  }
}

async function clickByTextInFrame(frame: Frame, pattern: RegExp): Promise<boolean> {
  return await frame.evaluate(({ source, flags }) => {
    const regex = new RegExp(source, flags);
    const nodes = Array.from(document.querySelectorAll<HTMLElement>('button, [role="button"], a, li, [aria-label], [title], [data-name]'));
    for (const node of nodes) {
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 2 || rect.height < 2) continue;
      const text = `${node.textContent || ''} ${node.getAttribute('aria-label') || ''} ${node.getAttribute('title') || ''} ${node.getAttribute('data-name') || ''}`;
      if (!regex.test(text)) continue;
      node.click();
      return true;
    }
    return false;
  }, { source: pattern.source, flags: pattern.flags }).catch(() => false);
}

async function clickFirstVisibleSelector(frame: Frame, selectors: string[]): Promise<boolean> {
  for (const selector of selectors) {
    try {
      const loc = frame.locator(selector).first();
      if (await loc.count() === 0) continue;
      if (!(await loc.isVisible().catch(() => false))) continue;
      await loc.click({ timeout: 700 }).catch(() => undefined);
      return true;
    } catch {
      // try next selector
    }
  }
  return false;
}

async function isQuoteMenuVisible(frame: Frame): Promise<boolean> {
  return await frame.evaluate(() => {
    const candidates = Array.from(
      document.querySelectorAll<HTMLElement>(
        '[role="menu"], .se-document-toolbar-select-option-list, .se-document-toolbar-select-option-layer, [class*="select-option"], [class*="dropdown"], [class*="layer"]',
      ),
    );
    const hasVisibleMenu = candidates.some((el) => {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 2 && rect.height > 2;
    });
    if (hasVisibleMenu) return true;
    const expanded = Array.from(document.querySelectorAll<HTMLElement>('button[aria-haspopup="true"]')).some(
      (btn) => btn.getAttribute('aria-expanded') === 'true',
    );
    return expanded;
  }).catch(() => false);
}

async function clickQuote2Option(frame: Frame): Promise<boolean> {
  const selectorCandidates = [
    ...NAVER_SELECTORS.quote2Option,
    '[role="menu"] button:has-text("인용구2")',
    '[role="menu"] [role="menuitem"]:has-text("인용구2")',
    '[class*="layer"] button:has-text("인용구2")',
    '[class*="select"] button:has-text("인용구2")',
  ];
  if (await clickFirstVisibleSelector(frame, selectorCandidates)) {
    return true;
  }
  return await clickByTextInFrame(frame, /^인용구2$/i)
    || await clickByTextInFrame(frame, /(인용구\s*2|quote\s*2|quote2)/i);
}

async function waitDropdownClosed(frame: Frame, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() <= deadline) {
    const opened = await frame.evaluate(() => {
      const menus = Array.from(document.querySelectorAll<HTMLElement>('[role="menu"], [class*="dropdown"], [class*="layer"], [class*="menu"]'));
      return menus.some((el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      });
    }).catch(() => false);
    if (!opened) return true;
    await frame.waitForTimeout(120).catch(() => undefined);
  }
  return false;
}

async function verifyQuote2TitlePlacement(frame: Frame, titleText: string): Promise<boolean> {
  return await frame.evaluate(({ quoteSelector, title }) => {
    const qNodes = Array.from(document.querySelectorAll<HTMLElement>(quoteSelector));
    const normalized = title.replace(/\s+/g, ' ').trim();
    return qNodes.some((node) => {
      const cls = `${node.className || ''} ${node.getAttribute('data-type') || ''} ${node.getAttribute('data-style') || ''}`.toLowerCase();
      if (!/(quote|blockquote|quotation|type[-_ ]?2|quote[-_ ]?2)/.test(cls)) return false;
      const txt = (node.innerText || '').replace(/\s+/g, ' ').trim();
      return txt.includes(normalized);
    });
  }, { quoteSelector: NAVER_SELECTORS.quoteRoot, title: titleText }).catch(() => false);
}

async function verifyBodyOutsideQuote(frame: Frame, bodyText: string): Promise<boolean> {
  const sample = extractVerificationSample(bodyText);
  if (!sample) return true;
  return await frame.evaluate(({ quoteSelector, needle }) => {
    const qNodes = Array.from(document.querySelectorAll<HTMLElement>(quoteSelector));
    const inQuote = qNodes.some((node) => (node.innerText || '').replace(/\s+/g, ' ').includes(needle));
    if (inQuote) return false;
    const comps = Array.from(document.querySelectorAll<HTMLElement>('.se-component, [class*="se-component"]'))
      .filter((el) => !el.closest(quoteSelector));
    return comps.some((el) => (el.innerText || '').replace(/\s+/g, ' ').includes(needle));
  }, { quoteSelector: NAVER_SELECTORS.quoteRoot, needle: sample }).catch(() => false);
}

async function writeSectionTitleAsQuote2Keyboard(
  ctx: EditorContext,
  titleText: string,
): Promise<Quote2SectionResult> {
  const attempts: Array<Record<string, unknown>> = [];
  try {
    return await withTimeout(async () => {
      let frame = await resolveToolbarFrame(ctx);
      if (!frame) {
        const debugPath = await captureQuote2KeyboardDebug(ctx, attempts, 'editor_frame_not_found');
        return { success: false, reason: 'editor_frame_not_found', debugPath };
      }

      let menuApplied = false;
      for (let attempt = 1; attempt <= 2; attempt++) {
        frame = (await resolveToolbarFrame(ctx)) || frame;
        const openMenuBySelector = await clickFirstVisibleSelector(frame, [
          '.se-toolbar-item-insert-quotation .se-document-toolbar-select-option-button',
          'button.se-document-toolbar-select-option-button[data-name="quotation"]',
          'button[data-name="quotation"][aria-haspopup="true"]',
          'button[aria-label*="인용구 선택"]',
          ...NAVER_SELECTORS.quoteMenu,
        ]);
        const openMenuByText = openMenuBySelector
          ? false
          : (
              (await clickByTextInFrame(frame, /(인용구\s*선택|인용구|quote)/i))
              || (await clickByTextInFrame(frame, /(서식|스타일|format)/i))
            );
        const openMenu = openMenuBySelector || openMenuByText;
        const menuVisible = openMenu ? await isQuoteMenuVisible(frame) : false;
        const chooseQuote2 = menuVisible ? await clickQuote2Option(frame) : false;
        const closed = chooseQuote2 ? await waitDropdownClosed(frame, 2_000) : false;
        attempts.push({ attempt, openMenu, chooseQuote2, closed, frameUrl: frame.url() });
        if (openMenu && chooseQuote2) {
          menuApplied = true;
          break;
        }
      }

      if (!menuApplied) {
        const debugPath = await captureQuote2KeyboardDebug(ctx, attempts, 'quote2_menu_open_failed');
        return { success: false, reason: 'quote2_menu_open_failed', debugPath };
      }

      const focused = await focusBodyEnd({ page: ctx.page, frame });
      if (!focused) {
        const debugPath = await captureQuote2KeyboardDebug(ctx, attempts, 'editable_focus_failed');
        return { success: false, reason: 'editable_focus_failed', debugPath };
      }

      await ctx.page.keyboard.type(titleText, { delay: randomBetween(0, 10) }).catch(() => undefined);
      await frame.waitForTimeout(randomBetween(200, 500)).catch(() => undefined);

      for (const key of QUOTE2_KEYBOARD_EXIT_SEQUENCE) {
        await ctx.page.keyboard.press(key).catch(() => undefined);
        await frame.waitForTimeout(randomBetween(80, 150)).catch(() => undefined);
      }
      await frame.waitForTimeout(randomBetween(120, 200)).catch(() => undefined);

      const titleOk = await verifyQuote2TitlePlacement(frame, titleText);
      if (!titleOk) {
        const debugPath = await captureQuote2KeyboardDebug(ctx, attempts, 'quote2_title_verify_failed');
        return { success: false, reason: 'quote2_title_verify_failed', debugPath };
      }

      return { success: true };
    }, QUOTE2_KEYBOARD_TIMEOUT_MS, 'writeSectionTitleAsQuote2 timeout');
  } catch (error) {
    const debugPath = await captureQuote2KeyboardDebug(ctx, attempts, String(error));
    return { success: false, reason: 'quote2_keyboard_timeout', debugPath };
  }
}

async function writeBodyAfterQuote2(
  ctx: EditorContext,
  bodyText: string,
  artifactsDir: string,
  blockIndex: number,
): Promise<TextBlockInputResult> {
  const frame = await resolveToolbarFrame(ctx);
  if (!frame) {
    const debugDir = await captureEditorDebug(ctx.page, ctx.frame, `quote2_exit_fail_${blockIndex}`, {
      blockIndex,
      reason: 'editor_frame_not_found',
    });
    return {
      success: false,
      failureReason: TextInputFailureReason.EDITOR_AREA_NOT_FOUND,
      attempts: [],
      debugDir,
    };
  }

  const insideQuote = await frame.evaluate((selector) => {
    const active = document.activeElement as HTMLElement | null;
    if (!active) return false;
    return !!active.closest(selector);
  }, NAVER_SELECTORS.quoteRoot).catch(() => false);

  if (insideQuote) {
    await ctx.page.keyboard.press('Enter').catch(() => undefined);
    await frame.waitForTimeout(120).catch(() => undefined);
  }

  const result = await insertTextBlock(ctx, bodyText, artifactsDir, blockIndex);
  if (!result.success) return result;

  const normalBody = await verifyBodyOutsideQuote(frame, bodyText);
  if (!normalBody) {
    // Quote2 포커스 탈출이 불안정한 경우가 있어 1회 보정 후 재검증한다.
    await focusBodyEnd({ page: ctx.page, frame }).catch(() => undefined);
    await ctx.page.keyboard.press('ArrowDown').catch(() => undefined);
    await frame.waitForTimeout(80).catch(() => undefined);
    await ctx.page.keyboard.press('Enter').catch(() => undefined);
    await frame.waitForTimeout(120).catch(() => undefined);

    const recovered = await verifyBodyOutsideQuote(frame, bodyText);
    if (recovered) {
      log.warn(`[quote2] reason_code=QUOTE2_EXIT_RECOVERED blockIndex=${blockIndex + 1}`);
      return result;
    }

    const debugDir = await captureEditorDebug(ctx.page, frame, `quote2_exit_fail_${blockIndex}`, {
      blockIndex,
      reason: 'quote2_exit_failed',
      sample: extractVerificationSample(bodyText),
      strict_verify: QUOTE2_STRICT_VERIFY,
    });
    if (QUOTE2_STRICT_VERIFY) {
      return {
        success: false,
        failureReason: TextInputFailureReason.VERIFICATION_FAILED,
        attempts: result.attempts,
        debugDir,
      };
    }
    log.warn(
      `[quote2] reason_code=QUOTE2_EXIT_VERIFY_BYPASS blockIndex=${blockIndex + 1} debugPath=${debugDir ?? 'n/a'}`,
    );
    return result;
  }

  return result;
}

async function auditFinalQuoteBlocks(frame: Frame): Promise<{ emptyQuotes: number; quote1Count: number }> {
  try {
    return await frame.evaluate(() => {
      const quoteNodes = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.se-component-quotation, [class*="quote"], [class*="quotation"], [data-type*="quote"]',
        ),
      );
      let emptyQuotes = 0;
      let quote1Count = 0;
      for (const node of quoteNodes) {
        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
        if (!text) emptyQuotes += 1;
        const cls = `${node.className || ''} ${node.getAttribute('data-type') || ''}`.toLowerCase();
        if (/(quote[-_ ]?1|quotation[-_ ]?1|type[-_ ]?1)/.test(cls)) quote1Count += 1;
      }
      return { emptyQuotes, quote1Count };
    });
  } catch {
    return { emptyQuotes: 0, quote1Count: 0 };
  }
}

// ────────────────────────────────────────────
// [핵심] 블록 순차 삽입 - 개선
//
// 각 블록 처리 전후로 상태 체크
// 실패 시 어떤 블록에서 실패했는지 상세 로그
// iframe 재획득, 에디터 리커버리 후 1회 재시도
// ────────────────────────────────────────────
export async function insertBlocksSequentially(
  ctx: EditorContext,
  plan: PostPlan,
  imagePaths: string[],
  artifactsDir: string,
  options?: {
    state?: PostPlanState;
  },
): Promise<BlockInsertResult> {
  const uploadAttempts: ImageUploadAttemptTrace[] = [];
  const imageRefs: string[] = [];
  let uploadedCount = 0;
  let expectedImageCount = 0;
  let pendingQuote2Title: string | null = null;
  let duplicateSkipCount = 0;
  const state = options?.state ?? createPostPlanState();
  const planBlocks = plan.blocks;

  log.info(`블록 순차 삽입 시작: ${planBlocks.length}개 블록`);
  const insertStart = Date.now();

  // 실패한 블록 fixture 저장용
  const saveBlockFixture = (
    failedIdx: number,
    reason: string,
    attempts?: TextInputAttempt[],
    preferredDir?: string,
  ) => {
    try {
      const payload = buildDebugFixture(
        planBlocks.map((item): PostBlock => {
          if (item.type === 'image') {
            return { type: 'image', index: item.imageIndex ?? 1, marker: 'POST_PLAN' };
          }
          return { type: item.type, content: item.text ?? '' };
        }),
        imagePaths,
        failedIdx,
        reason,
        attempts,
      );
      if (preferredDir) {
        saveDebugFixture(preferredDir, payload);
      }
      const fixtureDir = path.join(artifactsDir, 'debug_fixtures');
      fs.mkdirSync(fixtureDir, { recursive: true });
      const fixturePath = path.join(fixtureDir, `debug_fixture_${Date.now()}.json`);
      fs.writeFileSync(fixturePath, JSON.stringify(payload, null, 2), 'utf-8');
      log.info(`블록 fixture 저장: ${fixturePath}`);
    } catch (e) {
      log.warn(`블록 fixture 저장 실패: ${e}`);
    }
  };

  for (let bi = 0; bi < planBlocks.length; bi++) {
    const planBlock = planBlocks[bi];
    const blockId = planBlock.blockId;
    if (state.insertedBlockIds.has(blockId)) {
      duplicateSkipCount += 1;
      const reasonCode = planBlock.type === 'image' ? 'DUP_IMG_BY_RETRY' : 'DUP_TEXT_BY_RETRY';
      log.warn(`[dedupe] reason_code=${reasonCode} block_id=${blockId} source_index=${planBlock.sourceIndex}`);
      if (planBlock.type === 'image') {
        expectedImageCount += 1;
        uploadedCount += 1;
      }
      continue;
    }

    const blockStart = Date.now();
    const preState = await getEditorRuntimeState(ctx.frame);
    log.info(
      `[block ${bi + 1}] pre-state active=${preState.activeTag}.${preState.activeClass || '-'} overlay=${preState.overlay} editables=${preState.editableCount}`,
    );

    if (planBlock.type === 'section_title') {
      const sectionTitle = planBlock.text ?? '';
      log.info(`[block-insert] blockId=${blockId} blockIndex=${bi} type=section_title inserted=false`);
      log.info(`[block ${bi + 1}/${planBlocks.length}] 섹션 제목 블록 (${sectionTitle.length}자)`);
      await focusBodyEnd(ctx).catch(() => undefined);
      const quoteResult = await writeSectionTitleAsQuote2Keyboard(ctx, sectionTitle);
      if (!quoteResult.success) {
        const elapsed = Date.now() - blockStart;
        log.error(`[block ${bi + 1}] 인용구2 소제목 생성 실패 (${quoteResult.reason ?? 'unknown'}, ${elapsed}ms)`);
        await captureEditorDebug(ctx.page, ctx.frame, `section_title_quote2_fail_${bi}`, {
          blockIndex: bi,
          sectionTitle,
          reason: quoteResult.reason,
          quoteDebugPath: quoteResult.debugPath || null,
        });
        return {
          success: false,
          expected_image_count: expectedImageCount,
          uploaded_image_count: uploadedCount,
          missing_image_count: Math.max(expectedImageCount - uploadedCount, 0),
          marker_residue_count: 0,
          marker_samples: [],
          upload_attempts: uploadAttempts,
          sample_image_refs: Array.from(new Set(imageRefs)).slice(0, 10),
          duplicate_skip_count: duplicateSkipCount,
          message: `인용구2 소제목 생성 실패 (block#${bi}, reason=${quoteResult.reason ?? 'unknown'})`,
        };
      }
      pendingQuote2Title = sectionTitle;
      state.insertedBlockIds.add(blockId);
      log.info(`[block-insert] blockId=${blockId} blockIndex=${bi} inserted=true`);
      log.success(`[block ${bi + 1}] 섹션 제목 인용구2 블록 입력 완료`);
      continue;
    }

    if (planBlock.type === 'text') {
      const textContent = planBlock.text ?? '';
      log.info(`[block-insert] blockId=${blockId} blockIndex=${bi} type=text inserted=false contentHash=${blockId.slice(-12)}`);
      log.info(`[block ${bi + 1}/${planBlocks.length}] 텍스트 블록 (${textContent.length}자)`);

      // 1차 시도
      let result = pendingQuote2Title
        ? await writeBodyAfterQuote2(ctx, textContent, artifactsDir, bi)
        : await insertTextBlock(ctx, textContent, artifactsDir, bi);

      if (!result.success) {
        // 리커버리 시도: iframe 재획득 + 에디터 준비 재확인
        log.warn(`[block ${bi + 1}] 텍스트 블록 입력 실패 (${result.failureReason}) → 에디터 리커버리 시도`);

        const editorFrame = ctx.page.frame('mainFrame');
        if (editorFrame) {
          ctx.frame = editorFrame;
          log.info('[recovery] 에디터 iframe 재획득 완료');
        }

        const editorReady = await waitForEditorReady(ctx.frame, artifactsDir, ctx.page);
        if (editorReady) {
          await ensureEditorClear(ctx.frame, ctx.page);
          log.info('[recovery] 에디터 리커버리 완료, 재시도');
          result = pendingQuote2Title
            ? await writeBodyAfterQuote2(ctx, textContent, artifactsDir, bi)
            : await insertTextBlock(ctx, textContent, artifactsDir, bi);
        }

        if (!result.success) {
          const elapsed = Date.now() - blockStart;
          log.error(`[block ${bi + 1}] 텍스트 블록 최종 실패 (${result.failureReason}, ${elapsed}ms) debug=${result.debugDir ?? 'n/a'}`);
          saveBlockFixture(
            bi,
            result.failureReason || 'UNKNOWN',
            result.attempts,
            result.debugDir,
          );

          return {
            success: false,
            expected_image_count: expectedImageCount,
            uploaded_image_count: uploadedCount,
            missing_image_count: Math.max(expectedImageCount - uploadedCount, 0),
            marker_residue_count: 0,
            marker_samples: [],
            upload_attempts: uploadAttempts,
            sample_image_refs: Array.from(new Set(imageRefs)).slice(0, 10),
            duplicate_skip_count: duplicateSkipCount,
            message: `텍스트 블록 입력 실패 (block#${bi}, reason=${result.failureReason}, ${textContent.length}자, debug=${result.debugDir ?? 'n/a'})`,
          };
        }
        log.success(`[block ${bi + 1}] 텍스트 블록 리커버리 재시도 성공`);
      }
      pendingQuote2Title = null;
      state.insertedBlockIds.add(blockId);
      log.info(`[block-insert] blockId=${blockId} blockIndex=${bi} inserted=true`);

      const elapsed = Date.now() - blockStart;
      log.info(`[block ${bi + 1}] 텍스트 블록 완료 (${elapsed}ms)`);
      const postState = await getEditorRuntimeState(ctx.frame);
      log.info(
        `[block ${bi + 1}] post-state active=${postState.activeTag}.${postState.activeClass || '-'} overlay=${postState.overlay} editables=${postState.editableCount}`,
      );
      continue;
    }

    // 이미지 블록
    expectedImageCount += 1;
    const imageIndex = planBlock.imageIndex ?? 0;
    const targetPath = planBlock.imagePath || imagePaths[imageIndex - 1];
    if (!targetPath) {
      log.error(`[block ${bi + 1}] 이미지 인덱스 누락 (index=${imageIndex})`);
      saveBlockFixture(bi, 'IMAGE_INDEX_MISSING');
      return {
        success: false,
        expected_image_count: expectedImageCount,
        uploaded_image_count: uploadedCount,
        missing_image_count: Math.max(expectedImageCount - uploadedCount, 0),
        marker_residue_count: 0,
        marker_samples: [],
        upload_attempts: uploadAttempts,
        sample_image_refs: Array.from(new Set(imageRefs)).slice(0, 10),
        duplicate_skip_count: duplicateSkipCount,
        message: `이미지 블록 인덱스 누락 (block#${bi}, index=${imageIndex})`,
        reason_code: 'MISMATCH_BY_SORTING',
      };
    }

    const imageId = getImageId(targetPath, imageIndex);
    if (state.insertedImageIds.has(imageId)) {
      duplicateSkipCount += 1;
      state.insertedBlockIds.add(blockId);
      uploadedCount += 1;
      log.warn(`[dedupe] reason_code=DUP_IMG_BY_RETRY image_id=${imageId} image_index=${imageIndex}`);
      continue;
    }

    log.info(`[block ${bi + 1}/${planBlocks.length}] 이미지 블록 (index=${imageIndex}, ${path.basename(targetPath)})`);
    log.info(`[image-insert] imageId=${imageId} imageIndex=${imageIndex} inserted=false`);

    const result = await uploadImages(ctx, [targetPath], artifactsDir, {
      imageIndex,
      totalImages: imagePaths.length,
    });
    uploadAttempts.push(...result.attempts);
    imageRefs.push(...result.sample_image_refs);

    if (!result.success || result.uploaded_count < 1) {
      const elapsed = Date.now() - blockStart;
      log.error(`[block ${bi + 1}] 이미지 업로드 실패 (${elapsed}ms)`);
      saveBlockFixture(bi, 'IMAGE_UPLOAD_FAILED');
      return {
        success: false,
        expected_image_count: expectedImageCount,
        uploaded_image_count: uploadedCount,
        missing_image_count: Math.max(expectedImageCount - uploadedCount, 0),
        marker_residue_count: 0,
        marker_samples: [],
        upload_attempts: uploadAttempts,
        sample_image_refs: Array.from(new Set(imageRefs)).slice(0, 10),
        duplicate_skip_count: duplicateSkipCount,
        message: `이미지 블록 삽입 실패 (block#${bi}, index=${imageIndex})`,
        reason_code: result.reason_code,
        debug_path: result.debug_path,
      };
    }

    uploadedCount += 1;
    state.insertedImageIds.add(imageId);
    state.insertedBlockIds.add(blockId);
    log.info(`[image-insert] imageId=${imageId} imageIndex=${imageIndex} inserted=true`);
    await focusBodyEnd(ctx);
    await ctx.page.keyboard.press('Enter').catch(() => undefined);

    const elapsed = Date.now() - blockStart;
    log.info(`[block ${bi + 1}] 이미지 블록 완료 (${elapsed}ms)`);
    const postState = await getEditorRuntimeState(ctx.frame);
    log.info(
      `[block ${bi + 1}] post-state active=${postState.activeTag}.${postState.activeClass || '-'} overlay=${postState.overlay} editables=${postState.editableCount}`,
    );
  }

  const markerResidues = await scanImageMarkerResidues(ctx.frame);
  const quoteAudit = await auditFinalQuoteBlocks(ctx.frame);
  const totalElapsed = Date.now() - insertStart;

  log.info(`블록 순차 삽입 완료: ${planBlocks.length}개 블록, ${totalElapsed}ms`);
  log.info(
    `  이미지: ${uploadedCount}/${expectedImageCount}, 중복스킵: ${duplicateSkipCount}, 마커 잔존: ${markerResidues.count}, 빈인용구: ${quoteAudit.emptyQuotes}, 인용구1: ${quoteAudit.quote1Count}`,
  );

  return {
    success: uploadedCount === expectedImageCount
      && markerResidues.count === 0
      && quoteAudit.emptyQuotes === 0
      && quoteAudit.quote1Count === 0,
    expected_image_count: expectedImageCount,
    uploaded_image_count: uploadedCount,
    missing_image_count: Math.max(expectedImageCount - uploadedCount, 0),
    marker_residue_count: markerResidues.count,
    marker_samples: markerResidues.samples,
    upload_attempts: uploadAttempts,
    sample_image_refs: Array.from(new Set(imageRefs)).slice(0, 10),
    duplicate_skip_count: duplicateSkipCount,
    message:
      markerResidues.count > 0
        ? `마커 텍스트 잔존 감지 (${markerResidues.count})`
        : quoteAudit.emptyQuotes > 0
          ? `빈 인용구 감지 (${quoteAudit.emptyQuotes})`
          : quoteAudit.quote1Count > 0
            ? `인용구1 감지 (${quoteAudit.quote1Count})`
            : `블록 삽입 완료 (${uploadedCount}/${expectedImageCount}, dedupe=${duplicateSkipCount})`,
  };
}

// ────────────────────────────────────────────
// 이미지 업로드
// ────────────────────────────────────────────
export async function uploadImages(
  ctx: EditorContext,
  imagePaths: string[],
  artifactsDir: string,
  options?: {
    imageIndex?: number;
    totalImages?: number;
  },
): Promise<ImageUploadResult> {
  const traces: ImageUploadItemTrace[] = imagePaths.map((imagePath) => {
    const resolved = path.resolve(imagePath);
    const extension = path.extname(resolved).toLowerCase();
    const exists = fs.existsSync(resolved);
    const size_bytes = exists ? fs.statSync(resolved).size : 0;
    return {
      image_path: resolved,
      file_name: path.basename(resolved),
      extension,
      mime_type: extToMime(extension),
      exists,
      size_bytes,
    };
  });

  if (imagePaths.length === 0) {
    const reasonCode: ImageUploadReasonCode = 'IMAGE_LIST_EMPTY';
    const message = '업로드 대상 이미지가 비어 있습니다';
    const debugPath = await saveImageFailureDebug(ctx, {
      reason_code: reasonCode,
      index: options?.imageIndex ?? 1,
      total: options?.totalImages ?? 0,
      image_paths: imagePaths,
      traces,
    }, options?.imageIndex ?? 1);
    return {
      success: false,
      partial: false,
      expected_count: imagePaths.length,
      uploaded_count: 0,
      missing_count: imagePaths.length,
      editor_image_count: 0,
      message,
      traces,
      attempts: [],
      sample_image_refs: [],
      reason_code: reasonCode,
      debug_path: debugPath,
    };
  }

  const missingLocalFiles = traces.filter((item) => !item.exists);
  if (missingLocalFiles.length > 0) {
    const reasonCode: ImageUploadReasonCode = 'IMAGE_FILE_NOT_FOUND';
    const message = `로컬 이미지 파일 누락: ${missingLocalFiles.length}개`;
    log.error(message);
    const debugPath = await saveImageFailureDebug(ctx, {
      reason_code: reasonCode,
      index: options?.imageIndex ?? 1,
      total: options?.totalImages ?? imagePaths.length,
      missing_files: missingLocalFiles.map((item) => item.image_path),
      traces,
    }, options?.imageIndex ?? 1);
    return {
      success: false,
      partial: false,
      expected_count: imagePaths.length,
      uploaded_count: 0,
      missing_count: imagePaths.length,
      editor_image_count: 0,
      message,
      traces,
      attempts: [],
      sample_image_refs: [],
      reason_code: reasonCode,
      debug_path: debugPath,
    };
  }

  const simulationMode = (process.env.SIMULATE_IMAGE_UPLOAD_FAILURE || '').toLowerCase();
  if (simulationMode === 'timeout' || simulationMode === 'fail') {
    const attempts: ImageUploadAttemptTrace[] = [];
    for (let attempt = 1; attempt <= 3; attempt++) {
      const delay = computeBackoffMs(attempt);
      attempts.push({
        attempt,
        started_at: new Date().toISOString(),
        duration_ms: delay,
        success: false,
        message: `SIMULATED_${simulationMode.toUpperCase()}`,
        network_traces: [],
        editor_image_count: 0,
        transient_failure: simulationMode === 'timeout',
        reason_code: simulationMode === 'timeout' ? 'IMAGE_UPLOAD_STUCK' : 'IMAGE_UPLOAD_NO_INSERT',
      });
    }
    const message = simulationMode === 'timeout'
      ? 'SIMULATED_TIMEOUT: 이미지 업로드 실패'
      : 'SIMULATED_FAILURE: 이미지 업로드 실패';
    log.warn(message);
    return {
      success: false,
      partial: false,
      expected_count: imagePaths.length,
      uploaded_count: 0,
      missing_count: imagePaths.length,
      editor_image_count: 0,
      message,
      traces,
      attempts,
      sample_image_refs: [],
      reason_code: simulationMode === 'timeout' ? 'IMAGE_UPLOAD_STUCK' : 'IMAGE_UPLOAD_NO_INSERT',
    };
  }

  // 다중 이미지는 단건 순차 업로드로 처리
  if (imagePaths.length > 1) {
    log.info(`다중 이미지 단건 순차 업로드 모드: ${imagePaths.length}장`);
    let uploadedCount = 0;
    let editorCount = 0;
    const attempts: ImageUploadAttemptTrace[] = [];
    const refs: string[] = [];
    let lastReasonCode: ImageUploadReasonCode | undefined;
    let lastDebugPath: string | undefined;

    for (const [idx, singlePath] of imagePaths.entries()) {
      const singleResult = await uploadImages(ctx, [singlePath], artifactsDir, {
        imageIndex: idx + 1,
        totalImages: imagePaths.length,
      });
      uploadedCount += singleResult.uploaded_count > 0 ? 1 : 0;
      editorCount = Math.max(editorCount, singleResult.editor_image_count);
      refs.push(...singleResult.sample_image_refs);
      if (!singleResult.success) {
        lastReasonCode = singleResult.reason_code;
        lastDebugPath = singleResult.debug_path;
      }
      for (const at of singleResult.attempts) {
        attempts.push({
          ...at,
          message: `[single:${path.basename(singlePath)}] ${at.message}`,
        });
      }
    }

    const missingCount = Math.max(imagePaths.length - uploadedCount, 0);
    const success = uploadedCount >= imagePaths.length;
    const partial = uploadedCount > 0 && uploadedCount < imagePaths.length;
    return {
      success,
      partial,
      expected_count: imagePaths.length,
      uploaded_count: uploadedCount,
      missing_count: missingCount,
      editor_image_count: Math.max(editorCount, uploadedCount),
      message: uploadedCount >= imagePaths.length
        ? `단건 순차 업로드 성공 (${uploadedCount}/${imagePaths.length})`
        : uploadedCount > 0
          ? `단건 순차 업로드 일부 성공 (${uploadedCount}/${imagePaths.length})`
          : `단건 순차 업로드 실패 (0/${imagePaths.length})`,
      traces,
      attempts,
      sample_image_refs: Array.from(new Set(refs)).slice(0, 10),
      reason_code: success ? undefined : (lastReasonCode ?? 'IMAGE_UPLOAD_NO_INSERT'),
      debug_path: success ? undefined : lastDebugPath,
    };
  }

  log.info(`이미지 업로드 시작: ${imagePaths.length}장 (index=${options?.imageIndex ?? 1}/${options?.totalImages ?? imagePaths.length})`);
  const { page, frame } = ctx;
  const maxAttempts = Math.max(2, parseInt(process.env.NAVER_IMAGE_UPLOAD_MAX_ATTEMPTS ?? '3', 10));
  const attempts: ImageUploadAttemptTrace[] = [];
  let lastEditorCount = 0;
  let lastRefs: string[] = [];
  let uploadedDelta = 0;
  let lastReasonCode: ImageUploadReasonCode | undefined;
  let lastDebugPath: string | undefined;
  const totalImages = options?.totalImages ?? imagePaths.length;
  const imageIndex = options?.imageIndex ?? 1;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const startedAt = Date.now();
    const currentImageName = path.basename(imagePaths[0] ?? `image_attempt_${attempt}`);
    log.info(`[timing] step=image_upload_start image=${currentImageName} elapsed=0.0s`);
    const beforeState = await getEditorImageState(frame);
    log.info(`[image] 업로드 전 이미지 개수=${beforeState.count} target=${currentImageName}`);
    const networkTraces: UploadNetworkTrace[] = [];
    const responseStartedAt = new Map<string, number>();
    const onRequest = (req: import('playwright').Request) => {
      const url = req.url();
      if (/upload|attach|photo|image|resource/i.test(url)) {
        responseStartedAt.set(req.url(), Date.now());
      }
    };
    const onResponse = (res: import('playwright').Response) => {
      const url = res.url();
      if (!/upload|attach|photo|image|resource/i.test(url)) return;
      const started = responseStartedAt.get(url) ?? Date.now();
      networkTraces.push({
        url,
        status: res.status(),
        ok: res.ok(),
        elapsed_ms: Date.now() - started,
      });
    };

    page.on('request', onRequest);
    page.on('response', onResponse);

    let transientFailure = false;
    let attemptMessage = '';
    let uploaded = false;
    let usedAttachSelector = '';
    let usedInputSelector = '';
    const signals: ImageUploadSignalsObserved = {
      toast: false,
      response2xx: false,
      domInserted: false,
      spinnerGone: false,
    };

    try {
      // 사진 버튼 찾기 (iframe 내부)
      const photoButtonStrategies = [
        async () => {
          const buttons = await frame.$$('button');
          for (const btn of buttons) {
            const text = await btn.textContent();
            if (text && text.trim() === '사진') {
              usedAttachSelector = 'button[text="사진"]';
              await btn.click();
              return true;
            }
          }
          return false;
        },
        async () => {
          const sel = '[data-name="image"], [data-name="photo"], [data-log="image"]';
          const el = await frame.$(sel);
          if (el) {
            usedAttachSelector = sel;
            await el.click();
            return true;
          }
          return false;
        },
        async () => {
          const firstBtn = await frame.$('.se-toolbar-item:first-child button');
          if (firstBtn) {
            const text = await firstBtn.textContent();
            if (text && text.includes('사진')) {
              usedAttachSelector = '.se-toolbar-item:first-child button';
              await firstBtn.click();
              return true;
            }
          }
          return false;
        },
      ];

      let photoClicked = false;
      for (const [i, strategy] of photoButtonStrategies.entries()) {
        try {
          if (await strategy()) {
            photoClicked = true;
            log.success(`사진 버튼 클릭 완료 (전략 ${i + 1})`);
            break;
          }
        } catch {
          // 다음 전략
        }
      }

      if (!photoClicked) {
        const reasonCode: ImageUploadReasonCode = 'IMAGE_UPLOAD_UI_FAILED';
        attemptMessage = '사진 버튼을 찾을 수 없음';
        log.error(attemptMessage);
        const debugPath = await saveImageFailureDebug(ctx, {
          reason_code: reasonCode,
          index: imageIndex,
          total: totalImages,
          imagePath: traces[0]?.image_path,
          exists: traces[0]?.exists ?? false,
          size: traces[0]?.size_bytes ?? 0,
          usedSelector: { attachButton: usedAttachSelector, fileInput: usedInputSelector },
          uploadSignalsObserved: signals,
          editorImageCountBefore: beforeState.count,
          editorImageCountAfter: beforeState.count,
          attempt,
          networkTraces,
        }, imageIndex);
        attempts.push({
          attempt,
          started_at: new Date(startedAt).toISOString(),
          duration_ms: Date.now() - startedAt,
          success: false,
          message: attemptMessage,
          network_traces: networkTraces,
          editor_image_count: 0,
          transient_failure: false,
          reason_code: reasonCode,
          debug_path: debugPath,
          upload_signals: signals,
        });
        lastReasonCode = reasonCode;
        lastDebugPath = debugPath;
        continue;
      }

      await frame.waitForTimeout(500);

      // 파일 업로드
      const uploadStrategies = [
        async () => {
          const pcLabels = ['내 PC', 'PC에서', '컴퓨터에서'];
          const allBtns = await frame.$$('button, a, span, div[role="button"]');
          for (const btn of allBtns) {
            const text = await btn.textContent();
            if (text && pcLabels.some((l) => text.includes(l)) && await btn.isVisible()) {
              usedInputSelector = 'filechooser(pc_button)';
              const [fileChooser] = await Promise.all([
                page.waitForEvent('filechooser', { timeout: 5000 }),
                btn.click(),
              ]);
              await fileChooser.setFiles(imagePaths[0]);
              log.success('fileChooser로 파일 선택 완료');
              return true;
            }
          }
          return false;
        },
        async () => {
          const fileInputs = await frame.$$('input[type="file"]');
          for (const input of fileInputs) {
            try {
              usedInputSelector = 'frame:input[type=file]';
              await input.setInputFiles(imagePaths[0]);
              log.success('input[type=file]로 파일 설정 완료');
              return true;
            } catch {
              // 다음 input
            }
          }
          return false;
        },
        async () => {
          const fileInputs = await page.$$('input[type="file"]');
          for (const input of fileInputs) {
            try {
              usedInputSelector = 'page:input[type=file]';
              await input.setInputFiles(imagePaths[0]);
              log.success('page-level input[type=file]로 파일 설정 완료');
              return true;
            } catch {
              // 다음
            }
          }
          return false;
        },
      ];

      for (const [i, strategy] of uploadStrategies.entries()) {
        try {
          if (await strategy()) {
            uploaded = true;
            break;
          }
        } catch (e) {
          log.warn(`이미지 업로드 전략 ${i + 1} 실패: ${e}`);
        }
      }

      if (!uploaded) {
        const reasonCode: ImageUploadReasonCode = 'IMAGE_UPLOAD_UI_FAILED';
        attemptMessage = '업로드 input 처리 실패';
        log.error(attemptMessage);
        const debugPath = await saveImageFailureDebug(ctx, {
          reason_code: reasonCode,
          index: imageIndex,
          total: totalImages,
          imagePath: traces[0]?.image_path,
          exists: traces[0]?.exists ?? false,
          size: traces[0]?.size_bytes ?? 0,
          usedSelector: { attachButton: usedAttachSelector, fileInput: usedInputSelector },
          uploadSignalsObserved: signals,
          editorImageCountBefore: beforeState.count,
          editorImageCountAfter: beforeState.count,
          attempt,
          networkTraces,
        }, imageIndex);
        attempts.push({
          attempt,
          started_at: new Date(startedAt).toISOString(),
          duration_ms: Date.now() - startedAt,
          success: false,
          message: attemptMessage,
          network_traces: networkTraces,
          editor_image_count: beforeState.count,
          transient_failure: false,
          reason_code: reasonCode,
          debug_path: debugPath,
          upload_signals: signals,
        });
        lastReasonCode = reasonCode;
        lastDebugPath = debugPath;
        break;
      } else {
        log.info(`이미지 업로드 완료 대기 중 (timeout=${SINGLE_IMAGE_UPLOAD_TIMEOUT_MS}ms)...`);
        const responseSignal = page.waitForResponse((res) => (
          /upload|attach|photo|image|resource/i.test(res.url()) && res.status() >= 200 && res.status() < 300
        ), { timeout: SINGLE_IMAGE_UPLOAD_TIMEOUT_MS }).then(() => true).catch(() => false);
        const toastSignal = frame.waitForFunction(
          () => /업로드|첨부|완료|추가/.test((document.body?.innerText || '').replace(/\s+/g, ' ')),
          {},
          { timeout: 5_000 },
        ).then(() => true).catch(() => false);
        const spinnerGoneSignal = frame.waitForFunction(
          (selectors) => {
            const joined = (selectors as string[]).join(',');
            const nodes = Array.from(document.querySelectorAll<HTMLElement>(joined));
            if (nodes.length === 0) return true;
            return nodes.every((node) => {
              const style = window.getComputedStyle(node);
              return style.display === 'none' || style.visibility === 'hidden' || node.getBoundingClientRect().height < 2;
            });
          },
          NAVER_SELECTORS.spinner,
          { timeout: 5_000 },
        ).then(() => true).catch(() => false);
        const incrementResult = await waitForEditorImageIncrement(frame, beforeState.count, SINGLE_IMAGE_UPLOAD_TIMEOUT_MS);
        signals.response2xx = await responseSignal;
        signals.toast = await toastSignal;
        signals.spinnerGone = await spinnerGoneSignal;
        const editorState = incrementResult.state;
        lastEditorCount = editorState.count;
        lastRefs = editorState.refs;
        uploadedDelta = Math.max(editorState.count - beforeState.count, 0);
        signals.domInserted = incrementResult.increased && uploadedDelta >= 1;

        if (signals.domInserted && (signals.response2xx || signals.toast || signals.spinnerGone)) {
          attemptMessage = `이미지 업로드 성공 (delta=${uploadedDelta}, total=${editorState.count})`;
          attempts.push({
            attempt,
            started_at: new Date(startedAt).toISOString(),
            duration_ms: Date.now() - startedAt,
            success: true,
            message: attemptMessage,
            network_traces: networkTraces,
            editor_image_count: editorState.count,
            transient_failure: false,
            upload_signals: signals,
          });

          await frame.waitForTimeout(300);
          try {
            const doneBtn = await frame.$('.se-popup-close-button, .se-popup-button-confirm, .se-section-done-button');
            if (doneBtn && await doneBtn.isVisible()) {
              await doneBtn.click();
              await frame.waitForTimeout(500);
            }
          } catch {
            // 무시
          }

          return {
            success: true,
            partial: false,
            expected_count: imagePaths.length,
            uploaded_count: 1,
            missing_count: 0,
            editor_image_count: editorState.count,
            message: attemptMessage,
            traces,
            attempts,
            sample_image_refs: lastRefs,
          };
        }

        const reasonCode: ImageUploadReasonCode = (!signals.domInserted && !signals.response2xx && !signals.toast)
          ? 'IMAGE_UPLOAD_STUCK'
          : 'IMAGE_UPLOAD_NO_INSERT';
        attemptMessage = `이미지 삽입 검증 실패 (before=${beforeState.count}, after=${editorState.count}, reason=${reasonCode})`;
        log.warn(attemptMessage);
        const debugPath = await saveImageFailureDebug(ctx, {
          reason_code: reasonCode,
          index: imageIndex,
          total: totalImages,
          imagePath: traces[0]?.image_path,
          exists: traces[0]?.exists ?? false,
          size: traces[0]?.size_bytes ?? 0,
          usedSelector: { attachButton: usedAttachSelector, fileInput: usedInputSelector },
          uploadSignalsObserved: signals,
          editorImageCountBefore: beforeState.count,
          editorImageCountAfter: editorState.count,
          attempt,
          networkTraces,
        }, imageIndex);
        lastReasonCode = reasonCode;
        lastDebugPath = debugPath;
      }

      const statusCodes = networkTraces.map((t) => t.status);
      const hasTransientHttp = statusCodes.some((status) => status === 429 || status >= 500);
      transientFailure = hasTransientHttp || networkTraces.length === 0 || lastReasonCode === 'IMAGE_UPLOAD_STUCK';
      if (!attemptMessage) {
        attemptMessage = transientFailure ? '업로드 응답 미확인/일시 실패 가능' : '업로드 실패';
      }
    } catch (e: any) {
      const text = String(e?.message || e);
      attemptMessage = `업로드 예외: ${text}`;
      transientFailure = /timeout|timed out|ECONN|net::|temporar|429|5\d\d/i.test(text);
      lastReasonCode = transientFailure ? 'IMAGE_UPLOAD_STUCK' : 'IMAGE_UPLOAD_NO_INSERT';
      log.warn(attemptMessage);
    } finally {
      log.info(
        `[timing] step=image_upload_complete image=${currentImageName} elapsed=${((Date.now() - startedAt) / 1000).toFixed(1)}s`
      );
      page.off('request', onRequest);
      page.off('response', onResponse);
    }

    attempts.push({
      attempt,
      started_at: new Date(startedAt).toISOString(),
      duration_ms: Date.now() - startedAt,
      success: false,
      message: attemptMessage || '업로드 실패',
      network_traces: networkTraces,
      editor_image_count: lastEditorCount,
      transient_failure: transientFailure,
      reason_code: lastReasonCode,
      debug_path: lastDebugPath,
      upload_signals: signals,
    });

    await captureFailure(page, `image_upload_failed_attempt_${attempt}`, artifactsDir);

    if (!transientFailure || attempt >= maxAttempts) {
      break;
    }

    const sleepMs = computeBackoffMs(attempt);
    log.warn(`일시 실패로 판단, ${sleepMs}ms 후 재시도 (${attempt + 1}/${maxAttempts})`);
    await frame.waitForTimeout(sleepMs);
  }

  const uploadedCount = Math.min(uploadedDelta, imagePaths.length);
  const missingCount = Math.max(imagePaths.length - uploadedCount, 0);
  const partial = uploadedCount > 0 && uploadedCount < imagePaths.length;
  const success = uploadedCount >= imagePaths.length;

  const message = success
    ? `이미지 업로드 성공 (${uploadedCount}/${imagePaths.length})`
    : `이미지 업로드 실패 (0/${imagePaths.length})`;

  return {
    success,
    partial,
    expected_count: imagePaths.length,
    uploaded_count: uploadedCount,
    missing_count: missingCount,
    editor_image_count: lastEditorCount,
    message,
    traces,
    attempts,
    sample_image_refs: lastRefs,
    reason_code: success ? undefined : (lastReasonCode ?? 'IMAGE_UPLOAD_NO_INSERT'),
    debug_path: success ? undefined : lastDebugPath,
  };
}

async function probeOverlay(frame: Frame, page: Page): Promise<boolean> {
  const overlaySelectors = [
    '.se-popup-dim',
    '.se-popup-dim-transparent',
    '[class*="dimmed"]',
    '[class*="overlay"]',
    '[role="dialog"]',
    '.ReactModal__Overlay',
  ].join(', ');
  try {
    const inFrame = await frame.evaluate((sel) => {
      const els = Array.from(document.querySelectorAll<HTMLElement>(sel));
      return els.some((el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 10 && rect.height > 10;
      });
    }, overlaySelectors);
    if (inFrame) return true;
  } catch {
    // ignore
  }
  try {
    return await page.evaluate((sel) => {
      const els = Array.from(document.querySelectorAll<HTMLElement>(sel));
      return els.some((el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 10 && rect.height > 10;
      });
    }, overlaySelectors);
  } catch {
    return false;
  }
}

async function probeSessionExpired(page: Page): Promise<boolean> {
  const loginSelectors = [
    '#id',
    '#pw',
    '.btn_login',
    'form[action*="nidlogin.login"]',
    'iframe[src*="captcha"]',
    'iframe[title*="captcha"]',
  ];
  for (const sel of loginSelectors) {
    try {
      const loc = page.locator(sel).first();
      if (await loc.count()) {
        if (await loc.isVisible().catch(() => true)) return true;
      }
    } catch {
      // ignore and continue
    }
  }
  try {
    const url = page.url();
    if (/nid\.naver\.com|captcha|auth/i.test(url)) return true;
  } catch {
    // ignore
  }
  try {
    const bodyText = await page.evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' '));
    if (/권한이\s*없|로그인|인증|캡차|보안문자/i.test(bodyText)) return true;
  } catch {
    // ignore
  }
  return false;
}

export async function verifyImageReferencesInEditor(
  frame: Frame,
  expectedCount: number,
  options?: {
    page?: Page;
    requestId?: string;
    accountId?: string;
    expectedPaths?: string[];
    /** 업로드 전 에디터 이미지 기준값 — DUPLICATED 오탐 방지를 위해 차감 */
    baselineCount?: number;
  },
): Promise<{
  success: boolean;
  image_count: number;
  refs: string[];
  message: string;
  reason_code?: ImageUploadReasonCode;
  debug_path?: string;
}> {
  const baseline = options?.baselineCount ?? 0;

  if (expectedCount === 0) {
    const s = await getEditorImageState(frame);
    return { success: true, image_count: s.count, refs: s.refs, message: '이미지 미요청 포스트' };
  }

  // 폴링: 최대 5회 × 400ms = 2초, 각 회차에서 frame 재탐색 포함
  const MAX_POLL = 5;
  const POLL_INTERVAL_MS = 400;
  let lastState = { count: 0, refs: [] as string[] };

  for (let i = 0; i < MAX_POLL; i++) {
    if (i > 0) await frame.waitForTimeout(POLL_INTERVAL_MS).catch(() => new Promise((r) => setTimeout(r, POLL_INTERVAL_MS)));

    // 1차: 전달받은 frame으로 시도
    let state = await getEditorImageState(frame);

    // 2차: frame이 stale하거나 count=0이면 page.frames()에서 에디터 frame 재탐색
    if (state.count === 0 && options?.page) {
      const found = await findEditorFrameState(options.page);
      if (found.count > 0) state = found;
    }

    lastState = state;
    const adjusted = Math.max(0, state.count - baseline);

    if (adjusted === expectedCount) {
      return {
        success: true,
        image_count: adjusted,
        refs: state.refs,
        message: `이미지 참조 검증 성공 (${adjusted}/${expectedCount})${baseline > 0 ? ` [기준값 차감: ${baseline}]` : ''}`,
      };
    }

    // 기준값 차감 후에도 초과면 DUPLICATED (실제 중복 삽입)
    if (adjusted > expectedCount) break;

    // adjusted < expectedCount: 계속 폴링
  }

  const adjusted = Math.max(0, lastState.count - baseline);

  // DUPLICATED: 기준값 차감 후에도 초과
  if (adjusted > expectedCount) {
    let debugPath: string | undefined;
    if (options?.page) {
      debugPath = await saveImageFailureDebug({ page: options.page, frame }, {
        reason_code: 'IMAGE_UPLOAD_DUPLICATED',
        requestId: options.requestId ?? null,
        accountId: options.accountId ?? null,
        expectedCount,
        observedCount: adjusted,
        baselineCount: baseline,
        expectedPaths: options.expectedPaths ?? [],
        observedRefs: lastState.refs,
      }, expectedCount || 1);
    }
    return {
      success: false,
      image_count: adjusted,
      refs: lastState.refs,
      message: `이미지 중복 삽입 감지 (${adjusted}/${expectedCount})${baseline > 0 ? ` [기준값 차감: ${baseline}]` : ''}`,
      reason_code: 'IMAGE_UPLOAD_DUPLICATED',
      debug_path: debugPath,
    };
  }

  // adjusted < expectedCount: 일부 누락 또는 0
  // count=0이면 임시저장은 성공했으나 DOM 검증 불가 → IMAGE_VERIFY_POSTSAVE_FAILED (경고)
  // count>0이면 실제 부분 누락 → IMAGE_UPLOAD_STUCK
  const reasonCode: ImageUploadReasonCode = adjusted === 0
    ? 'IMAGE_VERIFY_POSTSAVE_FAILED'
    : 'IMAGE_UPLOAD_STUCK';

  let debugPath: string | undefined;
  if (options?.page) {
    debugPath = await saveImageFailureDebug({ page: options.page, frame }, {
      reason_code: reasonCode,
      requestId: options.requestId ?? null,
      accountId: options.accountId ?? null,
      expectedCount,
      observedCount: adjusted,
      baselineCount: baseline,
      expectedPaths: options.expectedPaths ?? [],
      observedRefs: lastState.refs,
    }, expectedCount || 1);
  }

  return {
    success: false,
    image_count: adjusted,
    refs: lastState.refs,
    message: adjusted === 0
      ? `이미지 참조 검증 불가 (0/${expectedCount}) — 임시저장은 성공, DOM 재확인 불가 (경고)`
      : `이미지 참조 일부 누락 (${adjusted}/${expectedCount})`,
    reason_code: reasonCode,
    debug_path: debugPath,
  };
}

// ────────────────────────────────────────────
// 임시저장
// ────────────────────────────────────────────
export async function clickTempSave(
  ctx: EditorContext,
  artifactsDir: string,
  options?: {
    waitForSignal?: boolean;
    signalTimeoutMs?: number;
    recoveryRetries?: number;
    expectedTitle?: string;
    expectedDraftId?: string;
  },
): Promise<TempSaveClickResult> {
  log.info('임시저장 시작...');
  const { page } = ctx;
  const waitForSignal = options?.waitForSignal ?? true;
  const signalTimeoutMs = options?.signalTimeoutMs ?? TEMP_SAVE_SIGNAL_TIMEOUT_MS;
  const recoveryRetries = Math.min(
    2,
    Math.max(0, options?.recoveryRetries ?? parseInt(process.env.NAVER_DRAFT_SAVE_RECOVERY_RETRIES ?? '2', 10)),
  );
  const expectedTitle = options?.expectedTitle?.trim() ?? '';

  const verifyDraftPersistedInEditor = async (meta: {
    detectedDraftId?: string;
    detectedDraftEditUrl?: string;
  }): Promise<{ ok: boolean; reason?: string; debugPath?: string }> => {
    const expectedId = options?.expectedDraftId || meta.detectedDraftId || '';
    const normalizedTitle = expectedTitle.replace(/\s+/g, ' ').trim();
    const debugDir = createDebugRunDir('navertimeoutdebug', 'draft_verify_fail');
    const collectFailure = async (reason: string, payload: Record<string, unknown>) => {
      try {
        fs.mkdirSync(debugDir, { recursive: true });
        await ctx.page.screenshot({ path: path.join(debugDir, 'draft_verify.png'), fullPage: true }).catch(() => undefined);
        fs.writeFileSync(
          path.join(debugDir, 'draft_verify.json'),
          JSON.stringify({
            reason,
            pageUrl: ctx.page.url(),
            expectedTitle: normalizedTitle || null,
            expectedDraftId: expectedId || null,
            usedKey: expectedId ? 'draftId' : 'title',
            ...payload,
            capturedAt: new Date().toISOString(),
          }, null, 2),
          'utf-8',
        );
      } catch {
        // ignore
      }
      return { ok: false, reason, debugPath: debugDir };
    };

    if (!normalizedTitle && !expectedId) {
      return collectFailure('verify_key_missing', { matchedCount: 0, listSnippet: [] });
    }

    const frame = ctx.frame;
    try {
      const countBtn = frame.locator('button[class*="save_count_btn"], [class*="save_count_btn"]').first();
      if (await countBtn.count() === 0) {
        return collectFailure('count_button_not_found', { matchedCount: 0, listSnippet: [] });
      }
      await countBtn.click({ force: true });
      await frame.waitForTimeout(700);

      const panel = await frame.evaluate(({ expectedIdParam, expectedTitleParam }) => {
        const textLines = (document.body.innerText || '')
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean);
        const panelIdx = textLines.findIndex((line) => line.includes('임시저장 글'));
        const panelLines = panelIdx >= 0 ? textLines.slice(panelIdx, Math.min(panelIdx + 60, textLines.length)) : [];
        const normalizedExpected = expectedTitleParam.replace(/\s+/g, ' ').trim();
        const anchors = Array.from(document.querySelectorAll('a[href]'))
          .map((a) => ({
            href: (a as HTMLAnchorElement).href,
            text: ((a.textContent || '').replace(/\s+/g, ' ').trim()),
          }))
          .filter((item) => /PostWriteForm|Redirect=Write|logNo=|draft|temporary|tmp/i.test(item.href) || /임시저장|편집/.test(item.text));

        const idMatches = expectedIdParam
          ? anchors.filter((item) => item.href.includes(expectedIdParam))
          : [];
        const titleMatches = normalizedExpected
          ? panelLines.filter((line) => line.replace(/\s+/g, ' ').includes(normalizedExpected.slice(0, Math.min(12, normalizedExpected.length))))
          : [];

        return {
          panelFound: panelIdx >= 0,
          panelLines: panelLines.slice(0, 20),
          anchorSample: anchors.slice(0, 20),
          matchedCount: expectedIdParam ? idMatches.length : titleMatches.length,
          matchedBy: expectedIdParam ? 'draftId' : 'title',
        };
      }, { expectedIdParam: expectedId, expectedTitleParam: normalizedTitle });

      if (panel.matchedCount > 0) {
        return { ok: true };
      }
      const reason = expectedId ? 'draft_id_not_found' : 'draft_title_not_found';
      return collectFailure(reason, {
        matchedCount: panel.matchedCount,
        listSnippet: panel.panelLines,
        anchorSample: panel.anchorSample,
      });
    } catch (error) {
      return collectFailure('verify_exception', { error: String(error) });
    }
  };

  const findFrameWithSaveButton = async (): Promise<Frame | null> => {
    const frameCandidates = [ctx.page.frame('mainFrame'), ...ctx.page.frames()].filter(Boolean) as Frame[];
    const unique = Array.from(new Set(frameCandidates));
    for (const frame of unique) {
      for (const sel of NAVER_SELECTORS.saveButtons) {
        try {
          const found = await frame.evaluate((selector) => {
            const node = document.querySelector<HTMLElement>(selector);
            if (!node) return false;
            const text = (node.textContent || '').replace(/\s+/g, '');
            return !text || text.includes('저장');
          }, sel);
          if (found) return frame;
        } catch {
          // 다음 프레임/셀렉터 검사
        }
      }
      try {
        const hasTextButton = await frame.evaluate(() => {
          const buttons = Array.from(document.querySelectorAll<HTMLElement>('button, [role="button"], a'));
          return buttons.some((btn) => {
            const text = (btn.textContent || '').replace(/\s+/g, '');
            if (!text) return false;
            return text.includes('임시저장') || text.includes('저장');
          });
        });
        if (hasTextButton) return frame;
      } catch {
        // ignore
      }
    }
    return null;
  };

  const reacquireEditorFrame = async (): Promise<boolean> => {
    const prev = ctx.frame;
    const direct = await findFrameWithSaveButton();
    const next = direct ?? (await getEditorFrame(ctx.page, artifactsDir));
    if (next) {
      ctx.frame = next;
    }
    return Boolean(next && prev !== next);
  };

  const prepareForTempSave = async (): Promise<void> => {
    await reacquireEditorFrame();
    const frame = ctx.frame;
    await dismissPopups(frame);
    await page.keyboard.press('Escape').catch(() => undefined);
    await frame.waitForTimeout(300);
    await page.keyboard.press('Escape').catch(() => undefined);

    try {
      await frame.evaluate(() => {
        document.querySelectorAll('.se-popup-dim, .se-popup-dim-transparent, [class*="dimmed"], [class*="overlay"]').forEach(el => {
          const target = el as HTMLElement;
          target.style.display = 'none';
          target.style.pointerEvents = 'none';
        });
      });
      await page.evaluate(() => {
        document.querySelectorAll('.se-popup-dim, .se-popup-dim-transparent, [class*="dimmed"], [class*="overlay"]').forEach(el => {
          const target = el as HTMLElement;
          target.style.display = 'none';
          target.style.pointerEvents = 'none';
        });
      });
    } catch {
      // 무시
    }

    const overlayNow = await probeOverlay(frame, page);
    if (overlayNow) {
      await dismissPopups(frame);
      await page.keyboard.press('Escape').catch(() => undefined);
    }
  };

  const clickSaveButton = async (): Promise<boolean> => {
    await reacquireEditorFrame();
    const frame = ctx.frame;
    for (const sel of NAVER_SELECTORS.saveButtons) {
      const elements = await frame.$$(sel);
      for (const el of elements) {
        const visible = await el.isVisible().catch(() => false);
        if (!visible) continue;
        const className = (await el.getAttribute('class')) || '';
        if (className.includes('save_count_btn')) continue;
        const text = (await el.textContent())?.replace(/\s+/g, '') ?? '';
        if (text && !text.includes('임시저장') && !text.includes('저장')) continue;
        await el.click({ force: true, timeout: 2_000 }).catch(() => undefined);
        return true;
      }
    }
    await page.keyboard.press('Control+s').catch(() => undefined);
    await frame.waitForTimeout(800).catch(() => undefined);
    return true;
  };

  const saver = new DraftSaver({
    ctx,
    clickSave: clickSaveButton,
    prepare: prepareForTempSave,
    detectOverlay: async () => probeOverlay(ctx.frame, page),
    closeOverlay: async () => {
      await dismissPopups(ctx.frame);
      await page.keyboard.press('Escape').catch(() => undefined);
    },
    reacquireFrame: reacquireEditorFrame,
    signalTimeBudgetMs: waitForSignal ? signalTimeoutMs : 1_000,
    maxRecoveryCount: recoveryRetries,
    debugPath: artifactsDir,
    stepName: 'clickTempSave',
    verifyPersisted: expectedTitle
      ? async (meta) => await verifyDraftPersistedInEditor({
        detectedDraftId: meta.detectedDraftId,
        detectedDraftEditUrl: meta.detectedDraftEditUrl,
      })
      : undefined,
  });

  const result = await saver.save();
  if (!result.success) {
    await captureFailure(page, 'tempsave_pipeline_failed', artifactsDir);
  } else {
    log.success(`임시저장 성공 (via=${result.via ?? 'unknown'}, retries=${result.retries ?? 0}, draftId=${result.draftId ?? 'n/a'})`);
  }
  return waitForSignal ? result : { success: true };
}

// ────────────────────────────────────────────
// 셀렉터 헬스체크
// ────────────────────────────────────────────
export async function selectorHealthcheck(frame: Frame): Promise<Record<string, boolean>> {
  log.info('=== 셀렉터 헬스체크 (iframe 내부) ===');

  const checks: Record<string, string[]> = {
    '제목 입력': ['[placeholder="제목"]', '.se-documentTitle', '.se-title-textarea'],
    '본문 영역': ['.se-text-paragraph', '.se-content', '[contenteditable="true"]'],
    '사진 버튼': ['[data-name="image"]'],
    '장소 버튼': ['[data-name="map"]'],
    '임시저장': ['.btn_save', 'button[class*="save_btn"]'],
    '툴바': ['.se-toolbar'],
  };

  const results: Record<string, boolean> = {};

  for (const [name, selectors] of Object.entries(checks)) {
    let found = false;
    for (const sel of selectors) {
      const el = await frame.$(sel);
      if (el) {
        found = true;
        log.success(`${name}: ${sel}`);
        break;
      }
    }

    if (!found) {
      const textMap: Record<string, string[]> = {
        '사진 버튼': ['사진'],
        '장소 버튼': ['장소', '지도'],
        '임시저장': ['임시저장'],
      };

      if (textMap[name]) {
        const buttons = await frame.$$('button');
        for (const btn of buttons) {
          const text = await btn.textContent();
          if (text && textMap[name].some((t) => text.includes(t))) {
            found = true;
            log.success(`${name}: button(text="${text.trim().slice(0, 20)}")`);
            break;
          }
        }
      }
    }

    if (!found) log.error(`${name}: 찾을 수 없음`);
    results[name] = found;
  }

  return results;
}
