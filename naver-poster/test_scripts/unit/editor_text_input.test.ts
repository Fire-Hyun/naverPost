import {
  buildDebugFixture,
  extractVerificationSample,
  sanitizeForEditor,
  splitIntoChunks,
  TextInputFailureReason,
} from '../../src/naver/editor';
import { PostBlock } from '../../src/utils/parser';

describe('editor text input fixtures', () => {
  test('case1 short text(200자) chunking/sanitizing', () => {
    const text = '가'.repeat(200);
    const sanitized = sanitizeForEditor(text);
    const chunks = splitIntoChunks(sanitized, 250);
    expect(chunks.length).toBe(1);
    expect(chunks[0].length).toBe(200);
    expect(extractVerificationSample(sanitized).length).toBeGreaterThanOrEqual(6);
  });

  test('case2 production-like text(약1200자) chunking', () => {
    const paragraph = '제주 맛집 후기 문단입니다. '.repeat(30);
    const text = Array.from({ length: 6 }, () => paragraph).join('\n\n');
    const sanitized = sanitizeForEditor(text);
    const chunks = splitIntoChunks(sanitized, 250);
    expect(sanitized.length).toBeGreaterThan(1100);
    expect(chunks.length).toBeGreaterThan(4);
    expect(chunks.every((c) => c.length <= 250)).toBe(true);
  });

  test('case3 special chars(따옴표/이모지/줄바꿈/사진마커) fixture payload', () => {
    const text = `\"따옴표\"와 😀 이모지\n둘째 줄 [사진1] 표기\n셋째 줄`;
    const sanitized = sanitizeForEditor(text);
    expect(sanitized.includes('😀')).toBe(true);
    expect(sanitized.includes('[사진1]')).toBe(true);

    const blocks: PostBlock[] = [
      { type: 'text', content: sanitized },
      { type: 'image', index: 1, marker: '[사진1]' },
    ];
    const fixture = buildDebugFixture(
      blocks,
      ['/tmp/mock/image1.jpg'],
      0,
      TextInputFailureReason.INPUT_NOT_REFLECTED,
    );
    expect(fixture.failed_block_index).toBe(0);
    expect(fixture.failure_reason).toBe(TextInputFailureReason.INPUT_NOT_REFLECTED);
    expect(fixture.blocks[0].content_length).toBeGreaterThan(0);
    expect(fixture.blocks[0].content).toContain('😀');
  });
});
