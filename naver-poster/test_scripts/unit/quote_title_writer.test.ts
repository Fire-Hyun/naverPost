import { writeSectionTitleAsQuote2, type QuoteTitleAdapter } from '../../src/naver/quote_title_writer';
import { QuoteBlockCreateError } from '../../src/naver/quote_block_creator';

class FakeQuoteAdapter implements QuoteTitleAdapter {
  private quotes: Array<{ type: 'quote1' | 'quote2'; text: string }> = [];
  private outsideTexts: string[] = [];
  private readonly makeQuote1: boolean;
  private readonly leakOutside: boolean;
  public lastWrittenTitle = '';

  constructor(options: { makeQuote1?: boolean; leakOutside?: boolean } = {}) {
    this.makeQuote1 = options.makeQuote1 ?? false;
    this.leakOutside = options.leakOutside ?? false;
  }

  async createQuote2Block(title: string): Promise<boolean> {
    this.quotes.push({ type: this.makeQuote1 ? 'quote1' : 'quote2', text: '' });
    const latest = this.quotes[this.quotes.length - 1];
    if (!latest) return false;
    this.lastWrittenTitle = title;
    latest.text = title;
    if (this.leakOutside) this.outsideTexts.push(title);
    return true;
  }

  async inspect(title: string) {
    return {
      emptyQuotes: this.quotes.filter((q) => !q.text.trim()).length,
      quote1Count: this.quotes.filter((q) => q.type === 'quote1').length,
      quote2Count: this.quotes.filter((q) => q.type === 'quote2').length,
      latestTitleInQuote: (this.quotes[this.quotes.length - 1]?.text || '').includes(title),
      titleOutsideQuote: this.outsideTexts.some((t) => t.includes(title)),
    };
  }

  async cleanupEmptyQuotes(): Promise<number> {
    const before = this.quotes.length;
    this.quotes = this.quotes.filter((q) => q.text.trim().length > 0);
    return before - this.quotes.length;
  }
}

describe('quote title writer', () => {
  test('T1: 소제목이 인용구2 내부에만 입력된다', async () => {
    const adapter = new FakeQuoteAdapter();
    const result = await writeSectionTitleAsQuote2(adapter, '"비용정보"');
    expect(result.success).toBe(true);
    expect(result.audit?.latestTitleInQuote).toBe(true);
    expect(result.audit?.titleOutsideQuote).toBe(false);
  });

  test('T2: 빈 인용구가 남지 않는다', async () => {
    const adapter = new FakeQuoteAdapter();
    await adapter.createQuote2Block(''); // empty quote
    const result = await writeSectionTitleAsQuote2(adapter, '"주차정보"');
    expect(result.success).toBe(true);
    expect(result.audit?.emptyQuotes).toBe(0);
  });

  test('T3: 인용구1이면 실패 처리된다', async () => {
    const adapter = new FakeQuoteAdapter({ makeQuote1: true });
    const result = await writeSectionTitleAsQuote2(adapter, '"위치/교통"');
    expect(result.success).toBe(false);
    expect(result.reason).toBe('quote1_detected');
  });

  test('T4: 소제목+본문 입력이어도 소제목 한 줄만 인용구에 기록된다', async () => {
    const adapter = new FakeQuoteAdapter();
    const result = await writeSectionTitleAsQuote2(adapter, '"주차정보\n주차는 공영주차장..."');
    expect(result.success).toBe(true);
    expect(adapter.lastWrittenTitle).toBe('주차정보');
  });

  test('T5: quote 탈출 실패 시 실패 처리된다', async () => {
    const adapter: QuoteTitleAdapter = {
      createQuote2Block: async (_title: string) => true,
      inspect: async () => ({
        emptyQuotes: 0,
        quote1Count: 0,
        quote2Count: 1,
        latestTitleInQuote: true,
        titleOutsideQuote: false,
      }),
      cleanupEmptyQuotes: async () => 0,
      escapeQuoteBlock: async () => false,
    };
    const result = await writeSectionTitleAsQuote2(adapter, '"첫 방문기"');
    expect(result.success).toBe(false);
    expect(result.reason).toBe('quote_escape_failed');
  });

  test('T6: quote2 블록 생성 실패 시 QuoteBlockCreateError가 발생한다', async () => {
    const adapter: QuoteTitleAdapter = {
      createQuote2Block: async (_title: string) => false,
      inspect: async () => ({
        emptyQuotes: 0,
        quote1Count: 0,
        quote2Count: 1,
        latestTitleInQuote: true,
        titleOutsideQuote: false,
      }),
      cleanupEmptyQuotes: async () => 0,
    };

    await expect(writeSectionTitleAsQuote2(adapter, '"첫 방문기"')).rejects.toBeInstanceOf(QuoteBlockCreateError);
  });
});
