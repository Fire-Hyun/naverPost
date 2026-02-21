import { normalizeForVerification, splitIntoChunks } from '../../src/naver/editor';

describe('block writer guards', () => {
  test('긴 텍스트는 chunking으로 분할된다', () => {
    const longText = `${'가'.repeat(700)}\n${'나'.repeat(700)}`;
    const chunks = splitIntoChunks(longText, 300);
    expect(chunks.length).toBeGreaterThan(3);
    expect(chunks.every((c) => c.length <= 300)).toBe(true);
  });

  test('verification normalize는 공백/개행 차이를 흡수한다', () => {
    const raw = 'A  B\n\nC\r\nD';
    expect(normalizeForVerification(raw)).toBe('A BCD');
  });
});
