/**
 * Login Policy v2 단위 테스트
 *
 * 검증 항목:
 * 1) headless + LOGGED_OUT → 자격증명 자동 입력 SKIP → SessionBlockedError
 * 2) CHALLENGE_DETECTED → 즉시 SessionBlockedError + cooldown 저장
 * 3) 동일 run 내 2회 자동 로그인 시도 방지 (session.autoLoginAttempted=true)
 * 4) worker SECURITY_CHALLENGE → interactiveLogin fallback 없이 즉시 BLOCKED_LOGIN
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  classifyLoginState,
  ensureLoggedIn,
  getSessionCooldownPath,
  isCooldownActive,
  loadSessionCooldown,
  SessionBlockedError,
  type SessionOptions,
  type SessionResult,
} from '../../src/naver/session';
import { WorkerService } from '../../src/worker/worker_service';
import { type FailureReasonCode } from '../../src/worker/types';

// ────────────────────────────────────────────────────────────────
// 공통 mock 헬퍼
// ────────────────────────────────────────────────────────────────

function makeFakePage(opts: {
  url?: string;
  hasLoginForm?: boolean;
  hasCaptcha?: boolean;
  hasWriterFrame?: boolean;
}): any {
  const {
    url = 'https://nid.naver.com/nidlogin.login',
    hasLoginForm = false,
    hasCaptcha = false,
    hasWriterFrame = false,
  } = opts;
  let currentUrl = url;

  return {
    goto: async (u: string) => { currentUrl = u; },
    url: () => currentUrl,
    title: async () => 'mock-title',
    content: async () => '<html></html>',
    screenshot: async () => undefined,
    evaluate: async () => hasCaptcha ? '캡차 보안문자 자동입력방지' : '',
    locator: (selector: string) => ({
      first: () => ({
        count: async () => {
          if (selector === '#id' && hasLoginForm) return 1;
          if (selector === '#captcha_image' && hasCaptcha) return 1;
          if (selector === 'iframe#mainFrame' && hasWriterFrame) return 1;
          return 0;
        },
        isVisible: async () => false,
        textContent: async () => null,
      }),
    }),
    frames: () => hasWriterFrame
      ? [{ url: () => 'https://blog.naver.com/PostWriteForm.naver' }]
      : [],
    frame: () => null,
    waitForTimeout: async () => undefined,
    waitForURL: async () => undefined,
    waitForSelector: async () => undefined,
    fill: async () => undefined,
    click: async () => undefined,
    context: () => ({
      cookies: async () => [],
    }),
  };
}

function makeSession(page: any, overrides: Partial<SessionResult> = {}): SessionResult {
  return {
    browser: null,
    context: { cookies: async () => [] } as any,
    page,
    isPersistentProfile: true,
    profileDir: undefined,
    ...overrides,
  } as SessionResult;
}

// ────────────────────────────────────────────────────────────────
// Test 1: headless + LOGGED_OUT → 자격증명 입력 SKIP
// ────────────────────────────────────────────────────────────────
describe('Login Policy v2 - T1: headless + LOGGED_OUT → 자격증명 SKIP', () => {
  test('headless=true이면 logged_out 상태에서 SessionBlockedError를 던진다 (credential 시도 안 함)', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lp2-t1-'));
    // 로그인 폼이 있는 페이지 (LOGGED_OUT)
    const page = makeFakePage({ url: 'https://nid.naver.com/nidlogin.login', hasLoginForm: true });
    const session = makeSession(page);
    const opts: SessionOptions = {
      userDataDir: tempDir,
      headless: true,
      // enabledInHeadless 기본값 false → credential 시도 금지
    };

    await expect(
      ensureLoggedIn(session, opts, 'https://blog.naver.com/jun12310?Redirect=Write&'),
    ).rejects.toThrow(SessionBlockedError);

    // session.autoLoginAttempted는 false이어야 함 (시도하지 않았으므로)
    expect(session.autoLoginAttempted).toBeFalsy();

    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  test('headless=false이면 logged_out 상태에서 credential 시도(autoLoginAttempted=true)가 일어난다', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lp2-t1b-'));
    // NAVER_ID/PW 없으면 attempt 내부에서 실패하지만 시도 자체는 진행됨
    const savedId = process.env.NAVER_ID;
    const savedPw = process.env.NAVER_PW;
    delete process.env.NAVER_ID;
    delete process.env.NAVER_PW;

    const page = makeFakePage({ url: 'https://nid.naver.com/nidlogin.login', hasLoginForm: true });
    const session = makeSession(page);
    const opts: SessionOptions = {
      userDataDir: tempDir,
      headless: false,
    };

    try {
      await ensureLoggedIn(session, opts, 'https://blog.naver.com/jun12310?Redirect=Write&');
    } catch {
      // 예외는 예상됨 (NAVER_ID/PW 없으면 로그인 실패)
    }

    // 시도가 일어났으므로 autoLoginAttempted = true
    expect(session.autoLoginAttempted).toBe(true);
    fs.rmSync(tempDir, { recursive: true, force: true });
    if (savedId !== undefined) process.env.NAVER_ID = savedId;
    if (savedPw !== undefined) process.env.NAVER_PW = savedPw;
  });
});

// ────────────────────────────────────────────────────────────────
// Test 2: CHALLENGE_DETECTED → 즉시 차단 + cooldown 저장
// ────────────────────────────────────────────────────────────────
describe('Login Policy v2 - T2: CHALLENGE_DETECTED → 즉시 BLOCKED + cooldown 저장', () => {
  test('CAPTCHA 신호 감지 시 SessionBlockedError를 던지고 cooldown 파일을 저장한다', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lp2-t2-'));
    const page = makeFakePage({
      url: 'https://nid.naver.com/nidlogin.login',
      hasCaptcha: true,
      hasLoginForm: true,
    });
    const session = makeSession(page);
    const opts: SessionOptions = { userDataDir: tempDir, headless: true };

    await expect(
      ensureLoggedIn(session, opts, 'https://blog.naver.com/jun12310?Redirect=Write&'),
    ).rejects.toThrow(SessionBlockedError);

    // cooldown 파일이 생성되어야 함
    const cooldownPath = getSessionCooldownPath(tempDir);
    const cooldown = loadSessionCooldown(cooldownPath);
    expect(isCooldownActive(cooldown)).toBe(true);
    // CAPTCHA_DETECTED는 장시간 쿨다운
    expect(cooldown.lastReason).toBe('CAPTCHA_DETECTED');
    expect(cooldown.cooldownUntilTs - Date.now()).toBeGreaterThan(60 * 60 * 1000); // 최소 1시간

    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  test('CHALLENGE 시 session.autoLoginAttempted는 false (시도 없이 차단)', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lp2-t2b-'));
    const page = makeFakePage({
      url: 'https://nid.naver.com/nidlogin.login',
      hasCaptcha: true,
    });
    const session = makeSession(page);
    const opts: SessionOptions = { userDataDir: tempDir, headless: true };

    try {
      await ensureLoggedIn(session, opts, 'https://blog.naver.com/jun12310?Redirect=Write&');
    } catch { /* 예상된 예외 */ }

    expect(session.autoLoginAttempted).toBeFalsy();
    fs.rmSync(tempDir, { recursive: true, force: true });
  });
});

