#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const dotenv = require('dotenv');

dotenv.config({ path: path.resolve(process.cwd(), '.env') });

function parseArgs(argv) {
  const out = {
    headless: (process.env.HEADLESS || 'true').toLowerCase() !== 'false',
    statePath: process.env.NAVER_STORAGE_STATE_PATH || path.resolve(process.cwd(), '.secrets/state.json'),
    writeUrl: process.env.NAVER_WRITE_URL || `https://blog.naver.com/${process.env.NAVER_BLOG_ID || 'jun12310'}?Redirect=Write&`,
    selectorsPath: path.resolve(process.cwd(), 'etc_scripts/post_selectors.example.json'),
    title: process.env.POST_TITLE || '',
    body: process.env.POST_BODY || '',
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--headful') out.headless = false;
    if (arg === '--headless') out.headless = true;
    if (arg === '--state' && argv[i + 1]) out.statePath = path.resolve(argv[++i]);
    if (arg === '--writeUrl' && argv[i + 1]) out.writeUrl = argv[++i];
    if (arg === '--selectors' && argv[i + 1]) out.selectorsPath = path.resolve(argv[++i]);
    if (arg === '--title' && argv[i + 1]) out.title = argv[++i];
    if (arg === '--body' && argv[i + 1]) out.body = argv[++i];
  }
  return out;
}

function isLoginUrl(url) {
  return url.includes('nid.naver.com/nidlogin') || url.includes('logins.naver.com');
}

async function firstVisible(page, selectors) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (await locator.count().catch(() => 0)) return { selector, locator };
  }
  return null;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!fs.existsSync(opts.statePath)) {
    throw new Error(`state 파일이 없습니다: ${opts.statePath}\n먼저 node etc_scripts/auth_save_state.js 를 실행하세요.`);
  }
  if (!opts.title.trim() || !opts.body.trim()) {
    throw new Error('업로드할 title/body가 비어 있습니다. --title/--body 또는 POST_TITLE/POST_BODY를 설정하세요.');
  }

  const selectors = JSON.parse(fs.readFileSync(opts.selectorsPath, 'utf-8'));
  fs.mkdirSync(path.resolve(process.cwd(), 'artifacts'), { recursive: true });

  const browser = await chromium.launch({ headless: opts.headless });
  const context = await browser.newContext({
    storageState: opts.statePath,
    viewport: { width: 1400, height: 900 },
    locale: 'ko-KR',
  });
  const page = await context.newPage();

  try {
    await page.goto(opts.writeUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    if (isLoginUrl(page.url())) {
      throw new Error('세션이 만료되었거나 유효하지 않습니다. node etc_scripts/auth_save_state.js 를 다시 실행하세요.');
    }

    const titleTarget = await firstVisible(page, selectors.title);
    if (!titleTarget) throw new Error('title selector를 찾지 못했습니다. selectors 파일을 업데이트하세요.');
    await titleTarget.locator.click({ timeout: 5000 });
    await titleTarget.locator.fill(opts.title, { timeout: 5000 });

    const bodyTarget = await firstVisible(page, selectors.body);
    if (!bodyTarget) throw new Error('body selector를 찾지 못했습니다. selectors 파일을 업데이트하세요.');
    await bodyTarget.locator.click({ timeout: 5000 });
    await page.keyboard.type(opts.body, { delay: 20 });

    const saveTarget = await firstVisible(page, selectors.draftSave);
    if (!saveTarget) throw new Error('draftSave selector를 찾지 못했습니다. selectors 파일을 업데이트하세요.');
    await saveTarget.locator.click({ timeout: 5000 });

    if (Array.isArray(selectors.draftSavedSignals) && selectors.draftSavedSignals.length > 0) {
      await firstVisible(page, selectors.draftSavedSignals).catch(() => null);
    }

    console.log('[upload] 임시저장 클릭 완료');
  } catch (error) {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const screenshotPath = path.resolve(process.cwd(), `artifacts/upload_failed_${ts}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => undefined);
    console.error(`[upload] 실패: ${String(error)}`);
    console.error(`[upload] 디버그 스크린샷: ${screenshotPath}`);
    process.exitCode = 1;
  } finally {
    await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
  }
}

main().catch((error) => {
  console.error(`[upload] 예외: ${String(error)}`);
  process.exit(1);
});
