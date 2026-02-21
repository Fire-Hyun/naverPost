import { buildSemanticImageBlockSequence } from '../../src/utils/image_matcher';

describe('image matcher placement', () => {
  const blogText = [
    '# 인트로',
    '',
    '가게 위치와 첫인상 소개 문단입니다.',
    '',
    '메뉴와 맛 평가 문단입니다.',
    '',
    '마무리 총평 문단입니다.',
  ].join('\n');

  test('이미지 1장이 B003으로 매칭되면 B003 텍스트 위에 삽입', async () => {
    const result = await buildSemanticImageBlockSequence(blogText, ['/tmp/menu.jpg'], {
      matcher: async () => ({ blockId: 'B003', confidence: 0.91 }),
    });
    expect(result.placements).toHaveLength(1);
    expect(result.placements[0].chosenBlockId).toBe('B003');
    expect(result.placements[0].strategy).toBe('semantic');

    const firstImageIndex = result.blocks.findIndex((b) => b.type === 'image');
    const targetTextIndex = result.blocks.findIndex((b) => b.type === 'text' && b.content.includes('메뉴와 맛 평가'));
    expect(firstImageIndex).toBeGreaterThanOrEqual(0);
    expect(firstImageIndex).toBe(targetTextIndex - 1);
  });

  test('UNKNOWN 반환 시 이미지 첨부 순서대로 fallback 배치', async () => {
    const matcher = jest.fn(async () => ({ blockId: 'UNKNOWN' as const, confidence: 0 }));
    const result = await buildSemanticImageBlockSequence(blogText, ['/tmp/a.jpg', '/tmp/b.jpg'], { matcher });

    expect(result.placements[0].strategy).toBe('fallback');
    expect(result.placements[1].strategy).toBe('fallback');
    expect(result.placements[0].chosenBlockId).toBe('B001');
    expect(result.placements[1].chosenBlockId).toBe('B002');
  });

  test('confidence가 threshold 미만이면 fallback 적용', async () => {
    const result = await buildSemanticImageBlockSequence(blogText, ['/tmp/low.jpg'], {
      matcher: async () => ({ blockId: 'B003', confidence: 0.2 }),
      matchThreshold: 0.55,
    });

    expect(result.placements[0].strategy).toBe('fallback');
    expect(result.placements[0].chosenBlockId).toBe('B001');
  });
});
