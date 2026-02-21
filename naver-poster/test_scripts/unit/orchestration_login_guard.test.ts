import * as fs from 'fs';
import * as path from 'path';

describe('orchestration login guard', () => {
  test('임시저장 직전에 ensureLoggedIn(passive) 호출이 존재한다', () => {
    const filePath = path.resolve(__dirname, '../../src/cli/post_to_naver.ts');
    const src = fs.readFileSync(filePath, 'utf-8');
    expect(src.includes('ensure_logged_in_before_draft')).toBe(true);
    expect(src.includes("ensureLoggedIn(session, sessionOpts, config.writeUrl, 'passive')")).toBe(true);
  });
});
