import {
  buildVerificationAnchors,
  evaluateVerificationAgainstObserved,
  normalizeForVerification,
  splitIntoChunks,
} from '../../src/naver/editor';

describe('10:29 block2 verification regression', () => {
  test('normalizeForVerification strips quote markers and control chars', () => {
    const raw = '[[QUOTE2:첫 방문기]]\n**강조**\u200B 본문';
    const normalized = normalizeForVerification(raw);
    expect(normalized).toContain('강조');
    expect(normalized).not.toContain('[[QUOTE2');
  });

  test('anchor verification passes when 2/3 anchors match', () => {
    const expected = '제목 다음 본문 첫 문장입니다. '.repeat(40);
    const observed = `불필요 머리글 ${expected.slice(0, 80)} ... 중간 변형 ... ${expected.slice(expected.length - 80)}`;
    const result = evaluateVerificationAgainstObserved(expected, observed);
    expect(result.ok).toBe(true);
    expect(result.matchedAnchors).toBeGreaterThanOrEqual(2);
  });

  test('long text chunking supports >1500 chars with bounded chunk size', () => {
    const longText = Array.from({ length: 140 }, (_, i) => `line-${i} 본문 문장입니다.`).join('\n');
    const chunks = splitIntoChunks(longText, 360);
    expect(longText.length).toBeGreaterThan(1500);
    expect(chunks.length).toBeGreaterThan(3);
    expect(chunks.every((chunk) => chunk.length <= 360)).toBe(true);
  });

  test('anchors are generated from normalized text', () => {
    const anchors = buildVerificationAnchors('[[QUOTE2:소제목]]\n본문 첫줄\n본문 끝줄');
    expect(anchors.start.length).toBeGreaterThan(0);
    expect(anchors.middle.length).toBeGreaterThan(0);
    expect(anchors.end.length).toBeGreaterThan(0);
  });
});
