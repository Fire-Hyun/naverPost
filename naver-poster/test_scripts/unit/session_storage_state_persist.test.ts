import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { persistSessionState } from '../../src/naver/session';

describe('persistSessionState', () => {
  test('storageState 저장 호출 시 파일 쓰기를 수행한다', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'persist-session-state-'));
    const storagePath = path.join(tempDir, 'session_storage_state.json');
    const storageState = jest.fn(async ({ path: targetPath }: { path: string }) => {
      fs.writeFileSync(
        targetPath,
        JSON.stringify({
          cookies: [{ name: 'NID_SES', value: 'v', domain: '.naver.com', path: '/' }],
          origins: [],
        }),
        'utf-8',
      );
    });

    const fakeContext = { storageState } as any;
    const fakePage = {
      url: () => 'https://blog.naver.com',
      evaluate: jest.fn(async () => ({ localStorage: { k: 'v' }, sessionStorage: {} })),
    } as any;

    await persistSessionState(fakeContext, fakePage, storagePath);

    expect(storageState).toHaveBeenCalledTimes(1);
    expect(storageState).toHaveBeenCalledWith({ path: path.resolve(storagePath) });
    expect(fs.existsSync(storagePath)).toBe(true);
    expect(fs.statSync(storagePath).size).toBeGreaterThan(0);
    expect(fs.existsSync(`${path.resolve(storagePath)}.webstorage.json`)).toBe(true);
  });
});
