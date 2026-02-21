/**
 * T1: headless 결정 우선순위 테스트
 * T2: CAPTCHA fallback 플로우 테스트
 * T3: 세션 없으면 업로드 진입 금지 테스트
 */

import * as fs from 'fs';
import * as path from 'path';
import { backupInvalidStorageState } from '../../src/naver/session';
import { WorkerService, WorkerConfig } from '../../src/worker/worker_service';
import { WorkerJob, SessionValidationResult, FailureReasonCode } from '../../src/worker/types';

// ────────────────────────────────────────────────────────────────
// T1: headless 결정 우선순위 테스트 (코드 정적 분석 기반)
// ────────────────────────────────────────────────────────────────
describe('T1: headless 결정 우선순위', () => {
  test('session.ts: HEADLESS !== "false" 이면 headless=true (기본값)', () => {
    const sessionSrc = fs.readFileSync(
      path.resolve(__dirname, '../../src/naver/session.ts'),
      'utf-8',
    );
    // 최종 결정 로직 존재 확인
    expect(sessionSrc).toContain('opts.headless ?? (process.env.HEADLESS !== \'false\')');
  });

  test('post_to_naver.ts: getConfig()에서 HEADLESS 기본값이 true임을 확인', () => {
    const cliSrc = fs.readFileSync(
      path.resolve(__dirname, '../../src/cli/post_to_naver.ts'),
      'utf-8',
    );
    // getConfig() 내 headless 결정 로직
    expect(cliSrc).toContain("headless: process.env.HEADLESS !== 'false'");
  });

  test('worker.ts: headless=true 강제 설정', () => {
    const workerSrc = fs.readFileSync(
      path.resolve(__dirname, '../../src/cli/worker.ts'),
      'utf-8',
    );
    expect(workerSrc).toContain("process.env.HEADLESS = 'true'");
    expect(workerSrc).toContain('headless: true');
  });

  test('worker_service.ts: defaultUploadExecutorFactory에서 HEADLESS=true 강제 주입', () => {
    const serviceSrc = fs.readFileSync(
      path.resolve(__dirname, '../../src/worker/worker_service.ts'),
      'utf-8',
    );
    expect(serviceSrc).toContain("HEADLESS: 'true'");
    expect(serviceSrc).toContain("'--headless'");
  });

  test('worker_service.ts: interactiveLogin fallback은 HEADLESS=false로 실행', () => {
    const serviceSrc = fs.readFileSync(
      path.resolve(__dirname, '../../src/worker/worker_service.ts'),
      'utf-8',
    );
    expect(serviceSrc).toContain("HEADLESS: 'false'");
    expect(serviceSrc).toContain('--interactiveLogin');
  });
});

// ────────────────────────────────────────────────────────────────
// T2: CAPTCHA fallback 플로우 테스트 (mock deps)
// ────────────────────────────────────────────────────────────────

function makeJob(overrides: Partial<WorkerJob> = {}): WorkerJob {
  return {
    id: 'test-job-1',
    status: 'PROCESSING',
    mode: 'draft',
    dirPath: '/tmp/test-dir',
    chatId: 'chat-123',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    attempts: 0,
    ...overrides,
  };
}

type MockDeps = {
  executeUploadJob: jest.Mock;
  validateSession: jest.Mock;
  notifyAdmin: jest.Mock;
  notifyUser: jest.Mock;
};

