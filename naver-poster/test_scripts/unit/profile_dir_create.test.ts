describe('profile dir create', () => {
  afterEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
    jest.unmock('fs');
  });

  test('존재하지 않는 profileDir이면 mkdirSync를 호출한다', () => {
    const existsSync = jest.fn()
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    const mkdirSync = jest.fn();

    jest.doMock('fs', () => {
      const actual = jest.requireActual('fs');
      return {
        ...actual,
        existsSync,
        mkdirSync,
      };
    });

    jest.isolateModules(() => {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { ensureProfileDir } = require('../../src/naver/session');
      const result = ensureProfileDir('/tmp/naver_profile_bot');
      expect(mkdirSync).toHaveBeenCalledTimes(1);
      expect(result.exists).toBe(true);
      expect(result.created).toBe(true);
    });
  });
});
