import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  acquireJobLock,
  releaseJobLock,
} from '../../src/common/idempotency';

describe('idempotency job lock', () => {
  const originalDir = process.env.NAVER_IDEMPOTENCY_DIR;

  afterEach(() => {
    if (originalDir === undefined) {
      delete process.env.NAVER_IDEMPOTENCY_DIR;
    } else {
      process.env.NAVER_IDEMPOTENCY_DIR = originalDir;
    }
  });

  test('A) 동일 job_key 2회 진입 시 2번째는 DUP_RUN_DETECTED', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'idempotency-lock-'));
    process.env.NAVER_IDEMPOTENCY_DIR = path.join(tmp, 'idempotency');

    const first = acquireJobLock('telegram:12345', 'run_1');
    expect(first.ok).toBe(true);
    if (!first.ok) return;

    const second = acquireJobLock('telegram:12345', 'run_2');
    expect(second.ok).toBe(false);
    if (!second.ok) {
      expect(second.reasonCode).toBe('DUP_RUN_DETECTED');
    }

    releaseJobLock(first.handle);
  });
});
