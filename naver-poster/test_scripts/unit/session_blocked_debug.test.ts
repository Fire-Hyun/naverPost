jest.mock('../../src/naver/timeout_debug', () => ({
  collectTimeoutDebugArtifacts: jest.fn(async () => ({
    debugDir: '/tmp/mock-timeout-debug',
    report: {},
  })),
}));

import { buildSessionBlockedError, SessionBlockedError } from '../../src/naver/session';
import { collectTimeoutDebugArtifacts } from '../../src/naver/timeout_debug';

describe('session blocked debug handling', () => {
  test('session blocked 경로에서 timeoutdebug collector를 호출한다', async () => {
    const fakeFrame = {
      url: () => 'https://blog.naver.com/PostWriteForm.naver',
    };
    const fakePage = {
      url: () => 'https://nid.naver.com/nidlogin.login',
      frames: () => [fakeFrame],
      frame: () => fakeFrame,
      waitForTimeout: async () => undefined,
    } as any;

    const error = await buildSessionBlockedError(
      fakePage,
      'https://blog.naver.com/jun12310?Redirect=Write&',
      false,
      true,
      'SESSION_BLOCKED_LOGIN_STUCK',
      undefined,
      5,
    );

    expect(error).toBeInstanceOf(SessionBlockedError);
    expect(error.reason).toBe('SESSION_BLOCKED_LOGIN_STUCK');
    expect(error.loginProbe.loginDetected).toBe(false);
    expect(error.loginProbe.autoLoginTriggered).toBe(true);
    expect(collectTimeoutDebugArtifacts).toHaveBeenCalledTimes(1);
  });

  test('세부 차단 reason이 loginProbe에 반영된다', async () => {
    const fakePage = {
      url: () => 'https://nid.naver.com/nidlogin.login',
      frames: () => [],
      frame: () => null,
      waitForTimeout: async () => undefined,
      evaluate: async () => '',
    } as any;

    const error = await buildSessionBlockedError(
      fakePage,
      'https://blog.naver.com/jun12310?Redirect=Write&',
      false,
      true,
      'CAPTCHA_DETECTED',
      {
        writeUrlReached: false,
        frameWriteReached: false,
        gotoRetried: true,
        loginSignal: 'blocked:CAPTCHA_DETECTED',
        blockReason: 'CAPTCHA_DETECTED',
      },
      5,
    );

    expect(error.reason).toBe('CAPTCHA_DETECTED');
    expect(error.loginProbe.blockReason).toBe('CAPTCHA_DETECTED');
    expect(error.loginProbe.gotoRetried).toBe(true);
  });
});
