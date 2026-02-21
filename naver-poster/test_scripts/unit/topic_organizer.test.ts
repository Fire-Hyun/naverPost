import { organizeTopics } from '../../src/utils/topic_organizer';

describe('topic organizer', () => {
  test('서론/본론/결론 구조를 만들고 결론을 마지막에 둔다', () => {
    const draftText = [
      '이번 여행에서 선택한 호텔은 위치가 좋아서 기대가 컸습니다.',
      '',
      '전체적으로 조용하고 깔끔해서 첫인상이 좋았습니다.',
      '',
      '주차장은 지하 2층까지 있고 발렛도 가능했습니다.',
      '',
      '총 비용은 1박 18만원이고 조식은 2만원 추가였습니다.',
      '',
      '다음에 만나요!',
    ].join('\n');

    const result = organizeTopics(draftText, { useDefaultOrder: true });
    expect(result.sections[0].title).toBe('서론');
    expect(result.sections[result.sections.length - 1].title).toBe('총평');
    expect(result.sections.some((s) => s.title === '주차정보')).toBe(true);
    expect(result.sections.some((s) => s.title === '비용정보')).toBe(true);
    expect(result.sections[result.sections.length - 1].paragraphs.at(-1)).toBe('다음에 만나요!');
  });

  test('중간 섹션의 조기 결론 문구를 결론 섹션으로 이동한다', () => {
    const draftText = [
      '방문 이유와 핵심 요약입니다.',
      '',
      '객실 뷰가 좋았습니다.',
      '',
      '마무리로 다음에 만나요! 라고 적고 싶었지만 아직 본문입니다.',
      '',
      '주차장은 무료였습니다.',
    ].join('\n');
    const result = organizeTopics(draftText, { useDefaultOrder: true });
    const conclusion = result.sections[result.sections.length - 1];
    expect(conclusion.title).toBe('총평');
    expect(conclusion.paragraphs.at(-1)).toBe('다음에 만나요!');
    const bodyText = result.sections
      .filter((s) => s.title !== '총평')
      .map((s) => s.paragraphs.join(' '))
      .join(' ');
    expect(bodyText.includes('다음에 만나요')).toBe(false);
  });

  test('결론 문구가 없어도 결론 섹션은 항상 마지막에 생성된다', () => {
    const draftText = [
      '출장 일정으로 호텔을 방문했습니다.',
      '',
      '객실은 조용했고 침구가 편했습니다.',
      '',
      '주차장은 넓어서 진입이 수월했습니다.',
    ].join('\n');
    const result = organizeTopics(draftText, { useDefaultOrder: true });
    const last = result.sections[result.sections.length - 1];
    expect(last.title).toBe('총평');
    expect(last.paragraphs.at(-1)).toBe('다음에 만나요!');
  });
});
