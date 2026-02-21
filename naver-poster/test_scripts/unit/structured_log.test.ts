import * as fs from 'fs';
import * as path from 'path';
import { logStructured, sanitizeLogPayload, getRunContext, getRunArtifactDir } from '../../src/utils/logger';

// ────────────────────────────────────────────────────────────────────
// 헬퍼: process.stdout.write 캡처
// ────────────────────────────────────────────────────────────────────
function captureStdout(fn: () => void): string[] {
  const captured: string[] = [];
  const spy = jest
    .spyOn(process.stdout, 'write')
    .mockImplementation((chunk: string | Uint8Array) => {
      captured.push(String(chunk));
      return true;
    });
  try {
    fn();
  } finally {
    spy.mockRestore();
  }
  return captured;
}

function extractJsonFromLines(lines: string[], eventName: string): Record<string, unknown> {
  const line = lines.find((l) => l.includes(`${eventName}: {`));
  if (!line) throw new Error(`'${eventName}:' 포함 로그 라인을 찾지 못했습니다. 캡처된 라인:\n${lines.join('\n')}`);
  const idx = line.indexOf(`${eventName}: `);
  const jsonStr = line.slice(idx + eventName.length + 2).trim();
  return JSON.parse(jsonStr);
}

// ────────────────────────────────────────────────────────────────────
// Test 1: 로그 스키마 스냅샷
// ────────────────────────────────────────────────────────────────────
describe('structured log schema', () => {
  beforeEach(() => {
    process.env.NAVER_RUN_ID = 'test-run-123';
    delete process.env.NAVER_JOB_KEY;
  });

  afterEach(() => {
    delete process.env.NAVER_RUN_ID;
    delete process.env.NAVER_JOB_KEY;
  });

  test('session_init 로그에 필수 필드가 포함된다', () => {
    const lines = captureStdout(() => {
      logStructured('session_init', {
        stage: 'SESSION_INIT',
        profile_dir: '/tmp/test-profile',
        context_mode: 'persistent',
        headless: true,
        storage_state_exists: false,
        storage_state_load_reason: null,
        storage_state_cookie_count: 0,
        storage_state_age_seconds: -1,
        singleton_lock_found: false,
        elapsed_ms: 100,
      });
    });
    const json = extractJsonFromLines(lines, 'session_init');
    expect(json.run_id).toBe('test-run-123');
    expect(json.stage).toBe('SESSION_INIT');
    expect(json.profile_dir).toBeDefined();
    expect(json.context_mode).toBeDefined();
    expect(json.headless).toBe(true);
    expect(json.storage_state_exists).toBe(false);
    expect(json.singleton_lock_found).toBe(false);
    expect(typeof json.elapsed_ms).toBe('number');
    expect((json.elapsed_ms as number)).toBeGreaterThanOrEqual(0);
  });

  test('login_check 로그에 필수 필드가 포함된다', () => {
    process.env.NAVER_JOB_KEY = 'job-abc';
    const lines = captureStdout(() => {
      logStructured('login_check', {
        stage: 'LOGIN_CHECK',
        url: 'https://blog.naver.com/write',
        login_phase: 'LOGGED_OUT',
        signal: 'login_form_visible',
        cooldown_active: false,
        cooldown_remaining_sec: 0,
        consecutive_failures: 0,
        headless: true,
      });
    });
    const json = extractJsonFromLines(lines, 'login_check');
    expect(json.run_id).toBe('test-run-123');
    expect(json.job_id).toBe('job-abc');
    expect(json.stage).toBe('LOGIN_CHECK');
    expect(json.url).toBeDefined();
    expect(json.login_phase).toBe('LOGGED_OUT');
    expect(json.signal).toBeDefined();
    expect(typeof json.cooldown_active).toBe('boolean');
    expect(typeof json.consecutive_failures).toBe('number');
  });

  test('auto_login_attempt 로그에 필수 필드가 포함된다', () => {
    const lines = captureStdout(() => {
      logStructured('auto_login_attempt', {
        stage: 'AUTO_LOGIN_ATTEMPT',
        attempted: true,
        result: 'success',
        skipped_reason: null,
        blocked_reason: null,
        duration_ms: 3500,
        headless: false,
        url: 'https://nid.naver.com/nidlogin.login',
      });
    });
    const json = extractJsonFromLines(lines, 'auto_login_attempt');
    expect(json.run_id).toBe('test-run-123');
    expect(json.stage).toBe('AUTO_LOGIN_ATTEMPT');
    expect(json.attempted).toBe(true);
    expect(json.result).toBe('success');
    expect(json.blocked_reason).toBeNull();
    expect(typeof json.duration_ms).toBe('number');
  });
});

