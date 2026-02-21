import * as fs from 'fs';
import * as path from 'path';
import type { Page, Frame, Request, Response, ConsoleMessage } from 'playwright';
import { writeLog } from '../common/logger';


type ActivityHook = (msg: string) => void;
let activityHook: ActivityHook | null = null;

export function setLogActivityHook(hook: ActivityHook | null): void {
  activityHook = hook;
}

function notifyActivity(msg: string): void {
  if (!activityHook) return;
  try {
    activityHook(msg);
  } catch {
    // activity hook failure must not break main flow
  }
}

export function info(msg: string): void {
  notifyActivity(msg);
  writeLog('INFO', 'naver', msg);
}

export function success(msg: string): void {
  notifyActivity(msg);
  writeLog('SUCCESS', 'naver', msg);
}

export function warn(msg: string): void {
  notifyActivity(msg);
  writeLog('WARN', 'naver', msg);
}

export function error(msg: string): void {
  notifyActivity(msg);
  writeLog('ERROR', 'naver', msg);
}

export function step(current: number, total: number, msg: string): void {
  notifyActivity(msg);
  writeLog('STEP', 'naver', `[${current}/${total}] ${msg}`);
}

export function fatal(msg: string): never {
  error(msg);
  process.exit(1);
}

/** artifacts 디렉토리에 스크린샷/HTML 덤프를 저장한다 */
export function artifactPath(artifactsDir: string, prefix: string, ext: string): string {
  fs.mkdirSync(artifactsDir, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
  return path.join(artifactsDir, `${prefix}_${ts}.${ext}`);
}

type ConsoleTrace = {
  timestamp: string;
  type: string;
  text: string;
  location?: { url?: string; lineNumber?: number; columnNumber?: number };
};

type NetworkTrace = {
  timestamp: string;
  event: 'response' | 'requestfailed';
  url: string;
  method?: string;
  status?: number;
  statusText?: string;
  failureText?: string;
};

type PageErrorTrace = {
  timestamp: string;
  message: string;
  stack?: string;
};

type PageDebugCollector = {
  consoleLogs: ConsoleTrace[];
  networkErrors: NetworkTrace[];
  pageErrors: PageErrorTrace[];
  attached: boolean;
  listeners: {
    console: (msg: ConsoleMessage) => void;
    pageerror: (err: Error) => void;
    response: (res: Response) => void;
    requestfailed: (req: Request) => void;
  };
};

const MAX_DEBUG_EVENTS = 300;
const pageCollectors = new WeakMap<Page, PageDebugCollector>();

function nowIso(): string {
  return new Date().toISOString();
}

function pushBounded<T>(arr: T[], item: T): void {
  arr.push(item);
  if (arr.length > MAX_DEBUG_EVENTS) {
    arr.splice(0, arr.length - MAX_DEBUG_EVENTS);
  }
}

function classifyNetworkError(res: Response): boolean {
  const status = res.status();
  return status >= 400;
}

export function attachPageDebugCollectors(page: Page): void {
  const existing = pageCollectors.get(page);
  if (existing?.attached) return;

  const collector: PageDebugCollector = existing ?? {
    consoleLogs: [],
    networkErrors: [],
    pageErrors: [],
    attached: false,
    listeners: {
      console: () => undefined,
      pageerror: () => undefined,
      response: () => undefined,
      requestfailed: () => undefined,
    },
  };

  collector.listeners.console = (msg: ConsoleMessage) => {
    pushBounded(collector.consoleLogs, {
      timestamp: nowIso(),
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
    });
  };
  collector.listeners.pageerror = (err: Error) => {
    pushBounded(collector.pageErrors, {
      timestamp: nowIso(),
      message: err.message,
      stack: err.stack,
    });
  };
  collector.listeners.response = (res: Response) => {
    if (!classifyNetworkError(res)) return;
    pushBounded(collector.networkErrors, {
      timestamp: nowIso(),
      event: 'response',
      url: res.url(),
      method: res.request().method(),
      status: res.status(),
      statusText: res.statusText(),
    });
  };
  collector.listeners.requestfailed = (req: Request) => {
    pushBounded(collector.networkErrors, {
      timestamp: nowIso(),
      event: 'requestfailed',
      url: req.url(),
      method: req.method(),
      failureText: req.failure()?.errorText,
    });
  };

  page.on('console', collector.listeners.console);
  page.on('pageerror', collector.listeners.pageerror);
  page.on('response', collector.listeners.response);
  page.on('requestfailed', collector.listeners.requestfailed);
  collector.attached = true;
  pageCollectors.set(page, collector);
}

function getCollectorSnapshot(page: Page): {
  console_logs: ConsoleTrace[];
  network_errors: NetworkTrace[];
  page_errors: PageErrorTrace[];
} {
  const collector = pageCollectors.get(page);
  if (!collector) {
    return {
      console_logs: [],
      network_errors: [],
      page_errors: [],
    };
  }
  return {
    console_logs: [...collector.consoleLogs],
    network_errors: [...collector.networkErrors],
    page_errors: [...collector.pageErrors],
  };
}

async function writeFrameOuterHtml(frame: Frame, outputPath: string): Promise<void> {
  const html = await frame.evaluate(() => document.documentElement.outerHTML);
  fs.writeFileSync(outputPath, html, 'utf-8');
}

export async function captureFailure(
  page: Page,
  stepName: string,
  artifactsDir: string
): Promise<void> {
  try {
    const screenshotPath = artifactPath(artifactsDir, `fail_${stepName}`, 'png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    error(`Screenshot saved: ${screenshotPath}`);
  } catch (e) {
    error(`Failed to capture screenshot: ${e}`);
  }

  try {
    const htmlPath = artifactPath(artifactsDir, `fail_${stepName}`, 'html');
    const html = await page.content();
    fs.writeFileSync(htmlPath, html, 'utf-8');
    error(`HTML dump saved: ${htmlPath}`);
  } catch (e) {
    error(`Failed to capture HTML: ${e}`);
  }
}

/**
 * 에디터 디버그 스냅샷: 텍스트 블록 입력 실패 시 상세 증거 수집
 * - 스크린샷, HTML 덤프, 콘솔 로그, activeElement, 에디터 DOM 상태
 */
export async function captureEditorDebug(
  page: Page,
  frame: Frame,
  stepName: string,
  context: Record<string, unknown> = {},
): Promise<string> {
  attachPageDebugCollectors(page);
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const dir = path.join('/tmp/naver_editor_debug', `${ts}_${stepName}`);
  fs.mkdirSync(dir, { recursive: true });

  // 1) 스크린샷
  try {
    await page.screenshot({ path: path.join(dir, 'screenshot.png'), fullPage: true });
  } catch (e) {
    error(`[debug] screenshot failed: ${e}`);
  }

  // 2) HTML 덤프
  try {
    const pageOuterHtml = await page.evaluate(() => document.documentElement.outerHTML);
    fs.writeFileSync(path.join(dir, 'page_outerHTML.html'), pageOuterHtml, 'utf-8');
  } catch (e) {
    error(`[debug] html dump failed: ${e}`);
  }

  // 3) iframe HTML 덤프
  try {
    await writeFrameOuterHtml(frame, path.join(dir, 'frame_outerHTML.html'));
  } catch (e) {
    error(`[debug] frame html dump failed: ${e}`);
  }

  // 4) 콘솔/네트워크/페이지 오류 로그
  try {
    const traces = getCollectorSnapshot(page);
    fs.writeFileSync(path.join(dir, 'console_logs.json'), JSON.stringify(traces.console_logs, null, 2), 'utf-8');
    fs.writeFileSync(path.join(dir, 'network_errors.json'), JSON.stringify(traces.network_errors, null, 2), 'utf-8');
    fs.writeFileSync(path.join(dir, 'page_errors.json'), JSON.stringify(traces.page_errors, null, 2), 'utf-8');
  } catch (e) {
    error(`[debug] traces dump failed: ${e}`);
  }

  // 5) activeElement, 에디터 DOM 존재 여부, 오버레이/팝업 상태
  try {
    const editorState = await frame.evaluate(() => {
      const ae = document.activeElement;
      const editables = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"]'));

      // 오버레이/팝업 감지
      const overlaySelectors = [
        '.se-popup-dim', '.se-popup-dim-transparent', '[class*="dimmed"]',
        '[class*="overlay"]', '.se-popup', '[role="dialog"]',
      ];
      const overlays = overlaySelectors.flatMap(sel =>
        Array.from(document.querySelectorAll<HTMLElement>(sel))
          .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0)
          .map(el => ({
            selector: sel,
            className: el.className,
            tagName: el.tagName,
            text: (el.textContent || '').slice(0, 100),
          }))
      );

      // 에디터 핵심 DOM 존재 여부
      const domChecks: Record<string, boolean> = {
        'se-toolbar': !!document.querySelector('.se-toolbar'),
        'se-content': !!document.querySelector('.se-content'),
        'se-documentTitle': !!document.querySelector('.se-documentTitle'),
        'se-components-content': !!document.querySelector('.se-components-content'),
        'se-main-container': !!document.querySelector('.se-main-container'),
        'se-text-paragraph': !!document.querySelector('.se-text-paragraph'),
        'contenteditable': editables.length > 0,
      };

      // 로딩 스피너 감지
      const spinnerSelectors = ['.se-loading', '[class*="spinner"]', '[class*="loading"]'];
      const loadingVisible = spinnerSelectors.some(sel => {
        const el = document.querySelector<HTMLElement>(sel);
        return el && el.offsetWidth > 0 && el.offsetHeight > 0;
      });

      return {
        activeElement: ae ? {
          tagName: ae.tagName,
          className: ae.className,
          id: ae.id,
          contentEditable: (ae as HTMLElement).contentEditable,
          inTitle: !!ae.closest?.('.se-documentTitle'),
          inBody: !!ae.closest?.('.se-components-content, .se-main-container, .se-content'),
        } : null,
        editableCount: editables.length,
        editableSummary: editables.slice(0, 20).map((el, idx) => ({
          idx,
          tagName: el.tagName,
          className: el.className,
          width: el.getBoundingClientRect().width,
          height: el.getBoundingClientRect().height,
          inTitle: !!el.closest('.se-documentTitle'),
          textLength: (el.textContent || '').length,
        })),
        domChecks,
        overlays,
        loadingVisible,
        url: location.href,
      };
    });
    const pageState = await page.evaluate(() => {
      const ae = document.activeElement as HTMLElement | null;
      return {
        activeElement: ae ? {
          tagName: ae.tagName,
          className: ae.className,
          id: ae.id,
          contentEditable: ae.contentEditable,
        } : null,
        url: location.href,
      };
    });

    fs.writeFileSync(
      path.join(dir, 'editor_state.json'),
      JSON.stringify({ ...editorState, pageState, context, timestamp: ts }, null, 2),
      'utf-8',
    );
  } catch (e) {
    error(`[debug] editor state capture failed: ${e}`);
  }

  info(`[debug] 에디터 디버그 스냅샷 저장: ${dir}`);
  return dir;
}

// ── 구조화 JSON 로그 헬퍼 ─────────────────────────────────────────

export type StructuredLogPayload = Record<string, unknown>;

export function getRunContext(): { run_id: string; job_id?: string } {
  return {
    run_id: process.env.NAVER_RUN_ID ?? 'none',
    ...(process.env.NAVER_JOB_KEY ? { job_id: process.env.NAVER_JOB_KEY } : {}),
  };
}

export function sanitizeLogPayload(data: StructuredLogPayload): StructuredLogPayload {
  const naverId = (process.env.NAVER_ID ?? '').trim();
  const naverPw = (process.env.NAVER_PW ?? '').trim();
  return JSON.parse(
    JSON.stringify(data, (key, val) => {
      if (typeof val === 'string') {
        if (naverId && val.includes(naverId)) return '[REDACTED_ID]';
        if (naverPw && val.includes(naverPw)) return '[REDACTED_PW]';
        if (/^(cookie_value|token_value|session_token)$/.test(key)) return '[REDACTED]';
      }
      return val;
    }),
  );
}

export function logStructured(event: string, data: StructuredLogPayload): void {
  const ctx = getRunContext();
  const payload = sanitizeLogPayload({ ...ctx, ...data });
  info(`${event}: ${JSON.stringify(payload)}`);
}

export function getRunArtifactDir(stage: string, now: Date = new Date()): string {
  const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const runId = process.env.NAVER_RUN_ID ?? 'norun';
  const dir = path.resolve('logs', dateStr, `run_${runId}`, stage);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
