import * as fs from 'fs';
import * as path from 'path';

export type TimeoutCaptureError = {
  step: string;
  type: string;
  message: string;
};

export type TimeoutDebugArtifactStatus = {
  screenshot_saved: boolean;
  page_content_saved: boolean;
  frame_content_saved: boolean;
};

export type TimeoutDebugReport = {
  reason: string;
  timestamp: string;
  run_id?: string;
  job_id?: string;
  last_activity: string;
  current_stage: string;
  last_activity_age_ms: number;
  watchdog_limit_seconds: number;
  silence_watchdog_seconds: number;
  page_url: string | null;
  page_title: string | null;
  active_element_page: { tagName: string } | null;
  active_element_frame: { tagName: string } | null;
  frame_url: string | null;
  overlay_matches: {
    page: string[];
    frame: string[];
  };
  artifact_status: TimeoutDebugArtifactStatus;
  editor_ready_probe: Record<string, unknown> | null;
  login_probe?: Record<string, unknown> | null;
  login_state?: Record<string, unknown> | null;
  iframe_probe?: Record<string, unknown> | null;
  capture_errors: TimeoutCaptureError[];
};

type DebugPageLike = {
  url(): string;
  title(): Promise<string>;
  screenshot(options: Record<string, unknown>): Promise<unknown>;
  content(): Promise<string>;
  evaluate<T>(fn: () => T): Promise<T>;
};

type DebugFrameLike = {
  url(): string;
  evaluate<T>(fn: () => T): Promise<T>;
};

export type CollectTimeoutDebugInput = {
  page: DebugPageLike | null;
  frame: DebugFrameLike | null;
  reason: string;
  currentStage: string;
  lastActivityLabel: string;
  lastActivityAgeMs: number;
  watchdogLimitSeconds: number;
  silenceWatchdogSeconds: number;
  editorReadyProbe: Record<string, unknown> | null;
  loginProbe?: Record<string, unknown> | null;
  loginState?: Record<string, unknown> | null;
  iframeProbe?: Record<string, unknown> | null;
  debugRootDir: string;
};

export type CollectTimeoutDebugResult = {
  debugDir: string;
  report: TimeoutDebugReport;
};

function toMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function pushCaptureError(
  report: TimeoutDebugReport,
  step: string,
  type: string,
  err: unknown,
): void {
  report.capture_errors.push({
    step,
    type,
    message: toMessage(err).slice(0, 300),
  });
}

function writeReportFile(debugDir: string, report: TimeoutDebugReport): void {
  fs.writeFileSync(
    path.join(debugDir, 'timeout_report.json'),
    JSON.stringify(report, null, 2),
    'utf-8',
  );
}

function sanitizeActiveElementTagName(value: unknown): { tagName: string } | null {
  if (!value || typeof value !== 'object') {
    return { tagName: 'NULL' };
  }
  const obj = value as Record<string, unknown>;
  const tagName = typeof obj.tagName === 'string' && obj.tagName.trim().length > 0
    ? obj.tagName.trim()
    : 'NULL';
  return { tagName };
}

