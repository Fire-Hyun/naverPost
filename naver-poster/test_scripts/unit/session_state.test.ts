import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  classifyLoginState,
  getStorageStatePath,
  resolveNewContextStorageStateOption,
} from '../../src/naver/session';

describe('classifyLoginState', () => {
  test('로그인 리다이렉트 URL 단독 신호는 unknown', () => {
    const result = classifyLoginState(
      'https://nid.naver.com/nidlogin.login?mode=form',
      false,
      null,
      null,
      false,
    );
    expect(result.state).toBe('unknown');
    expect(result.signal).toBe('login_redirect_url_transient');
  });

  test('writer iframe 신호가 있으면 logged_in', () => {
    const result = classifyLoginState(
      'https://blog.naver.com/test?Redirect=Write&',
      true,
      null,
      null,
      false,
    );
    expect(result.state).toBe('logged_in');
    expect(result.signal).toBe('writer_iframe');
  });

  test('logout 신호가 있으면 logged_out', () => {
    const result = classifyLoginState(
      'https://www.naver.com',
      false,
      null,
      '#id',
      false,
    );
    expect(result.state).toBe('logged_out');
    expect(result.signal).toContain('logout_indicator');
  });

  test('신호가 없으면 unknown', () => {
    const result = classifyLoginState(
      'https://www.naver.com',
      false,
      null,
      null,
      false,
    );
    expect(result.state).toBe('unknown');
    expect(result.signal).toBe('no_indicator');
  });

  test('로그인 쿠키가 있으면 logged_in', () => {
    const result = classifyLoginState(
      'https://nid.naver.com/nidlogin.login?mode=form',
      false,
      null,
      null,
      true,
    );
    expect(result.state).toBe('logged_in');
    expect(result.signal).toBe('login_cookie_present');
  });

  test('storageStatePath 기본 경로를 userDataDir 하위로 생성한다', () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'storage-state-path-'));
    const storagePath = getStorageStatePath({ userDataDir: tempDir });
    expect(storagePath).toBe(path.join(path.resolve(tempDir), 'session_storage_state.json'));
  });

  test('newContext 모드에서 storageState 파일이 있으면 loaded=true', () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'storage-state-load-'));
    const storagePath = path.join(tempDir, 'session_storage_state.json');
    fs.writeFileSync(
      storagePath,
      JSON.stringify({
        cookies: [{ name: 'NID_SES', value: 'v', domain: '.naver.com', path: '/' }],
        origins: [],
      }),
      'utf-8',
    );

    const { storageStateOption, loadResult } = resolveNewContextStorageStateOption(storagePath);
    expect(storageStateOption).toBe(path.resolve(storagePath));
    expect(loadResult.loaded).toBe(true);
    expect(loadResult.cookieCount).toBe(1);
    expect(loadResult.fileSize).toBeGreaterThan(0);
  });
});