function makeMockDeps(overrides: Partial<MockDeps> = {}): MockDeps {
  return {
    executeUploadJob: jest.fn().mockResolvedValue({ ok: true, detail: 'ok', stdout: '', stderr: '' }),
    validateSession: jest.fn().mockResolvedValue({ ok: true, detail: 'ok' } as SessionValidationResult),
    notifyAdmin: jest.fn().mockResolvedValue(undefined),
    notifyUser: jest.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

const baseConfig: WorkerConfig = {
  pollSec: 1,
  headless: true,
  resume: false,
};

describe('T2: CAPTCHA fallback 플로우', () => {
  test('1차 CAPTCHA, DISPLAY 없음 → fallback 실패 → BLOCKED_LOGIN + CAPTCHA 안내 메시지', async () => {
    const captchaResult = {
      ok: false,
      reasonCode: 'SECURITY_CHALLENGE' as FailureReasonCode,
      detail: 'CAPTCHA_DETECTED',
      stdout: 'CAPTCHA_DETECTED',
      stderr: '',
    };
    const deps = makeMockDeps({
      executeUploadJob: jest.fn().mockResolvedValue(captchaResult),
    });

    // DISPLAY를 일시 제거하여 attemptInteractiveLoginFallback이 즉시 false 반환
    const savedDisplay = process.env.DISPLAY;
    delete process.env.DISPLAY;
    try {
      const tmpQueue = path.resolve('/tmp', `test_queue_${Date.now()}.json`);
      fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [makeJob({ status: 'PENDING' })] }, null, 2));

      const service = new WorkerService({ ...baseConfig, queuePath: tmpQueue }, deps);
      await service.processNextJob();

      // notifyUser가 CAPTCHA 관련 메시지를 포함하여 호출되어야 함
      expect(deps.notifyUser).toHaveBeenCalledWith(
        'chat-123',
        expect.stringContaining('CAPTCHA'),
      );
      // BLOCKED_LOGIN이므로 notifyAdmin도 호출되어야 함
      expect(deps.notifyAdmin).toHaveBeenCalled();
      fs.rmSync(tmpQueue, { force: true });
    } finally {
      if (savedDisplay !== undefined) process.env.DISPLAY = savedDisplay;
    }
  });

  test('captchaFallbackAttempted=true인 job이 또 CAPTCHA면 BLOCKED_LOGIN 처리 (무한 루프 방지)', async () => {
    const captchaResult = {
      ok: false,
      reasonCode: 'SECURITY_CHALLENGE' as FailureReasonCode,
      detail: 'CAPTCHA_DETECTED',
      stdout: 'CAPTCHA_DETECTED',
      stderr: '',
    };
    const deps = makeMockDeps({
      executeUploadJob: jest.fn().mockResolvedValue(captchaResult),
    });

    const tmpQueue = path.resolve('/tmp', `test_queue_${Date.now()}.json`);
    const jobWithFallback = makeJob({ status: 'PENDING', captchaFallbackAttempted: true });
    fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [jobWithFallback] }, null, 2));

    const service = new WorkerService({ ...baseConfig, queuePath: tmpQueue }, deps);
    await service.processNextJob();

    // 무한 루프 방지: "CAPTCHA 반복" 메시지가 전송되어야 함
    expect(deps.notifyUser).toHaveBeenCalledWith(
      'chat-123',
      expect.stringContaining('CAPTCHA 반복'),
    );
    // notifyAdmin도 BLOCKED_LOGIN 안내 전송 확인
    expect(deps.notifyAdmin).toHaveBeenCalled();
    fs.rmSync(tmpQueue, { force: true });
  });

  test('CAPTCHA fallback 없이 성공하면 notifyUser에 성공 메시지', async () => {
    const deps = makeMockDeps({
      executeUploadJob: jest.fn().mockResolvedValue({
        ok: true, detail: 'ok', stdout: 'success', stderr: '',
        requestId: 'req-1', accountId: 'acc-1',
      }),
    });

    const tmpQueue = path.resolve('/tmp', `test_queue_${Date.now()}.json`);
    fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [makeJob({ status: 'PENDING' })] }, null, 2));

    const service = new WorkerService({ ...baseConfig, queuePath: tmpQueue }, deps);
    await service.processNextJob();

    expect(deps.notifyUser).toHaveBeenCalledWith(
      'chat-123',
      expect.stringContaining('업로드 성공'),
    );
    fs.rmSync(tmpQueue, { force: true });
  });
});

