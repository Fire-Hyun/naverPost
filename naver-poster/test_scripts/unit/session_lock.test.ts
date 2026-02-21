import { AccountLock } from '../../src/worker/account_lock';

describe('session/account lock', () => {
  test('동일 accountId는 직렬 실행된다', async () => {
    const lock = new AccountLock();
    let inFlight = 0;
    let maxInFlight = 0;
    const tasks = Array.from({ length: 3 }).map((_, idx) => lock.runExclusive('acc-1', async () => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((resolve) => setTimeout(resolve, 20 + idx * 5));
      inFlight -= 1;
      return idx;
    }));
    const out = await Promise.all(tasks);
    expect(out).toEqual([0, 1, 2]);
    expect(maxInFlight).toBe(1);
  });
});
