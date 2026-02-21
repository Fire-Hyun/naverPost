import * as path from 'path';
import * as fs from 'fs';
import { chromium } from 'playwright';

async function main(): Promise<void> {
  const profileDir = process.env.NAVER_PROFILE_DIR || process.env.NAVER_USER_DATA_DIR || 'C:\\naverProfile_bot';
  const output = process.env.NAVER_STORAGE_STATE_PATH || path.join(profileDir, 'session_storage_state.json');
  fs.mkdirSync(path.dirname(output), { recursive: true });

  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    viewport: { width: 1400, height: 900 },
    locale: 'ko-KR',
  });
  const page = context.pages()[0] ?? await context.newPage();
  await page.goto('https://blog.naver.com?Redirect=Write&', { waitUntil: 'domcontentloaded' });

  process.stdout.write('Windows 브라우저에서 로그인/동의 완료 후 Enter를 누르세요... ');
  await new Promise<void>((resolve) => {
    process.stdin.once('data', () => resolve());
  });

  await context.storageState({ path: output });
  await context.close();
  process.stdout.write(`저장 완료: ${output}\n`);
}

main().catch((error) => {
  process.stderr.write(`실패: ${String(error)}\n`);
  process.exit(1);
});