// ────────────────────────────────────────────────────────────────
// T3: 세션 없으면 업로드 진입 금지 테스트
// ────────────────────────────────────────────────────────────────
describe('T3: 세션 검증 실패 시 업로드 진입 금지', () => {
  test('validateSession이 SESSION_EXPIRED이면 executeUploadJob이 호출되지 않음', async () => {
    const deps = makeMockDeps({
      validateSession: jest.fn().mockResolvedValue({
        ok: false,
        reasonCode: 'SESSION_EXPIRED' as FailureReasonCode,
        detail: '세션 만료',
      } as SessionValidationResult),
    });

    const tmpQueue = path.resolve('/tmp', `test_queue_${Date.now()}.json`);
    fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [makeJob({ status: 'PENDING' })] }, null, 2));

    const service = new WorkerService({ ...baseConfig, queuePath: tmpQueue }, deps);
    await service.processNextJob();

    // 세션이 없으면 업로드(executeUploadJob)가 절대 호출되면 안 됨
    expect(deps.executeUploadJob).not.toHaveBeenCalled();
    // BLOCKED_LOGIN 안내가 전송되어야 함
    expect(deps.notifyAdmin).toHaveBeenCalled();
    fs.rmSync(tmpQueue, { force: true });
  });

  test('validateSession이 SECURITY_CHALLENGE이면 executeUploadJob이 호출되지 않음', async () => {
    const deps = makeMockDeps({
      validateSession: jest.fn().mockResolvedValue({
        ok: false,
        reasonCode: 'SECURITY_CHALLENGE' as FailureReasonCode,
        detail: 'CAPTCHA',
      } as SessionValidationResult),
    });

    const tmpQueue = path.resolve('/tmp', `test_queue_${Date.now()}.json`);
    fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [makeJob({ status: 'PENDING' })] }, null, 2));

    const service = new WorkerService({ ...baseConfig, queuePath: tmpQueue }, deps);
    await service.processNextJob();

    expect(deps.executeUploadJob).not.toHaveBeenCalled();
    expect(deps.notifyAdmin).toHaveBeenCalled();
    fs.rmSync(tmpQueue, { force: true });
  });

  test('validateSession이 성공이면 executeUploadJob이 호출됨', async () => {
    const deps = makeMockDeps();

    const tmpQueue = path.resolve('/tmp', `test_queue_${Date.now()}.json`);
    fs.writeFileSync(tmpQueue, JSON.stringify({ version: 1, jobs: [makeJob({ status: 'PENDING' })] }, null, 2));

    const service = new WorkerService({ ...baseConfig, queuePath: tmpQueue }, deps);
    await service.processNextJob();

    expect(deps.executeUploadJob).toHaveBeenCalledTimes(1);
    fs.rmSync(tmpQueue, { force: true });
  });
});

// ────────────────────────────────────────────────────────────────
// backupInvalidStorageState 단위 테스트
// ────────────────────────────────────────────────────────────────
describe('backupInvalidStorageState', () => {
  test('파일이 없으면 null 반환', () => {
    const result = backupInvalidStorageState('/tmp/nonexistent_storage_state.json');
    expect(result).toBeNull();
  });

  test('파일이 있으면 .invalid.<ts>.json으로 이름 변경 후 경로 반환', () => {
    const tmpFile = path.resolve('/tmp', `test_session_storage_${Date.now()}.json`);
    fs.writeFileSync(tmpFile, JSON.stringify({ cookies: [] }));

    const result = backupInvalidStorageState(tmpFile);
    expect(result).not.toBeNull();
    expect(result).toMatch(/\.invalid\.\d{4}-\d{2}-\d{2}T.*\.json$/);
    expect(fs.existsSync(tmpFile)).toBe(false);
    expect(fs.existsSync(result!)).toBe(true);

    // 정리
    fs.rmSync(result!, { force: true });
  });
});
