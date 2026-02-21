import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { FileJobQueue } from '../../../src/worker/job_queue';

describe('queue_persistence', () => {
  test('큐 파일은 재시작(재인스턴스) 후에도 job을 유지한다', () => {
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'worker-queue-'));
    const queuePath = path.join(tempRoot, 'queue.json');

    const queueA = new FileJobQueue(queuePath);
    const job = queueA.enqueue({
      id: 'job_1',
      chatId: '100',
      dirPath: '/tmp/post',
      mode: 'draft',
    });
    expect(job.status).toBe('PENDING');

    const queueB = new FileJobQueue(queuePath);
    const loaded = queueB.findById('job_1');
    expect(loaded).not.toBeNull();
    expect(loaded?.status).toBe('PENDING');
    expect(loaded?.chatId).toBe('100');
  });
});

