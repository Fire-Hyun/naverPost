import { Browser, chromium, Frame, Page } from 'playwright';
import { SignalDetector } from '../../src/naver/signal_detector';

describe('signal detector', () => {
  let browser: Browser;

  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
  });

  afterAll(async () => {
    await browser.close();
  });

  const baseHtml = '<html><body><div id="root"></div></body></html>';

  const detectorOf = (page: Page) => new SignalDetector({
    page,
    frameRef: () => page.mainFrame() as Frame,
  });

  test('toast only', async () => {
    const page = await browser.newPage();
    await page.setContent(baseHtml);
    await page.evaluate(() => {
      const toast = document.createElement('div');
      toast.className = 'toast-layer';
      toast.textContent = '임시저장 완료';
      document.body.appendChild(toast);
    });
    const signals = await detectorOf(page).detect();
    expect(signals.toast).toBe(true);
    expect(signals.spinner).toBe(false);
    await page.close();
  });

  test('spinner only', async () => {
    const page = await browser.newPage();
    await page.setContent(baseHtml);
    await page.evaluate(() => {
      const spinner = document.createElement('div');
      spinner.className = 'saving-spinner';
      spinner.style.width = '20px';
      spinner.style.height = '20px';
      document.body.appendChild(spinner);
    });
    const signals = await detectorOf(page).detect();
    expect(signals.spinner).toBe(true);
    expect(signals.toast).toBe(false);
    await page.close();
  });

  test('overlay only', async () => {
    const page = await browser.newPage();
    await page.setContent(baseHtml);
    await page.evaluate(() => {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.style.width = '100px';
      overlay.style.height = '100px';
      overlay.style.display = 'block';
      document.body.appendChild(overlay);
    });
    const signals = await detectorOf(page).detect();
    expect(signals.overlay).toBe(true);
    await page.close();
  });

  test('session blocked only', async () => {
    const page = await browser.newPage();
    await page.setContent('<html><body><div>로그인이 필요합니다</div><input id="id"/></body></html>');
    const signals = await detectorOf(page).detect();
    expect(signals.sessionBlocked).toBe(true);
    await page.close();
  });
});
