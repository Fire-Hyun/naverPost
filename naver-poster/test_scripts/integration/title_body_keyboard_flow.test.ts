import { Browser, chromium } from 'playwright';
import { EditorContext, TITLE_TO_BODY_ENTER_SEQUENCE, writeTitleThenBodyViaKeyboard } from '../../src/naver/editor';

describe('title -> body keyboard flow', () => {
  let browser: Browser;

  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
  });

  afterAll(async () => {
    await browser.close();
  });

  test('제목 입력 후 Enter 기반으로 본문이 분리 입력된다', async () => {
    const page = await browser.newPage();
    await page.setContent(`
      <html>
        <body>
          <div class="se-documentTitle">
            <div contenteditable="true" class="se-text-paragraph"></div>
          </div>
          <div class="se-main-container">
            <div class="se-components-content">
              <div class="se-component se-text">
                <div contenteditable="true" class="se-text-paragraph"></div>
              </div>
            </div>
          </div>
        </body>
      </html>
    `);

    const ctx: EditorContext = {
      page,
      frame: page.mainFrame(),
    };

    const title = '제목 테스트';
    const body = '본문 첫 문장입니다.\n본문 둘째 문장입니다.';
    const ok = await writeTitleThenBodyViaKeyboard(ctx, title, body);
    expect(ok).toBe(true);

    const titleText = await page.locator('.se-documentTitle').innerText();
    const bodyText = await page.locator('.se-components-content').innerText();
    expect(titleText).toContain('제목 테스트');
    expect(titleText).not.toContain('본문 첫 문장');
    expect(bodyText).toContain('본문 첫 문장입니다.');
    await page.close();
  });

  test('title->body 전환은 Enter 2회 시퀀스를 유지한다', () => {
    expect(TITLE_TO_BODY_ENTER_SEQUENCE).toEqual(['Enter', 'Enter']);
  });
});
