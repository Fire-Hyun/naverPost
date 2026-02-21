import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { createDebugRunDir } from '../../src/common/debug_paths';
import { getDateKey } from '../../src/common/logger';
import { TempSaveVerifier } from '../../src/naver/temp_save_verifier';
import { runDraftStage } from '../../src/naver/temp_save_state_machine';

describe('temp save timeout regression', () => {
  test('stage 타임박스: never-resolve waiter도 제한 시간 내 종료 + reason_code + debugPath', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'temp-save-timeout-'));
    const debugPath = path.join(root, 'debug-artifact');
    const startedAt = Date.now();
    const result = await runDraftStage(
      'clickTempSave',
      150,
      () => undefined,
      async () => await new Promise<boolean>(() => undefined),
      {
        timeoutReasonCode: 'STAGE_TIMEOUT_TEMP_SAVE',
        onTimeout: async () => {
          fs.mkdirSync(debugPath, { recursive: true });
          return debugPath;
        },
      },
    );

    expect(result.success).toBe(false);
    expect(result.timedOut).toBe(true);
    expect(result.reason_code).toBe('STAGE_TIMEOUT_TEMP_SAVE');
    expect(fs.existsSync(result.debug_path || '')).toBe(true);
    expect(Date.now() - startedAt).toBeLessThan(800);
  });

  test('debugPath 생성: cwd 변경에도 logs/<yyyyMMdd>/navertimeoutdebug/<timestamp> 사용', () => {
    const cwd = process.cwd();
    const tempCwd = fs.mkdtempSync(path.join(os.tmpdir(), 'temp-save-cwd-'));
    process.chdir(tempCwd);
    try {
      const created = createDebugRunDir('navertimeoutdebug');
      const expectedRoot = path.join(tempCwd, 'logs', getDateKey(), 'navertimeoutdebug');
      expect(created.startsWith(expectedRoot)).toBe(true);
      expect(created.includes('naver-poster/logs')).toBe(false);
      expect(fs.existsSync(created)).toBe(true);
    } finally {
      process.chdir(cwd);
    }
  });

  test('verifyDraftPersisted 타임박스: selector 미검출/무응답 시 DRAFT_VERIFY_TIMEOUT으로 종료', async () => {
    const verifier = new TempSaveVerifier(
      {
        page: {
          waitForTimeout: async () => undefined,
          screenshot: async ({ path: target }: { path: string }) => {
            fs.writeFileSync(target, 'screenshot');
          },
          url: () => 'https://blog.naver.com/jun12310?Redirect=Write&',
        } as any,
        frame: {} as any,
      },
      './artifacts',
      '테스트 제목',
      { verifyTimeoutMs: 120 },
    ) as any;

    verifier.verifyToastMessage = async () => ({ success: false });
    verifier.verifyDraftPersisted = async () => await new Promise(() => undefined);

    const result = await verifier.verifyTempSave();
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('DRAFT_VERIFY_TIMEOUT');
    expect(typeof result.debug_path).toBe('string');
    expect(fs.existsSync(result.debug_path)).toBe(true);
    expect(String(result.debug_path)).toContain(path.join('logs', getDateKey(), 'navertimeoutdebug'));
  });
});