export async function collectTimeoutDebugArtifacts(
  input: CollectTimeoutDebugInput,
): Promise<CollectTimeoutDebugResult> {
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const debugDir = path.resolve(input.debugRootDir, ts);
  fs.mkdirSync(debugDir, { recursive: true });

  const report: TimeoutDebugReport = {
    reason: input.reason,
    timestamp: new Date().toISOString(),
    run_id: process.env.NAVER_RUN_ID ?? 'none',
    job_id: process.env.NAVER_JOB_KEY,
    last_activity: input.lastActivityLabel,
    current_stage: input.currentStage,
    last_activity_age_ms: input.lastActivityAgeMs,
    watchdog_limit_seconds: input.watchdogLimitSeconds,
    silence_watchdog_seconds: input.silenceWatchdogSeconds,
    page_url: null,
    page_title: null,
    active_element_page: { tagName: 'NULL' },
    active_element_frame: { tagName: 'NULL' },
    frame_url: null,
    overlay_matches: {
      page: [],
      frame: [],
    },
    artifact_status: {
      screenshot_saved: false,
      page_content_saved: false,
      frame_content_saved: false,
    },
    editor_ready_probe: input.editorReadyProbe,
    login_probe: input.loginProbe ?? null,
    login_state: input.loginState ?? null,
    iframe_probe: input.iframeProbe ?? null,
    capture_errors: [],
  };

  writeReportFile(debugDir, report);

  if (input.page) {
    try {
      report.page_url = input.page.url();
    } catch (err) {
      pushCaptureError(report, 'page_url', 'page_url_read_failed', err);
    }
    try {
      report.page_title = await input.page.title();
    } catch (err) {
      pushCaptureError(report, 'page_title', 'page_title_read_failed', err);
    }
    try {
      await input.page.screenshot({
        path: path.join(debugDir, 'screenshot.png'),
        fullPage: true,
        timeout: 5000,
      });
      report.artifact_status.screenshot_saved = true;
    } catch (err) {
      pushCaptureError(report, 'screenshot', 'screenshot_save_failed', err);
    }
    try {
      const html = await input.page.content();
      fs.writeFileSync(path.join(debugDir, 'page.html'), html.slice(0, 300_000), 'utf-8');
      report.artifact_status.page_content_saved = true;
    } catch (err) {
      pushCaptureError(report, 'page_html', 'page_html_save_failed', err);
    }
    try {
      const active = await input.page.evaluate(() => {
        const ae = document.activeElement as HTMLElement | null;
        return { tagName: ae?.tagName ?? 'NULL' };
      });
      report.active_element_page = sanitizeActiveElementTagName(active);
    } catch (err) {
      pushCaptureError(report, 'active_element_page', 'active_element_page_read_failed', err);
      report.active_element_page = { tagName: 'NULL' };
    }
    try {
      report.overlay_matches.page = await input.page.evaluate(() => {
        const selectors = [
          '.se-popup-dim',
          '.se-popup-dim-transparent',
          '[class*="dimmed"]',
          '[class*="overlay"]',
          '[role="dialog"]',
          '.ReactModal__Overlay',
        ];
        const hits: string[] = [];
        for (const sel of selectors) {
          const el = document.querySelector<HTMLElement>(sel);
          if (!el) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width < 10 || rect.height < 10) continue;
          const style = window.getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') continue;
          hits.push(sel);
        }
        return hits;
      });
    } catch (err) {
      pushCaptureError(report, 'overlay_scan_page', 'overlay_scan_page_failed', err);
    }
  }

  if (input.frame) {
    try {
      report.frame_url = input.frame.url();
    } catch (err) {
      pushCaptureError(report, 'frame_url', 'frame_url_read_failed', err);
    }
    try {
      const frameHtml = await input.frame.evaluate(() => document.documentElement.outerHTML);
      fs.writeFileSync(path.join(debugDir, 'frame.html'), frameHtml.slice(0, 300_000), 'utf-8');
      report.artifact_status.frame_content_saved = true;
    } catch (err) {
      pushCaptureError(report, 'frame_html', 'frame_html_save_failed', err);
    }
    try {
      const active = await input.frame.evaluate(() => {
        const ae = document.activeElement as HTMLElement | null;
        return { tagName: ae?.tagName ?? 'NULL' };
      });
      report.active_element_frame = sanitizeActiveElementTagName(active);
    } catch (err) {
      pushCaptureError(report, 'active_element_frame', 'active_element_frame_read_failed', err);
      report.active_element_frame = { tagName: 'NULL' };
    }
    try {
      report.overlay_matches.frame = await input.frame.evaluate(() => {
        const selectors = [
          '.se-popup-dim',
          '.se-popup-dim-transparent',
          '[class*="dimmed"]',
          '[class*="overlay"]',
          '[role="dialog"]',
          '.ReactModal__Overlay',
        ];
        const hits: string[] = [];
        for (const sel of selectors) {
          const el = document.querySelector<HTMLElement>(sel);
          if (!el) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width < 10 || rect.height < 10) continue;
          const style = window.getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') continue;
          hits.push(sel);
        }
        return hits;
      });
    } catch (err) {
      pushCaptureError(report, 'overlay_scan_frame', 'overlay_scan_frame_failed', err);
    }
  }
  if (!input.frame) {
    report.capture_errors.push({
      step: 'frame_html_save_skipped',
      type: 'no_frame',
      message: 'frame가 없어 frame.html 저장을 건너뜀',
    });
  }

  if (
    !report.artifact_status.screenshot_saved
    && !report.artifact_status.page_content_saved
    && !report.artifact_status.frame_content_saved
  ) {
    try {
      const fallbackHtml = `<html><body><pre>timeout debug fallback: ${report.reason}</pre></body></html>`;
      fs.writeFileSync(path.join(debugDir, 'page.html'), fallbackHtml, 'utf-8');
      report.artifact_status.page_content_saved = true;
    } catch (err) {
      pushCaptureError(report, 'fallback_page_html', 'fallback_page_html_save_failed', err);
    }
  }

  writeReportFile(debugDir, report);
  return { debugDir, report };
}
