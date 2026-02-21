import { Browser, chromium, Page } from 'playwright';
import { writeSectionTitleAsQuote2, type QuoteTitleAdapter } from '../../src/naver/quote_title_writer';

describe('local editor fixture quote shift regression', () => {
  let browser: Browser;

  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
  });

  afterAll(async () => {
    await browser.close();
  });

  function makeAdapter(page: Page): QuoteTitleAdapter {
    return {
      createQuote2Block: async (title: string) => {
        return await page.evaluate(({ initialTitle }) => {
          const cfg = (window as any).__quote_cfg || {};
          if (cfg.selectorChanged) return false;
          const editor = document.querySelector('#editor') as HTMLElement | null;
          if (!editor) return false;
          const quote = document.createElement('div');
          if (cfg.makeQuote1) {
            quote.className = 'se-component-quotation quote1';
            quote.setAttribute('data-type', 'quote1');
          } else {
            quote.className = 'se-component-quotation quote2 vertical-line';
            quote.setAttribute('data-type', 'quote2');
          }
          const editable = document.createElement('div');
          editable.className = 'se-text-paragraph';
          editable.setAttribute('contenteditable', 'true');
          quote.appendChild(editable);
          editor.appendChild(quote);
          if (cfg.wrongFocus) {
            const outside = document.createElement('div');
            outside.className = 'se-paragraph';
            outside.setAttribute('contenteditable', 'true');
            outside.textContent = initialTitle;
            editor.appendChild(outside);
            outside.focus();
            return true;
          }
          editable.textContent = initialTitle;
          editable.focus();
          return true;
        }, { initialTitle: title });
      },
      inspect: async (title: string) => {
        return await page.evaluate((needle) => {
          const quoteNodes = Array.from(document.querySelectorAll<HTMLElement>('.se-component-quotation'));
          const latest = quoteNodes[quoteNodes.length - 1];
          const latestText = (latest?.innerText || '').trim();
          const outside = Array.from(document.querySelectorAll<HTMLElement>('#editor > .se-paragraph'))
            .map((el) => el.innerText || '')
            .join('\n');
          const quote1Count = quoteNodes.filter((q) => {
            const cls = `${q.className || ''} ${q.getAttribute('data-type') || ''}`.toLowerCase();
            return /(quote[-_ ]?1|quotation[-_ ]?1|type[-_ ]?1)/.test(cls);
          }).length;
          return {
            emptyQuotes: quoteNodes.filter((q) => !(q.innerText || '').trim()).length,
            quote1Count,
            quote2Count: quoteNodes.length,
            latestTitleInQuote: latestText.includes(needle),
            titleOutsideQuote: outside.includes(needle),
          };
        }, title);
      },
      cleanupEmptyQuotes: async () => 0,
      escapeQuoteBlock: async () => {
        return await page.evaluate(() => {
          const editor = document.querySelector('#editor') as HTMLElement | null;
          if (!editor) return false;
          const paragraph = document.createElement('div');
          paragraph.className = 'se-paragraph';
          paragraph.setAttribute('contenteditable', 'true');
          editor.appendChild(paragraph);
          paragraph.focus();
          return true;
        });
      },
      isCursorInsideQuote: async () => {
        return await page.evaluate(() => {
          const active = document.activeElement as HTMLElement | null;
          return !!active?.closest('.se-component-quotation');
        });
      },
    };
  }

  test('quote2에는 소제목만 들어가고 다음 본문은 quote 밖 문단에 들어간다', async () => {
    const page = await browser.newPage();
    await page.setContent('<html><body><div id="editor"></div></body></html>');

    await page.evaluate(() => {
      (window as any).__quote_cfg = {};
    });
    const result = await writeSectionTitleAsQuote2(makeAdapter(page), '첫 방문기');
    expect(result.success).toBe(true);

    await page.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      if (!active) return;
      active.textContent = '입구는 대기 줄이 짧았습니다.';
    });

    const snapshot = await page.evaluate(() => {
      const quoteText = (document.querySelector('.se-component-quotation [contenteditable="true"]') as HTMLElement | null)?.innerText?.trim() || '';
      const paragraphText = (document.querySelector('#editor > .se-paragraph') as HTMLElement | null)?.innerText?.trim() || '';
      return { quoteText, paragraphText };
    });

    expect(snapshot.quoteText).toBe('첫 방문기');
    expect(snapshot.paragraphText).toBe('입구는 대기 줄이 짧았습니다.');
    await page.close();
  });

  test('selector 변경(mock)으로 quote2 생성 실패 시 QuoteBlockCreateError', async () => {
    const page = await browser.newPage();
    await page.setContent('<html><body><div id="editor"></div></body></html>');
    await page.evaluate(() => {
      (window as any).__quote_cfg = { selectorChanged: true };
    });
    await expect(writeSectionTitleAsQuote2(makeAdapter(page), '첫 방문기'))
      .rejects.toThrow('quote2_block_create_failed');
    await page.close();
  });

  test('focus가 잘못되면 title_not_in_quote_block으로 실패', async () => {
    const page = await browser.newPage();
    await page.setContent('<html><body><div id="editor"></div></body></html>');
    await page.evaluate(() => {
      (window as any).__quote_cfg = { wrongFocus: true };
    });
    const result = await writeSectionTitleAsQuote2(makeAdapter(page), '첫 방문기');
    expect(result.success).toBe(false);
    expect(result.reason).toBe('title_not_in_quote_block');
    await page.close();
  });

  test('인용구1이 생성되면 quote1_detected로 실패', async () => {
    const page = await browser.newPage();
    await page.setContent('<html><body><div id="editor"></div></body></html>');
    await page.evaluate(() => {
      (window as any).__quote_cfg = { makeQuote1: true };
    });
    const result = await writeSectionTitleAsQuote2(makeAdapter(page), '첫 방문기');
    expect(result.success).toBe(false);
    expect(result.reason).toBe('quote1_detected');
    await page.close();
  });
});
