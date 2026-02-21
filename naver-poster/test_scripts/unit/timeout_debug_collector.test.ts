import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { collectTimeoutDebugArtifacts } from '../../src/naver/timeout_debug';

describe('timeout debug collector', () => {
  test('page screenshot 실패를 capture_errors에 기록한다', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'timeout-debug-collector-'));

    const page = {
      url: () => 'https://example.com/write',
      title: async () => 'write page',
      screenshot: async () => {
        throw new Error('mock screenshot fail');
      },
      content: async () => '<html><body>page</body></html>',
      evaluate: async <T>(fn: () => T): Promise<T> => {
        const src = String(fn);
        if (src.includes('activeElement')) {
          return ({ tagName: 'BODY' } as unknown) as T;
        }
        return ([] as unknown) as T;
      },
    };

    const frame = {
      url: () => 'https://example.com/PostWriteForm.naver',
      evaluate: async <T>(fn: () => T): Promise<T> => {
        const src = String(fn);
        if (src.includes('document.documentElement.outerHTML')) {
          return ('<html><body>frame</body></html>' as unknown) as T;
        }
        if (src.includes('activeElement')) {
          return ({ tagName: 'DIV' } as unknown) as T;
        }
        return ([] as unknown) as T;
      },
    };

    const { debugDir } = await collectTimeoutDebugArtifacts({
      page,
      frame,
      reason: 'stage_timeout_write_page_enter_45s',
      currentStage: 'write_page_enter',
      lastActivityLabel: 'write_page_enter',
      lastActivityAgeMs: 1234,
      watchdogLimitSeconds: 675,
      silenceWatchdogSeconds: 60,
      editorReadyProbe: {
        success: false,
        probes: { contentEditableFound: false },
      },
      loginProbe: {
        loginDetected: false,
        autoLoginTriggered: true,
        writeUrlReached: false,
        frameWriteReached: false,
      },
      debugRootDir: root,
    });

    const report = JSON.parse(
      fs.readFileSync(path.join(debugDir, 'timeout_report.json'), 'utf-8'),
    );
    expect(report.capture_errors.some((e: any) => e.type === 'screenshot_save_failed')).toBe(true);
    expect(report.login_probe?.autoLoginTriggered).toBe(true);
    expect(report.artifact_status.page_content_saved).toBe(true);
    expect(report.artifact_status.frame_content_saved).toBe(true);
  });

  test('EDITOR_IFRAME_NOT_FOUND reason + frame 없음 시 report/skip 기록', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'timeout-debug-collector-iframe-'));
    const page = {
      url: () => 'https://blog.naver.com/jun12310?Redirect=Write&',
      title: async () => '그낙 : 네이버 블로그',
      screenshot: async () => ({}),
      content: async () => '<html><body>writer page</body></html>',
      evaluate: async <T>(fn: () => T): Promise<T> => {
        const src = String(fn);
        if (src.includes('activeElement')) {
          return ({ tagName: 'BODY' } as unknown) as T;
        }
        return ([] as unknown) as T;
      },
    };

    const { debugDir } = await collectTimeoutDebugArtifacts({
      page,
      frame: null,
      reason: 'EDITOR_IFRAME_NOT_FOUND',
      currentStage: 'write_page_enter',
      lastActivityLabel: 'write_page_enter',
      lastActivityAgeMs: 100,
      watchdogLimitSeconds: 675,
      silenceWatchdogSeconds: 60,
      editorReadyProbe: null,
      loginProbe: {
        loginDetected: true,
        autoLoginTriggered: true,
        writeUrlReached: true,
        frameWriteReached: false,
      },
      loginState: {
        state: 'logged_in',
        signal: 'writer_iframe',
      },
      iframeProbe: {
        expectedFrameUrlPatternMatched: false,
        frameCount: 1,
        triedSelectors: ['iframe#mainFrame'],
        lastSeenFrameUrls: ['https://blog.naver.com/'],
      },
      debugRootDir: root,
    });

    const reportPath = path.join(debugDir, 'timeout_report.json');
    expect(fs.existsSync(reportPath)).toBe(true);
    const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
    expect(report.reason).toBe('EDITOR_IFRAME_NOT_FOUND');
    expect(report.current_stage).toBe('write_page_enter');
    expect(report.artifact_status.screenshot_saved).toBe(true);
    expect(report.artifact_status.page_content_saved).toBe(true);
    expect(report.capture_errors.some((e: any) => e.type === 'no_frame')).toBe(true);
  });
});
