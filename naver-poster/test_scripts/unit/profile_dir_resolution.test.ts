import * as path from 'path';
import { resolveProfileDir } from '../../src/naver/session';

describe('profile dir resolution', () => {
  const prevProfileDir = process.env.NAVER_PROFILE_DIR;
  const prevUserDataDir = process.env.NAVER_USER_DATA_DIR;

  afterEach(() => {
    if (prevProfileDir === undefined) delete process.env.NAVER_PROFILE_DIR;
    else process.env.NAVER_PROFILE_DIR = prevProfileDir;
    if (prevUserDataDir === undefined) delete process.env.NAVER_USER_DATA_DIR;
    else process.env.NAVER_USER_DATA_DIR = prevUserDataDir;
  });

  test('CLI profileDir가 ENV보다 우선한다', () => {
    process.env.NAVER_PROFILE_DIR = '/tmp/from-env';
    const resolved = resolveProfileDir({
      profileDir: '/tmp/from-cli',
      userDataDir: '/tmp/legacy',
    });
    expect(resolved).toBe(path.resolve('/tmp/from-cli'));
  });

  test('CLI 미지정 시 NAVER_PROFILE_DIR를 사용한다', () => {
    process.env.NAVER_PROFILE_DIR = '/tmp/from-env';
    delete process.env.NAVER_USER_DATA_DIR;
    const resolved = resolveProfileDir({});
    expect(resolved).toBe(path.resolve('/tmp/from-env'));
  });

  test('CLI/ENV 모두 없으면 기본값을 사용한다', () => {
    delete process.env.NAVER_PROFILE_DIR;
    delete process.env.NAVER_USER_DATA_DIR;
    const resolved = resolveProfileDir({});
    expect(resolved).toBe(path.resolve('./.secrets/naver_user_data_dir'));
  });
});
