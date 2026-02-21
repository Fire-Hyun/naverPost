import { writeSectionTitleAsQuote2, type QuoteTitleAdapter } from '../../src/naver/quote_title_writer';
import { QUOTE2_KEYBOARD_EXIT_SEQUENCE } from '../../src/naver/editor';

describe('editor quote2 smoke', () => {
  test('quote2 블록 생성 후 제목 입력 성공', async () => {
    let written = '';
    const adapter: QuoteTitleAdapter = {
      createQuote2Block: async (title: string) => {
        written = title;
        return true;
      },
      inspect: async () => ({
        emptyQuotes: 0,
        quote1Count: 0,
        quote2Count: 1,
        latestTitleInQuote: true,
        titleOutsideQuote: false,
      }),
      cleanupEmptyQuotes: async () => 0,
    };
    const result = await writeSectionTitleAsQuote2(adapter, '"주차정보"');
    expect(result.success).toBe(true);
    expect(written).toBe('주차정보');
  });

  test('quote2 제목 입력 시 본문이 딸려와도 첫 줄만 유지', async () => {
    let written = '';
    const adapter: QuoteTitleAdapter = {
      createQuote2Block: async (title: string) => {
        written = title;
        return true;
      },
      inspect: async () => ({
        emptyQuotes: 0,
        quote1Count: 0,
        quote2Count: 1,
        latestTitleInQuote: true,
        titleOutsideQuote: false,
      }),
      cleanupEmptyQuotes: async () => 0,
    };
    const result = await writeSectionTitleAsQuote2(adapter, '"방문후기\n본문이 들어가면 안 됩니다."');
    expect(result.success).toBe(true);
    expect(written).toBe('방문후기');
  });

  test('quote2 종료 키보드 시퀀스는 ↓ ↓ Enter 순서여야 한다', () => {
    expect(QUOTE2_KEYBOARD_EXIT_SEQUENCE).toEqual(['ArrowDown', 'ArrowDown', 'Enter']);
  });
});
