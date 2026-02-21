import { Browser, chromium, Frame, Page } from 'playwright';
import { DraftSaver } from '../../src/naver/draft_saver';
import type { TempSaveClickResult } from '../../src/naver/editor';

describe('local editor fixture (offline)', () => {
  let browser: Browser;

  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
  });

  afterAll(async () => {
    await browser.close();
  });

  const baseHtml = `
    <html>
      <body>
        <button id="save-btn">임시저장</button>
        <div id="toast-a" style="display:none"></div>
        <div id="toast-b" style="display:none"></div>
        <div id="overlay" style="display:none; width:100px; height:100px"></div>
      </body>
    </html>
  `;

  async function runSaver(
    page: Page,
    options?: { closeOverlayOnPrepare?: boolean; toastAfterOverlayClose?: boolean },
  ): Promise<TempSaveClickResult> {
    const ctx = { page, frame: page.mainFrame() as Frame };
    const saver = new DraftSaver({
      ctx,
      clickSave: async () => {
        const btn = await page.$('#save-btn');
        if (!btn) return false;
        await btn.click().catch(() => undefined);
        return true;
      },
      prepare: async () => {
        if (options?.closeOverlayOnPrepare) {
          await page.evaluate(() => {
            const overlay = document.querySelector('#overlay') as HTMLElement | null;
            if (overlay) overlay.style.display = 'none';
          });
        }
      },
      detectOverlay: async () => (await page.locator('#overlay:visible').count()) > 0,
      closeOverlay: async () => {
        await page.evaluate(() => {
          const overlay = document.querySelector('#overlay') as HTMLElement | null;
          if (overlay) overlay.style.display = 'none';
        });
        if (options?.toastAfterOverlayClose) {
          await page.evaluate(() => {
            const toast = document.querySelector('#toast-a') as HTMLElement | null;
            if (toast) {
              toast.style.display = 'block';
              toast.textContent = '임시저장 완료';
            }
          });
        }
      },
      reacquireFrame: async () => true,
      signalTimeBudgetMs: 1_200,
      pollIntervalMs: 50,
      maxRecoveryCount: 1,
    });

    return saver.save();
  }

  test('I1: overlay로 클릭 막힘 -> recovery 후 성공', async () => {
    const page = await browser.newPage();
    await page.setContent(baseHtml);
    await page.evaluate(() => {
      const overlay = document.querySelector('#overlay') as HTMLElement | null;
      if (overlay) overlay.style.display = 'block';
    });

    const result = await runSaver(page, { toastAfterOverlayClose: true });
    expect(result.success).toBe(true);
    expect((result.retries ?? 0)).toBeLessThanOrEqual(1);
    await page.close();
  });

  test('I2: toastA 없음/toastB만 있어도 성공', async () => {
    const page = await browser.newPage();
    await page.setContent(baseHtml);
    await page.evaluate(() => {
      const toast = document.querySelector('#toast-b') as HTMLElement | null;
      if (toast) {
        setTimeout(() => {
          toast.style.display = 'block';
          toast.textContent = '임시저장되었습니다';
        }, 120);
      }
    });

    const result = await runSaver(page);
    expect(result.success).toBe(true);
    await page.close();
  });

  test('I3: sessionBlocked면 즉시 실패', async () => {
    const page = await browser.newPage();
    await page.setContent(`${baseHtml}<input id="id" />`);

    const result = await runSaver(page);
    expect(result.success).toBe(false);
    expect(result.error || '').toContain('SessionBlockedError');
    await page.close();
  });
});
