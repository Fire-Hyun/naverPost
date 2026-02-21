import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { EditorIframeNotFoundError } from '../../src/naver/editor';
import { collectTimeoutDebugArtifacts } from '../../src/naver/timeout_debug';

describe('editor iframe not found handling', () => {
  test('EditorIframeNotFoundError 상황에서도 debugDir/timeout_report가 생성된다', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'editor-iframe-notfound-'));
    const error = new EditorIframeNotFoundError('EDITOR_IFRAME_NOT_FOUND', {
      expectedFrameUrlPatternMatched: false,
      frameCount: 0,
      triedSelectors: ['iframe#mainFrame', 'iframe[src*="PostWriteForm"]'],
      lastSeenFrameUrls: [],
    });

    const page = {
      url: () => 'https://blog.naver.com/jun12310?Redirect=Write&',
      title: async () => 'writer',
      screenshot: async () => ({}),
      content: async () => '<html><body>x</body></html>',
      evaluate: async <T>(fn: () => T): Promise<T> => {
        const src = String(fn);
        if (src.includes('activeElement')) return ({ tagName: 'BODY' } as unknown) as T;
        return ([] as unknown) as T;
      },
    };

    const result = await collectTimeoutDebugArtifacts({
      page,
      frame: null,
      reason: error.reason,
      currentStage: 'write_page_enter',
      lastActivityLabel: 'write_page_enter',
      lastActivityAgeMs: 0,
      watchdogLimitSeconds: 0,
      silenceWatchdogSeconds: 0,
      editorReadyProbe: null,
      loginProbe: null,
      iframeProbe: error.iframeProbe,
      loginState: { state: 'logged_in', signal: 'writer_iframe' },
      debugRootDir: root,
    });

    const reportPath = path.join(result.debugDir, 'timeout_report.json');
    expect(fs.existsSync(reportPath)).toBe(true);
    const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
    expect(report.reason).toBe('EDITOR_IFRAME_NOT_FOUND');
    expect(report.iframe_probe?.frameCount).toBe(0);
  });
});
