import { launchContextWithRetry } from '../../src/naver/session';

describe('session launch retry guard', () => {
  test('첫 시도 실패 후 재시도에서 성공하면 반환한다', async () => {
    let attempts = 0;
    const context = { id: 'ctx' };
    const result = await launchContextWithRetry(
      async () => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error('launch timeout');
        }
        return context;
      },
      {
        maxRetries: 1,
        retryDelayMs: 1,
        stageName: 'browser_launch_and_session_load',
      },
    );

    expect(result).toBe(context);
    expect(attempts).toBe(2);
  });

  test('재시도까지 실패하면 원인 포함 에러를 던진다', async () => {
    await expect(
      launchContextWithRetry(
        async () => {
          throw new Error('browser did not start');
        },
        {
          maxRetries: 1,
          retryDelayMs: 1,
          stageName: 'browser_launch_and_session_load',
        },
      ),
    ).rejects.toThrow(
      '[BROWSER_LAUNCH_TIMEOUT] waitedFor=[launchPersistentContext]',
    );
  });
});

