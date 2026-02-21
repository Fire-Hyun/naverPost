import { spawnSync } from 'child_process';
import * as path from 'path';

describe('e2e full flow once', () => {
  test('verify_flow 스크립트가 1회 통과한다', () => {
    const root = path.resolve(__dirname, '../..');
    const script = path.join(root, 'test_scripts/verify_flow.js');
    const result = spawnSync(process.execPath, [script], {
      cwd: root,
      env: {
        ...process.env,
        VERIFY_FLOW_ONLINE: process.env.VERIFY_FLOW_ONLINE || 'false',
      },
      encoding: 'utf-8',
    });
    if ((result.status ?? 1) !== 0) {
      throw new Error(`verify_flow failed\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
    }
  }, 300000);
});
