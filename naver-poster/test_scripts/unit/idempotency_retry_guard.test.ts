import {
  computeMarkdownBodyHash,
  ensureRetryConsistency,
  IdempotencyError,
  type JobRunState,
} from '../../src/common/idempotency';

describe('idempotency retry guard', () => {
  test('B) Step G 실패 후 재시도 시 run_id/content_hash 불일치면 RUN_ID_MISMATCH_RETRY_BLOCKED', () => {
    const previous: JobRunState = {
      job_key: 'telegram:777',
      run_id: '20260221_120000_ab12cd',
      blog_result_path: '/tmp/post/blog_result.md',
      content_hash: computeMarkdownBodyHash('# 제목\n\n본문 A\n'),
      content_length: 8,
      image_count: 1,
      updated_at: '2026-02-21T12:00:00.000Z',
    };

    expect(() => ensureRetryConsistency({
      retryAttempt: 1,
      state: previous,
      runId: previous.run_id,
      contentHash: computeMarkdownBodyHash('# 제목\n\n본문 B\n'),
    })).toThrow(IdempotencyError);

    try {
      ensureRetryConsistency({
        retryAttempt: 1,
        state: previous,
        runId: previous.run_id,
        contentHash: computeMarkdownBodyHash('# 제목\n\n본문 B\n'),
      });
    } catch (error) {
      const typed = error as IdempotencyError;
      expect(typed.reasonCode).toBe('RUN_ID_MISMATCH_RETRY_BLOCKED');
    }
  });
});
