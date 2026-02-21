describe('profile dir lock detection', () => {
  afterEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
    jest.unmock('fs');
  });

  test('Singleton 파일이 존재하면 lockDetected=true', () => {
    const existsSync = jest.fn((p: string) => p.endsWith('SingletonLock'));

    jest.doMock('fs', () => {
      const actual = jest.requireActual('fs');
      return {
        ...actual,
        existsSync,
      };
    });

    jest.isolateModules(() => {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { detectProfileDirLock } = require('../../src/naver/session');
      const result = detectProfileDirLock('/tmp/naver_profile_bot');
      expect(result.lockDetected).toBe(true);
      expect(result.lockPaths).toEqual(['/tmp/naver_profile_bot/SingletonLock']);
    });
  });
});
