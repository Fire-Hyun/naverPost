import { placeImagesBySection } from '../../src/utils/image_placer';
import type { TopicSection } from '../../src/utils/topic_organizer';

describe('image placer', () => {
  const sections: TopicSection[] = [
    { title: '방문기/요약', paragraphs: ['첫인상 내용'] },
    { title: '주차정보', paragraphs: ['주차 동선 내용'] },
    { title: '비용정보', paragraphs: ['요금 정보'] },
  ];

  test('비전 매칭이 주차정보를 반환하면 해당 섹션에 배치된다', async () => {
    const placements = await placeImagesBySection(sections, ['/tmp/a.jpg'], {
      matcher: async () => ({ sectionTitle: '주차정보', confidence: 0.88 }),
      threshold: 0.55,
    });
    expect(placements[0].sectionIndex).toBe(1);
    expect(placements[0].mode).toBe('vision');
  });

  test('UNKNOWN 반환 시 fallback으로 순차 배치된다', async () => {
    const placements = await placeImagesBySection(sections, ['/tmp/a.jpg', '/tmp/b.jpg'], {
      matcher: async () => ({ sectionTitle: 'UNKNOWN', confidence: 0 }),
      threshold: 0.55,
    });
    expect(placements[0].mode).toBe('fallback');
    expect(placements[0].sectionIndex).toBe(0);
    expect(placements[1].sectionIndex).toBe(1);
  });

  test('1차 UNKNOWN이면 2차 에스컬레이션 matcher를 호출한다', async () => {
    const primary = jest.fn(async () => ({ sectionTitle: 'UNKNOWN' as const, confidence: 0.1 }));
    const secondary = jest.fn(async () => ({ sectionTitle: '비용정보', confidence: 0.82 }));
    const placements = await placeImagesBySection(sections, ['/tmp/a.jpg'], {
      matcher: primary,
      escalationMatcher: secondary,
      threshold: 0.55,
    });
    expect(primary).toHaveBeenCalledTimes(1);
    expect(secondary).toHaveBeenCalledTimes(1);
    expect(placements[0].mode).toBe('vision');
    expect(placements[0].sectionIndex).toBe(2);
  });

  test('1차 confidence가 낮으면 2차 에스컬레이션 matcher를 호출한다', async () => {
    const primary = jest.fn(async () => ({ sectionTitle: '주차정보', confidence: 0.3 }));
    const secondary = jest.fn(async () => ({ sectionTitle: '주차정보', confidence: 0.88 }));
    await placeImagesBySection(sections, ['/tmp/a.jpg'], {
      matcher: primary,
      escalationMatcher: secondary,
      threshold: 0.55,
    });
    expect(primary).toHaveBeenCalledTimes(1);
    expect(secondary).toHaveBeenCalledTimes(1);
  });

  test('1차 confidence가 충분하면 2차 에스컬레이션 matcher를 호출하지 않는다', async () => {
    const primary = jest.fn(async () => ({ sectionTitle: '주차정보', confidence: 0.92, scoreGap: 0.2 }));
    const secondary = jest.fn(async () => ({ sectionTitle: '비용정보', confidence: 0.2 }));
    const placements = await placeImagesBySection(sections, ['/tmp/a.jpg'], {
      matcher: primary,
      escalationMatcher: secondary,
      threshold: 0.55,
      minScoreGap: 0.12,
    });
    expect(primary).toHaveBeenCalledTimes(1);
    expect(secondary).toHaveBeenCalledTimes(0);
    expect(placements[0].sectionIndex).toBe(1);
  });

  test('T3: 비동기 분석 응답 순서가 뒤섞여도 imageIndex 기준으로 매핑된다', async () => {
    const previous = process.env.VISION_ESCALATION_ENABLED;
    process.env.VISION_ESCALATION_ENABLED = 'false';
    try {
      const matcher = jest.fn(async (imageSource: string) => {
        const name = imageSource.split('/').pop() || '';
        const delay = name === 'c.jpg' ? 5 : (name === 'b.jpg' ? 20 : 40);
        await new Promise((resolve) => setTimeout(resolve, delay));
        if (name === 'a.jpg') return { sectionTitle: '방문기/요약' as const, confidence: 0.9 };
        if (name === 'b.jpg') return { sectionTitle: '주차정보' as const, confidence: 0.9 };
        return { sectionTitle: '비용정보' as const, confidence: 0.9 };
      });
      const placements = await placeImagesBySection(sections, ['/tmp/a.jpg', '/tmp/b.jpg', '/tmp/c.jpg'], {
        matcher,
        threshold: 0.55,
      });
      expect(placements.map((p) => p.imageIndex)).toEqual([1, 2, 3]);
      expect(placements.map((p) => p.sectionIndex)).toEqual([0, 1, 2]);
      expect(placements.every((p) => p.mode === 'vision')).toBe(true);
    } finally {
      if (previous === undefined) {
        delete process.env.VISION_ESCALATION_ENABLED;
      } else {
        process.env.VISION_ESCALATION_ENABLED = previous;
      }
    }
  });
});
