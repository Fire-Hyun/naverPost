#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { chromium } = require('playwright');
const dotenv = require('dotenv');

dotenv.config({ path: path.resolve(process.cwd(), '.env') });

function parseArgs(argv) {
  const out = {
    headless: (process.env.HEADLESS || 'true').toLowerCase() !== 'false',
    statePath: process.env.NAVER_STORAGE_STATE_PATH || path.resolve(process.cwd(), '.secrets/state.json'),
    writeUrl: process.env.NAVER_WRITE_URL || `https://blog.naver.com/${process.env.NAVER_BLOG_ID || 'jun12310'}?Redirect=Write&`,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--headful') out.headless = false;
    if (arg === '--headless') out.headless = true;
    if (arg === '--state' && argv[i + 1]) out.statePath = path.resolve(argv[++i]);
    if (arg === '--writeUrl' && argv[i + 1]) out.writeUrl = argv[++i];
  }
  return out;
}

function waitForEnter(promptText) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(promptText, () => {
      rl.close();
      resolve();
    });
  });
}

function isLoginUrl(url) {
  return url.includes('nid.naver.com/nidlogin') || url.includes('logins.naver.com');
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  fs.mkdirSync(path.dirname(opts.statePath), { recursive: true });
  fs.mkdirSync(path.resolve(process.cwd(), 'artifacts'), { recursive: true });

  const browser = await chromium.launch({ headless: opts.headless });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 }, locale: 'ko-KR' });
  const page = await context.newPage();

  try {
    await page.goto(opts.writeUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    console.log('[auth] 브라우저에서 네이버 로그인/필요 동의를 완료하세요.');
    await waitForEnter('[auth] 완료 후 Enter를 누르세요: ');

    await page.waitForLoadState('domcontentloaded', { timeout: 10000 }).catch(() => undefined);
    if (isLoginUrl(page.url())) {
      throw new Error('로그인 페이지에 머물러 있습니다. 로그인/인증 완료 후 다시 실행하세요.');
    }

    await context.storageState({ path: opts.statePath });
    console.log(`[auth] storageState 저장 완료: ${opts.statePath}`);
  } catch (error) {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const screenshotPath = path.resolve(process.cwd(), `artifacts/auth_save_state_failed_${ts}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => undefined);
    console.error(`[auth] 실패: ${String(error)}`);
    console.error(`[auth] 디버그 스크린샷: ${screenshotPath}`);
    process.exitCode = 1;
  } finally {
    await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
  }
}

main().catch((error) => {
  console.error(`[auth] 예외: ${String(error)}`);
  process.exit(1);
});
