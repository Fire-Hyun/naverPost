export class AccountLock {
  private tails = new Map<string, Promise<void>>();

  async runExclusive<T>(accountId: string, task: () => Promise<T>): Promise<T> {
    const key = accountId || 'default';
    const prev = this.tails.get(key) ?? Promise.resolve();
    const runner = prev.catch(() => undefined).then(async () => await task());
    const nextTail = runner.then(() => undefined, () => undefined);
    this.tails.set(key, nextTail);
    try {
      return await runner;
    } finally {
      if (this.tails.get(key) === nextTail) {
        this.tails.delete(key);
      }
    }
  }
}
