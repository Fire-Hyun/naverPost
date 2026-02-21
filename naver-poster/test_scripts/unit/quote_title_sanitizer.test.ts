import { sanitizeQuoteTitle } from '../../src/utils/quote_title_sanitizer';

describe('quote title sanitizer', () => {
  test('본문이 붙은 멀티라인 입력에서 첫 줄 소제목만 남긴다', () => {
    const raw = '주차정보\n주차는 공영주차장 이용이 편했습니다.';
    expect(sanitizeQuoteTitle(raw)).toBe('주차정보');
  });

  test('문장형 긴 텍스트는 기본 소제목으로 강등한다', () => {
    const raw = '여기는 정말 좋았고 다음에 또 오고 싶다는 생각이 들었습니다.';
    expect(sanitizeQuoteTitle(raw, '방문후기')).toBe('방문후기');
  });
});

