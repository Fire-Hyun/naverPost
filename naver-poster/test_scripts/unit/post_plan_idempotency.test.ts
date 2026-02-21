import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { parseBlogResult } from '../../src/utils/parser';
import {
  buildPostPlan,
  createPostPlanState,
  executePostPlanExactlyOnce,
  getImageId,
} from '../../src/utils/post_plan';

function makeTempDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'post-plan-test-'));
}

describe('post plan', () => {
  test('T1: blog_result.md 순서를 PostPlan.blocks가 그대로 유지한다', () => {
    const tmpDir = makeTempDir();
    try {
      const mdPath = path.join(tmpDir, 'blog_result.md');
      const content = [
        'TITLE: 순서 보장 테스트',
        '',
        '첫 문단',
        '',
        '[사진2]',
        '',
        '둘째 문단',
        '',
        '[사진1]',
        '',
        '마지막 문단',
      ].join('\n');
      fs.writeFileSync(mdPath, content, 'utf-8');
      const parsed = parseBlogResult(mdPath);
      const imagePaths = ['/tmp/first.jpg', '/tmp/second.jpg'];
      const plan = buildPostPlan(parsed.blocks, imagePaths);

      expect(plan.blocks.map((b) => b.type)).toEqual(parsed.blocks.map((b) => b.type));
      expect(plan.blocks.filter((b) => b.type === 'image').map((b) => b.imageIndex)).toEqual([2, 1]);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  test('T2: 중간 실패 후 재시도에서도 성공 블록은 정확히 1회만 처리된다', async () => {
    const plan = buildPostPlan(
      [
        { type: 'text', content: '첫 블록' },
        { type: 'image', index: 1, marker: '[사진1]' },
        { type: 'text', content: '마지막 블록' },
      ],
      ['/tmp/a.jpg'],
    );
    const state = createPostPlanState();
    const calls = new Map<string, number>();
    let failedOnce = false;

    const runner = jest.fn(async (block: { blockId: string; type: string }) => {
      calls.set(block.blockId, (calls.get(block.blockId) ?? 0) + 1);
      if (block.type === 'image' && !failedOnce) {
        failedOnce = true;
        throw new Error('transient');
      }
    });

    await expect(executePostPlanExactlyOnce(plan, state, runner)).rejects.toThrow('transient');
    await executePostPlanExactlyOnce(plan, state, runner);

    const firstBlockId = plan.blocks[0].blockId;
    const imageBlockId = plan.blocks[1].blockId;
    const lastBlockId = plan.blocks[2].blockId;
    expect(calls.get(firstBlockId)).toBe(1);
    expect(calls.get(imageBlockId)).toBe(2);
    expect(calls.get(lastBlockId)).toBe(1);
    expect(state.insertedBlockIds.has(firstBlockId)).toBe(true);
    expect(state.insertedBlockIds.has(imageBlockId)).toBe(true);
    expect(state.insertedBlockIds.has(lastBlockId)).toBe(true);
    expect(state.insertedImageIds.has(getImageId('/tmp/a.jpg', 1))).toBe(true);
  });
});
