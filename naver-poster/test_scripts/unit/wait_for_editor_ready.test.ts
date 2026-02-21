import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Browser, chromium, Frame, Page } from 'playwright';
import { getLastEditorReadyProbeSummary, waitForEditorReady } from '../../src/naver/editor';
import { collectTimeoutDebugArtifacts } from '../../src/naver/timeout_debug';

describe('waitForEditorReady', () => {
  let browser: Browser;
  let artifactsDir: string;

  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
    artifactsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'editor-ready-test-'));
  });

  afterAll(async () => {
    await browser.close();
  });

  async function getMainFrame(page: Page): Promise<Frame> {
    await page.waitForSelector('iframe#mainFrame', { timeout: 2_000 });
    const iframe = await page.$('iframe#mainFrame');
    if (!iframe) throw new Error('iframe_not_found');
    const frame = await iframe.contentFrame();
    if (!frame) throw new Error('frame_not_found');
    return frame;
  }

  async function reacquireMainFrame(page: Page): Promise<Frame | null> {
    const iframe = await page.$('iframe#mainFrame');
    if (!iframe) return null;
    return await iframe.contentFrame();
  }

  test('Case1: contentEditable가 존재하면 ready 성공', async () => {
    const page = await browser.newPage();
    await page.setContent(`
      <iframe id="mainFrame" srcdoc="
        <html><body>
          <div class='se-toolbar'><button>굵게</button></div>
          <div contenteditable='true'>본문</div>
        </body></html>
      "></iframe>
    `);
    const initialFrame = await getMainFrame(page);

    const ok = await waitForEditorReady(initialFrame, artifactsDir, page, {
      timeBudgetMs: 3_000,
      pollIntervalMs: 100,
      perSelectorTimeoutMs: 120,
      reacquireFrame: async () => reacquireMainFrame(page),
    });

    expect(ok).toBe(true);
    await page.close();
  });

  test('Case2: iframe detach/attach 교체 후에도 재획득으로 ready 성공', async () => {
    const page = await browser.newPage();
    await page.setContent(`
      <iframe id="mainFrame" srcdoc="
        <html><body><div id='booting'>loading</div></body></html>
      "></iframe>
    `);
    const initialFrame = await getMainFrame(page);

    await page.evaluate(() => {
      setTimeout(() => {
        const next = document.createElement('iframe');
        next.id = 'mainFrame';
        next.setAttribute('srcdoc', "<html><body><div contenteditable='true'>body</div></body></html>");
        const old = document.querySelector('iframe#mainFrame');
        old?.replaceWith(next);
      }, 220);
    });

    const ok = await waitForEditorReady(initialFrame, artifactsDir, page, {
      timeBudgetMs: 4_000,
      pollIntervalMs: 100,
      perSelectorTimeoutMs: 120,
      reacquireFrame: async () => reacquireMainFrame(page),
    });

    expect(ok).toBe(true);
    await page.close();
  });

  test('Case3: spinner가 사라지고 editor가 나타나는 지연 로딩 케이스 성공', async () => {
    const page = await browser.newPage();
    await page.setContent(`
      <iframe id="mainFrame" srcdoc="
        <html><body>
          <div class='se-loading' id='spin'>loading</div>
          <script>
            setTimeout(() => {
              const spin = document.getElementById('spin');
              if (spin) spin.style.display = 'none';
              const ed = document.createElement('div');
              ed.setAttribute('contenteditable', 'true');
              ed.textContent = 'editor ready';
              document.body.appendChild(ed);
            }, 260);
          </script>
        </body></html>
      "></iframe>
    `);
    const initialFrame = await getMainFrame(page);

    const ok = await waitForEditorReady(initialFrame, artifactsDir, page, {
      timeBudgetMs: 4_000,
      pollIntervalMs: 100,
      perSelectorTimeoutMs: 120,
      reacquireFrame: async () => reacquireMainFrame(page),
    });

    expect(ok).toBe(true);
    await page.close();
  });

  test('실패 시 명확한 timeout 에러를 반환하고 정체하지 않는다', async () => {
    const page = await browser.newPage();
    await page.setContent(`
      <iframe id="mainFrame" srcdoc="
        <html><body><div id='x'>still loading</div></body></html>
      "></iframe>
    `);
    const initialFrame = await getMainFrame(page);
    const budgetMs = 1_200;
    const started = Date.now();

    await expect(
      waitForEditorReady(initialFrame, artifactsDir, page, {
        timeBudgetMs: budgetMs,
        pollIntervalMs: 100,
        perSelectorTimeoutMs: 120,
        reacquireFrame: async () => reacquireMainFrame(page),
      }),
    ).rejects.toThrow('[EDITOR_READY_TIMEOUT]');

    const summary = getLastEditorReadyProbeSummary() as any;
    expect(summary?.lastSnapshot?.probes?.contentEditableFound).toBe(false);

    const debugRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'editor-ready-timeout-debug-'));
    const debugResult = await collectTimeoutDebugArtifacts({
      page,
      frame: initialFrame,
      reason: 'stage_timeout_write_page_enter_45s',
      currentStage: 'write_page_enter',
      lastActivityLabel: 'write_page_enter',
      lastActivityAgeMs: 500,
      watchdogLimitSeconds: 675,
      silenceWatchdogSeconds: 60,
      editorReadyProbe: summary,
      debugRootDir: debugRoot,
    });
    const reportPath = path.join(debugResult.debugDir, 'timeout_report.json');
    const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
    expect(report.editor_ready_probe?.lastSnapshot?.probes?.contentEditableFound).toBe(false);

    const elapsed = Date.now() - started;
    expect(elapsed).toBeLessThanOrEqual(budgetMs * 3);
    await page.close();
  });

  test('recovery 이후 contentEditable 신호가 살아나면 성공한다', async () => {
    const page = await browser.newPage();
    await page.setContent(`
      <iframe id="mainFrame" srcdoc="
        <html><body><div id='booting'>loading</div></body></html>
      "></iframe>
    `);
    const initialFrame = await getMainFrame(page);
    await page.evaluate(() => {
      setTimeout(() => {
        const iframe = document.querySelector('iframe#mainFrame') as HTMLIFrameElement | null;
        if (iframe) {
          iframe.setAttribute('srcdoc', '<html><body><div contenteditable=\"true\">ready after recovery</div></body></html>');
        }
      }, 1_150);
    });

    const ok = await waitForEditorReady(initialFrame, artifactsDir, page, {
      timeBudgetMs: 1_600,
      pollIntervalMs: 100,
      perSelectorTimeoutMs: 120,
      reacquireFrame: async () => reacquireMainFrame(page),
    });
    expect(ok).toBe(true);

    const summary = getLastEditorReadyProbeSummary() as any;
    expect(summary?.success).toBe(true);
    expect(summary?.recoveryAttempted).toBe(true);
    expect(summary?.recoveryCount).toBe(1);

    await page.close();
  });
});
