import { enforceOutlineAndConclusionRules } from '../../src/utils/outline_validator';
import type { TopicSection } from '../../src/utils/topic_organizer';

describe('outline validator', () => {
  test('결론 섹션을 항상 마지막으로 강제하고 조기 결론 문단을 이동한다', () => {
    const sections: TopicSection[] = [
      { title: '방문후기', paragraphs: ['동선이 좋아서 편했습니다.', '다음에 만나요!'] },
      { title: '주차정보', paragraphs: ['주차장은 지하에 있습니다.'] },
      { title: '서론', paragraphs: ['여행 동기 요약입니다.'] },
    ];

    const fixed = enforceOutlineAndConclusionRules(sections);
    expect(fixed.sections[0].title).toBe('서론');
    expect(fixed.sections[fixed.sections.length - 1].title).toBe('총평');
    expect(fixed.sections[fixed.sections.length - 1].paragraphs.at(-1)).toBe('다음에 만나요!');
    const joinedBody = fixed.sections
      .filter((s) => s.title !== '총평')
      .map((s) => s.paragraphs.join(' '))
      .join(' ');
    expect(joinedBody.includes('다음에 만나요')).toBe(false);
    expect(fixed.movedParagraphs).toBeGreaterThan(0);
  });
});

