import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  buildCooldownState,
  clearSessionCooldown,
  ensureLoggedIn,
  getSessionCooldownPath,
  isCooldownActive,
  type SessionOptions,
  type SessionResult,
} from '../../src/naver/session';

describe('session cooldown policy', () => {
  test('CAPTCHA_DETECTED는 장시간 쿨다운을 설정한다', () => {
    const now = Date.now();
    const next = buildCooldownState(
      { lastReason: null, lastTs: 0, cooldownUntilTs: 0, consecutiveFailures: 0 },
      'CAPTCHA_DETECTED',
      now,
    );
    expect(next.cooldownUntilTs - now).toBeGreaterThanOrEqual(12 * 60 * 60 * 1000);
    expect(isCooldownActive(next, now + 1)).toBe(true);
  });

  test('clearSessionCooldown은 상태 파일을 제거한다', () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'session-cooldown-clear-'));
    const cooldownPath = getSessionCooldownPath(tempDir);
    fs.mkdirSync(path.dirname(cooldownPath), { recursive: true });
    fs.writeFileSync(
      cooldownPath,
      JSON.stringify({ lastReason: 'CAPTCHA_DETECTED', cooldownUntilTs: Date.now() + 1000 }, null, 2),
      'utf-8',
    );
    expect(fs.existsSync(cooldownPath)).toBe(true);
    clearSessionCooldown(tempDir);
    expect(fs.existsSync(cooldownPath)).toBe(false);
  });

  test('passive 모드에서 cooldown active면 autoLogin 시도 없이 SessionBlockedError', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'session-cooldown-active-'));
    const cooldownPath = getSessionCooldownPath(tempDir);
    fs.mkdirSync(path.dirname(cooldownPath), { recursive: true });
    fs.writeFileSync(
      cooldownPath,
      JSON.stringify({
        lastReason: 'CAPTCHA_DETECTED',
        lastTs: Date.now(),
        cooldownUntilTs: Date.now() + 60_000,
        consecutiveFailures: 2,
      }, null, 2),
      'utf-8',
    );

    let currentUrl = 'https://blog.naver.com/jun12310?Redirect=Write&';
    const fakePage = {
      goto: async (url: string) => {
        currentUrl = url;
      },
      url: () => currentUrl,
      title: async () => 'mock-title',
      content: async () => '<html></html>',
      screenshot: async () => undefined,
      locator: (selector: string) => ({
        first: () => ({
          count: async () => (selector === '#id' ? 1 : 0),
          isVisible: async () => selector === '#id',
          textContent: async () => null,
        }),
      }),
      frames: () => [],
      frame: () => null,
      waitForTimeout: async () => undefined,
      evaluate: async () => '',
    } as any;
    const session = {
      browser: null,
      context: { cookies: async () => [] },
      page: fakePage,
    } as unknown as SessionResult;
    const opts: SessionOptions = { userDataDir: tempDir };

    try {
      await ensureLoggedIn(session, opts, 'https://blog.naver.com/jun12310?Redirect=Write&', 'passive');
      throw new Error('expected ensureLoggedIn to throw');
    } catch (error: any) {
      expect(error).toBeDefined();
    }
  });
});