// ────────────────────────────────────────────────────────────────
// Test 3: 동일 run 내 2회 자동 로그인 시도 방지
// ────────────────────────────────────────────────────────────────
describe('Login Policy v2 - T3: 동일 run 내 2회 credential 시도 방지', () => {
  test('session.autoLoginAttempted=true이면 두 번째 ensureLoggedIn 호출 시 즉시 차단', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lp2-t3-'));
    const page = makeFakePage({ url: 'https://nid.naver.com/nidlogin.login', hasLoginForm: true });
    // 첫 번째 시도 이후 상태: autoLoginAttempted=true
    const session = makeSession(page, { autoLoginAttempted: true });
    const opts: SessionOptions = {
      userDataDir: tempDir,
      headless: false, // headless 제한 제거해도 2회 차단
    };

    await expect(
      ensureLoggedIn(session, opts, 'https://blog.naver.com/jun12310?Redirect=Write&'),
    ).rejects.toThrow(SessionBlockedError);

    fs.rmSync(tempDir, { recursive: true, force: true });
  });
});

// ────────────────────────────────────────────────────────────────
// Test 4: worker - SECURITY_CHALLENGE → interactiveLogin fallback 없이 즉시 BLOCKED_LOGIN
// ────────────────────────────────────────────────────────────────
describe('Login Policy v2 - T4: worker SECURITY_CHALLENGE → 즉시 BLOCKED_LOGIN (fallback 없음)', () => {
  test('SECURITY_CHALLENGE 수신 시 worker는 fallback 없이 BLOCKED_LOGIN으로 전환한다', async () => {
    const tmpQueue = path.resolve('/tmp', `test_queue_lp2_${Date.now()}.json`);
    const now = new Date().toISOString();
    const job = {
      id: 'job-captcha-test',
      status: 'PENDING' as const,
      mode: 'draft' as const,
      dirPath: '/tmp/test-dir',
      chatId: 'chat-456',
      createdAt: now,
      updatedAt: now,
      attempts: 0,
    };
    fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [job] }, null, 2));

    const adminMessages: string[] = [];
    const userMessages: string[] = [];

    const service = new WorkerService(
      { queuePath: tmpQueue, pollSec: 1, headless: true, resume: false },
      {
        executeUploadJob: async () => ({
          ok: false,
          reasonCode: 'SECURITY_CHALLENGE' as FailureReasonCode,
          detail: 'CAPTCHA_DETECTED',
          stdout: '[auto_login_attempt] blocked_reason=CAPTCHA_DETECTED',
          stderr: '',
        }),
        notifyAdmin: async (msg) => { adminMessages.push(msg); },
        notifyUser: async (_cid, msg) => { userMessages.push(msg); },
      },
    );

    await service.processNextJob();

    // 즉시 BLOCKED_LOGIN 전환
    const updated = JSON.parse(fs.readFileSync(tmpQueue, 'utf-8')).jobs[0];
    expect(updated.status).toBe('BLOCKED_LOGIN');
    expect(updated.reasonCode).toBe('SECURITY_CHALLENGE');

    // fallback 시도 없이 바로 운영자에게 알림
    expect(adminMessages.length).toBeGreaterThan(0);
    expect(adminMessages[0]).toContain('interactiveLogin');

    // notifyUser도 BLOCKED_LOGIN 안내
    expect(userMessages.some((m) => m.includes('BLOCKED_LOGIN'))).toBe(true);

    fs.rmSync(tmpQueue, { force: true });
  });

  test('worker_service.ts 소스에 attemptInteractiveLoginFallback이 없다 (정적 검증)', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '../../src/worker/worker_service.ts'),
      'utf-8',
    );
    expect(src).not.toContain('attemptInteractiveLoginFallback');
    expect(src).not.toContain('interactiveLoginTimeoutMs');
  });
});

// ────────────────────────────────────────────────────────────────
// classifyLoginState 정적 분류 테스트 (상태 머신 기반)
// ────────────────────────────────────────────────────────────────
describe('Login Policy v2 - 상태 머신 분류 (classifyLoginState)', () => {
  const WRITE_URL = 'https://blog.naver.com/PostWriteForm.naver';

  test('writer iframe 존재 → logged_in', () => {
    const result = classifyLoginState(WRITE_URL, true, null, null, false);
    expect(result.state).toBe('logged_in');
    expect(result.signal).toBe('writer_iframe');
  });

  test('로그인 쿠키만 존재 → logged_in', () => {
    const result = classifyLoginState('https://www.naver.com', false, null, null, true);
    expect(result.state).toBe('logged_in');
    expect(result.signal).toBe('login_cookie_present');
  });

  test('로그아웃 지시자 → logged_out', () => {
    const result = classifyLoginState('https://nid.naver.com/nidlogin.login', false, null, '#id', false);
    expect(result.state).toBe('logged_out');
  });

  test('신호 없음 → unknown (AMBIGUOUS)', () => {
    const result = classifyLoginState('https://naver.com', false, null, null, false);
    expect(result.state).toBe('unknown');
  });
});
