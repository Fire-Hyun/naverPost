import { interleaveSection, splitSentences } from '../../src/utils/section_interleave';

describe('section interleave', () => {
  test('문장 12개 + 이미지 4장에서 텍스트 chunk는 1~5문장을 지킨다', () => {
    const text = Array.from({ length: 12 }, (_, i) => `문장${i + 1}.`).join(' ');
    const section = { title: '방문기/요약', paragraphs: [text] };
    const items = interleaveSection(section, [1, 2, 3, 4]);
    const textItems = items.filter((x) => x.type === 'text');
    expect(textItems.length).toBeGreaterThan(0);
    for (const item of textItems) {
      const sentenceCount = splitSentences(item.content).length;
      expect(sentenceCount).toBeGreaterThanOrEqual(1);
      expect(sentenceCount).toBeLessThanOrEqual(5);
    }
  });

  test('문장 2개 + 이미지 5장도 연속 이미지 없이 처리한다', () => {
    const section = { title: '객실/뷰', paragraphs: ['객실이 넓다. 뷰가 좋다.'] };
    const items = interleaveSection(section, [1, 2, 3, 4, 5], { avoidConsecutiveImages: true });
    const imageItems = items.filter((x) => x.type === 'image');
    expect(imageItems).toHaveLength(5);

    for (let i = 1; i < items.length; i++) {
      const prev = items[i - 1];
      const curr = items[i];
      expect(!(prev.type === 'image' && curr.type === 'image')).toBe(true);
    }
  });

  test('T4: 이미지 2장 이상이면 image->text 패턴으로 배치된다(텍스트 바로 위)', () => {
    const section = {
      title: '조식/편의',
      paragraphs: ['조식이 다양하다. 커피가 맛있다. 라운지가 조용하다.'],
    };
    const items = interleaveSection(section, [1, 2]);
    let foundPattern = false;
    for (let i = 0; i < items.length - 1; i++) {
      if (items[i].type === 'image' && items[i + 1].type === 'text') {
        foundPattern = true;
      }
    }
    expect(foundPattern).toBe(true);
  });
});
