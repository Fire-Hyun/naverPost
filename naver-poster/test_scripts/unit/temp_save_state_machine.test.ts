import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  computeInsertBlocksTimeoutSeconds,
  DraftProgressWatchdog,
  DraftStageTimeoutError,
  buildImageUploadPlan,
  isTempSaveSuccessSignal,
  normalizeBlockSequenceForDraft,
  runDraftStage,
} from '../../src/naver/temp_save_state_machine';

describe('temp_save_state_machine unit', () => {
  test('blocks: text only', () => {
    const input = [{ type: 'text', content: 'hello' }];
    const result = normalizeBlockSequenceForDraft(input);
    expect(result.syntheticTextInserted).toBe(false);
    expect(result.normalizedBlocks.length).toBe(1);
  });

  test('blocks: image only should inject synthetic text block', () => {
    const input = [{ type: 'image', index: 1 }];
    const result = normalizeBlockSequenceForDraft(input);
    expect(result.syntheticTextInserted).toBe(true);
    expect(result.normalizedBlocks[0].type).toBe('text');
    expect(result.normalizedBlocks.length).toBe(2);
  });

  test('long text > 2000 chars stays intact', () => {
    const text = '가'.repeat(2500);
    const input = [{ type: 'text', content: text }];
    const result = normalizeBlockSequenceForDraft(input);
    expect(result.syntheticTextInserted).toBe(false);
    expect((result.normalizedBlocks[0] as any).content.length).toBe(2500);
  });

  test('special chars + emoji success signal matcher', () => {
    expect(isTempSaveSuccessSignal('✅ 임시 저장 완료')).toBe(true);
    expect(isTempSaveSuccessSignal('자동저장 되었습니다 😀')).toBe(true);
    expect(isTempSaveSuccessSignal('[사진1] 저장 실패')).toBe(false);
  });

  test('image plan for 1/3/10 files and >5MB detection', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'draft-sm-'));
    const mk = (name: string, size: number) => {
      const p = path.join(dir, name);
      fs.writeFileSync(p, Buffer.alloc(size, 1));
      return p;
    };
    const files = [
      mk('a.jpg', 1000),
      mk('b.jpg', 6 * 1024 * 1024),
      mk('c.jpg', 2000),
    ];
    const plan3 = buildImageUploadPlan(files);
    expect(plan3.length).toBe(3);
    expect(plan3[1].tooLarge).toBe(true);

    const plan1 = buildImageUploadPlan([files[0]]);
    expect(plan1.length).toBe(1);

    const ten = Array.from({ length: 10 }, (_, i) => mk(`x${i}.jpg`, 1024));
    const plan10 = buildImageUploadPlan(ten);
    expect(plan10.length).toBe(10);
  });

  test('runDraftStage timeout', async () => {
    const result = await runDraftStage(
      'waitTempSaveSuccess',
      30,
      () => undefined,
      async () => {
        await new Promise((r) => setTimeout(r, 60));
        return true;
      },
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain('[STAGE_TIMEOUT]');
  });

  test('runDraftStage success', async () => {
    const result = await runDraftStage(
      'clickTempSave',
      500,
      () => undefined,
      async () => true,
    );
    expect(result.success).toBe(true);
    expect(result.data).toBe(true);
  });

  test('watchdog detects silence', async () => {
    let fired = false;
    const watchdog = new DraftProgressWatchdog(40, async () => {
      fired = true;
    });
    watchdog.start();
    await new Promise((r) => setTimeout(r, 90));
    watchdog.stop();
    expect(fired).toBe(true);
  });

  test('watchdog heartbeat prevents immediate fire', async () => {
    let fired = false;
    const watchdog = new DraftProgressWatchdog(120, async () => {
      fired = true;
    });
    watchdog.start();
    watchdog.heartbeat('insertBlocks');
    await new Promise((r) => setTimeout(r, 60));
    watchdog.stop();
    expect(fired).toBe(false);
  });

  test('iframe/login timeout error type', () => {
    const err = new DraftStageTimeoutError('ensureLoggedIn', 30000);
    expect(err.stage).toBe('ensureLoggedIn');
    expect(err.timeoutMs).toBe(30000);
  });

  test('insert-block timeout budget grows with image volume', () => {
    const light = computeInsertBlocksTimeoutSeconds([
      { type: 'text' },
      { type: 'image' },
    ]);
    const heavy = computeInsertBlocksTimeoutSeconds([
      { type: 'text' },
      { type: 'text' },
      { type: 'image' },
      { type: 'image' },
      { type: 'image' },
      { type: 'image' },
    ]);
    expect(light).toBeGreaterThanOrEqual(30);
    expect(heavy).toBeGreaterThan(light);
  });

  test('insert-block timeout budget clamps to min/max', () => {
    const minBudget = computeInsertBlocksTimeoutSeconds([], { fallbackSeconds: 10, minSeconds: 30, maxSeconds: 120 });
    expect(minBudget).toBe(30);

    const hugeBlocks = Array.from({ length: 100 }, () => ({ type: 'image' }));
    const maxBudget = computeInsertBlocksTimeoutSeconds(hugeBlocks, { maxSeconds: 120 });
    expect(maxBudget).toBe(120);
  });
});
