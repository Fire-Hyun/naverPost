import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { FileJobQueue } from '../../../src/worker/job_queue';
import { WorkerService } from '../../../src/worker/worker_service';

describe('worker_blocked_login', () => {
  test('세션 만료 시 job을 BLOCKED_LOGIN으로 전환하고 알림을 보낸다', async () => {
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'worker-blocked-'));
    const queuePath = path.join(tempRoot, 'queue.json');
    const queue = new FileJobQueue(queuePath);
    queue.enqueue({
      id: 'job_blocked_1',
      chatId: '12345',
      dirPath: '/tmp/post-dir',
      mode: 'draft',
    });

    const adminMessages: string[] = [];
    const userMessages: string[] = [];
    const service = new WorkerService(
      {
        queuePath,
        pollSec: 1,
        headless: true,
        resume: false,
      },
      {
        // 단일 세션 오너 모델: executeUploadJob이 SESSION_EXPIRED를 반환하면 BLOCKED_LOGIN으로 전환
        executeUploadJob: async () => ({
          ok: false,
          reasonCode: 'SESSION_EXPIRED' as const,
          detail: 'login redirect',
          stdout: 'SESSION_EXPIRED login redirect',
          stderr: '',
        }),
        notifyAdmin: async (message: string) => {
          adminMessages.push(message);
        },
        notifyUser: async (_chatId: string, message: string) => {
          userMessages.push(message);
        },
      },
    );

    const processed = await service.processNextJob();
    expect(processed).toBe(true);

    const updated = new FileJobQueue(queuePath).findById('job_blocked_1');
    expect(updated?.status).toBe('BLOCKED_LOGIN');
    expect(updated?.reasonCode).toBe('SESSION_EXPIRED');
    expect(adminMessages.length).toBeGreaterThan(0);
    expect(userMessages.some((m) => m.includes('BLOCKED_LOGIN'))).toBe(true);
  });
});
