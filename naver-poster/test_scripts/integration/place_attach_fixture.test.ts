import { Browser, chromium } from 'playwright';
import { EditorContext } from '../../src/naver/editor';
import { clickPlaceAddButtonForTest } from '../../src/naver/place';

describe('place attach fixture', () => {
  let browser: Browser;

  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
  });

  afterAll(async () => {
    await browser.close();
  });

  test('장소 버튼/패널/검색 결과를 통해 장소 카드가 삽입된다', async () => {
    const prevId = process.env.NAVER_MAP_CLIENT_ID;
    const prevSecret = process.env.NAVER_MAP_CLIENT_SECRET;
    const prevFallbackId = process.env.NAVER_CLIENT_ID;
    const prevFallbackSecret = process.env.NAVER_CLIENT_SECRET;
    delete process.env.NAVER_MAP_CLIENT_ID;
    delete process.env.NAVER_MAP_CLIENT_SECRET;
    delete process.env.NAVER_CLIENT_ID;
    delete process.env.NAVER_CLIENT_SECRET;
    const page = await browser.newPage();
    await page.setContent(`
      <html>
        <body>
          <div class="se-toolbar">
            <button data-name="map" id="place-btn">장소</button>
          </div>
          <div class="se-place-search-layer" id="panel" style="display:none;">
            <input type="text" placeholder="장소 검색" id="place-input" />
            <ul class="se-place-search-result" id="result-list"></ul>
            <button class="se-place-add-button" id="place-add-btn">추가</button>
          </div>
          <div id="editor-body"></div>
          <script>
            window.__placeAddClicked = false;
            const panel = document.getElementById('panel');
            const placeBtn = document.getElementById('place-btn');
            const input = document.getElementById('place-input');
            const resultList = document.getElementById('result-list');
            const addBtn = document.getElementById('place-add-btn');
            const editor = document.getElementById('editor-body');
            placeBtn.addEventListener('click', () => {
              panel.style.display = 'block';
            });
            input.addEventListener('keydown', (e) => {
              if (e.key !== 'Enter') return;
              resultList.innerHTML = '<li class="se-map-search-result-item se-is-highlight">하이디라오 제주도점 제주시</li>';
              const li = resultList.querySelector('li');
              li.addEventListener('click', () => {
                addBtn.setAttribute('data-selected', 'true');
              });
            });
            addBtn.addEventListener('click', () => {
              window.__placeAddClicked = true;
              const card = document.createElement('div');
              card.className = 'se-component-place';
              card.innerText = '하이디라오 제주도점 제주시';
              editor.appendChild(card);
            });
          </script>
        </body>
      </html>
    `);

    const ctx: EditorContext = { page, frame: page.mainFrame() };
    await page.click('#place-btn');
    await page.fill('#place-input', '하이디라오 제주도점');
    await page.press('#place-input', 'Enter');
    await page.click('.se-map-search-result-item');
    const addClicked = await clickPlaceAddButtonForTest(ctx.frame, 2_000);
    expect(addClicked).toBe(true);
    expect(await page.evaluate(() => (window as any).__placeAddClicked)).toBe(true);
    expect(await page.locator('.se-component-place').count()).toBeGreaterThan(0);
    await page.close();
    if (prevId) process.env.NAVER_MAP_CLIENT_ID = prevId;
    if (prevSecret) process.env.NAVER_MAP_CLIENT_SECRET = prevSecret;
    if (prevFallbackId) process.env.NAVER_CLIENT_ID = prevFallbackId;
    if (prevFallbackSecret) process.env.NAVER_CLIENT_SECRET = prevFallbackSecret;
  }, 45_000);
});
