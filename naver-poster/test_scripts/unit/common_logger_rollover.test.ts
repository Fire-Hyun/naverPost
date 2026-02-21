import fs from 'fs';
import path from 'path';
import os from 'os';

describe('common logger rollover', () => {
  const RealDate = Date;

  afterEach(() => {
    global.Date = RealDate as DateConstructor;
    jest.resetModules();
  });

  test('creates new yyyyMMdd directory when date changes', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'logger-rollover-'));
    const oldCwd = process.cwd();
    process.chdir(tmp);

    try {
      class MockDate1 extends RealDate {
        constructor(...args: any[]) {
          if (args.length === 0) {
            super('2026-02-21T10:00:00.123Z');
            return;
          }
          // @ts-ignore
          super(...args);
        }
      }
      // @ts-ignore
      global.Date = MockDate1;
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      let logger = require('../../src/common/logger') as typeof import('../../src/common/logger');
      logger.writeLog('INFO', 'naver.upload', 'first');
      expect(fs.existsSync(path.join(tmp, 'logs', '20260221', 'app.log'))).toBe(true);

      class MockDate2 extends RealDate {
        constructor(...args: any[]) {
          if (args.length === 0) {
            super('2026-02-22T00:00:00.001Z');
            return;
          }
          // @ts-ignore
          super(...args);
        }
      }
      // @ts-ignore
      global.Date = MockDate2;
      logger.writeLog('INFO', 'naver.upload', 'second');
      expect(fs.existsSync(path.join(tmp, 'logs', '20260222', 'app.log'))).toBe(true);

      const line = fs.readFileSync(path.join(tmp, 'logs', '20260222', 'app.log'), 'utf-8').trim();
      expect(line).toMatch(/^\[2026-02-22 /);
      expect(line).toContain('[INFO] [naver.upload] second');
    } finally {
      process.chdir(oldCwd);
    }
  });
});