// ────────────────────────────────────────────────────────────────────
// Test 2: 민감정보 필터링
// ────────────────────────────────────────────────────────────────────
describe('sanitizeLogPayload', () => {
  afterEach(() => {
    delete process.env.NAVER_ID;
    delete process.env.NAVER_PW;
  });

  test('NAVER_ID 값이 로그에 포함되지 않는다', () => {
    process.env.NAVER_ID = 'testuser123';
    const result = sanitizeLogPayload({ user: 'testuser123', other: 'ok' });
    expect(JSON.stringify(result)).not.toContain('testuser123');
    expect(JSON.stringify(result)).toContain('[REDACTED_ID]');
  });

  test('NAVER_PW 값이 로그에 포함되지 않는다', () => {
    process.env.NAVER_PW = 'secret_password_456';
    const result = sanitizeLogPayload({ pw_field: 'secret_password_456', other: 'data' });
    expect(JSON.stringify(result)).not.toContain('secret_password_456');
    expect(JSON.stringify(result)).toContain('[REDACTED_PW]');
  });

  test('NAVER_ID/NAVER_PW 미설정 시 정상 동작 (오류 없음)', () => {
    delete process.env.NAVER_ID;
    delete process.env.NAVER_PW;
    const result = sanitizeLogPayload({ foo: 'bar', count: 42 });
    expect(result.foo).toBe('bar');
    expect(result.count).toBe(42);
  });

  test('쿠키 값 필드(cookie_value)는 [REDACTED]로 치환된다', () => {
    const result = sanitizeLogPayload({ cookie_value: 'some_session_cookie' });
    expect((result as any).cookie_value).toBe('[REDACTED]');
  });

  test('쿠키 키 이름은 허용된다', () => {
    const result = sanitizeLogPayload({ cookie_name: 'NID_AUT', some_key: 'safe_value' });
    expect((result as any).cookie_name).toBe('NID_AUT');
    expect((result as any).some_key).toBe('safe_value');
  });
});

// ────────────────────────────────────────────────────────────────────
// Test 3: getRunContext
// ────────────────────────────────────────────────────────────────────
describe('getRunContext', () => {
  afterEach(() => {
    delete process.env.NAVER_RUN_ID;
    delete process.env.NAVER_JOB_KEY;
  });

  test('NAVER_RUN_ID가 설정된 경우 run_id에 포함된다', () => {
    process.env.NAVER_RUN_ID = 'my-run-id';
    const ctx = getRunContext();
    expect(ctx.run_id).toBe('my-run-id');
  });

  test('NAVER_RUN_ID 미설정 시 run_id는 "none"이다', () => {
    delete process.env.NAVER_RUN_ID;
    const ctx = getRunContext();
    expect(ctx.run_id).toBe('none');
  });

  test('NAVER_JOB_KEY 설정 시 job_id가 포함된다', () => {
    process.env.NAVER_RUN_ID = 'r1';
    process.env.NAVER_JOB_KEY = 'j1';
    const ctx = getRunContext();
    expect(ctx.job_id).toBe('j1');
  });

  test('NAVER_JOB_KEY 미설정 시 job_id가 없다', () => {
    process.env.NAVER_RUN_ID = 'r1';
    delete process.env.NAVER_JOB_KEY;
    const ctx = getRunContext();
    expect(ctx.job_id).toBeUndefined();
  });
});

// ────────────────────────────────────────────────────────────────────
// Test 4: 아티팩트 경로 생성
// ────────────────────────────────────────────────────────────────────
describe('getRunArtifactDir', () => {
  afterEach(() => {
    delete process.env.NAVER_RUN_ID;
  });

  test('run_id/stage 기반 경로가 예상 패턴으로 생성된다', () => {
    process.env.NAVER_RUN_ID = 'run-abc';
    const now = new Date('2026-02-22T10:00:00Z');
    const dir = getRunArtifactDir('EDITOR_READY', now);
    expect(dir).toMatch(/logs[/\\]20260222[/\\]run_run-abc[/\\]EDITOR_READY$/);
    expect(fs.existsSync(dir)).toBe(true);
    // 정리
    fs.rmSync(path.resolve('logs', '20260222'), { recursive: true, force: true });
  });

  test('NAVER_RUN_ID 미설정 시 norun이 사용된다', () => {
    delete process.env.NAVER_RUN_ID;
    const now = new Date('2026-02-22T10:00:00Z');
    const dir = getRunArtifactDir('SESSION_INIT', now);
    expect(dir).toMatch(/run_norun/);
    expect(fs.existsSync(dir)).toBe(true);
    fs.rmSync(path.resolve('logs', '20260222'), { recursive: true, force: true });
  });
});
