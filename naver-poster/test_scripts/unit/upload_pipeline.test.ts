import { UploadPipeline, UploadState } from '../../src/naver/upload_pipeline';

describe('upload pipeline state machine', () => {
  const stateTimeoutMs = {
    [UploadState.INIT]: 100,
    [UploadState.OPEN_EDITOR]: 100,
    [UploadState.WRITE_CONTENT]: 100,
    [UploadState.CLICK_SAVE]: 100,
    [UploadState.WAIT_SAVE]: 150,
    [UploadState.RECOVERY]: 100,
  };

  test('INIT -> OPEN_EDITOR -> WRITE_CONTENT -> CLICK_SAVE -> WAIT_SAVE -> SUCCESS', async () => {
    const pipeline = new UploadPipeline(
      {
        openEditor: async () => ({ ok: true }),
        writeContent: async () => ({ ok: true }),
        clickSave: async () => ({ ok: true }),
        waitSave: async () => ({ success: true, timeout: false, sessionBlocked: false }),
        recover: async () => ({ ok: true }),
      },
      { maxRecoveryCount: 1, stateTimeoutMs },
    );

    const result = await pipeline.run();
    expect(result.success).toBe(true);
    expect(result.history).toEqual([
      UploadState.INIT,
      UploadState.OPEN_EDITOR,
      UploadState.WRITE_CONTENT,
      UploadState.CLICK_SAVE,
      UploadState.WAIT_SAVE,
      UploadState.SUCCESS,
    ]);
  });

  test('WAIT_SAVE timeout -> RECOVERY -> SUCCESS', async () => {
    let waits = 0;
    const pipeline = new UploadPipeline(
      {
        openEditor: async () => ({ ok: true }),
        writeContent: async () => ({ ok: true }),
        clickSave: async () => ({ ok: true }),
        waitSave: async () => {
          waits += 1;
          if (waits === 1) return { success: false, timeout: true, sessionBlocked: false };
          return { success: true, timeout: false, sessionBlocked: false };
        },
        recover: async () => ({ ok: true }),
      },
      { maxRecoveryCount: 1, stateTimeoutMs },
    );

    const result = await pipeline.run();
    expect(result.success).toBe(true);
    expect(result.recoveryCount).toBe(1);
    expect(result.history).toContain(UploadState.RECOVERY);
  });

  test('WAIT_SAVE timeout -> RECOVERY -> FAILED', async () => {
    const pipeline = new UploadPipeline(
      {
        openEditor: async () => ({ ok: true }),
        writeContent: async () => ({ ok: true }),
        clickSave: async () => ({ ok: true }),
        waitSave: async () => ({ success: false, timeout: true, sessionBlocked: false }),
        recover: async () => ({ ok: false, reason: 'cannot_recover' }),
      },
      { maxRecoveryCount: 1, stateTimeoutMs },
    );

    const result = await pipeline.run();
    expect(result.success).toBe(false);
    expect(result.state).toBe(UploadState.FAILED);
    expect(result.failureReason).toBe('cannot_recover');
    expect(result.recoveryCount).toBe(1);
  });

  test('all signal false/hang path must finish within time budget', async () => {
    const started = Date.now();
    const pipeline = new UploadPipeline(
      {
        openEditor: async () => ({ ok: true }),
        writeContent: async () => ({ ok: true }),
        clickSave: async () => ({ ok: true }),
        waitSave: async () => new Promise((resolve) => setTimeout(() => resolve({ success: false, timeout: true, sessionBlocked: false }), 5000)),
        recover: async () => ({ ok: false, reason: 'timeout_recover' }),
      },
      {
        maxRecoveryCount: 1,
        stateTimeoutMs: {
          ...stateTimeoutMs,
          [UploadState.WAIT_SAVE]: 120,
        },
      },
    );

    const result = await pipeline.run();
    const elapsed = Date.now() - started;
    expect(result.success).toBe(false);
    expect(elapsed).toBeLessThanOrEqual(Math.floor(120 * 1.1) + 50);
  });
});
