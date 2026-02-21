import * as fs from 'fs';
import * as path from 'path';

import { WorkerJob, WorkerJobStatus, WorkerQueueState } from './types';

const DEFAULT_QUEUE_STATE: WorkerQueueState = {
  version: 1,
  jobs: [],
};

export class FileJobQueue {
  private readonly queuePath: string;

  constructor(queuePath: string) {
    this.queuePath = path.resolve(queuePath);
    this.ensureQueueFile();
  }

  private ensureQueueFile(): void {
    fs.mkdirSync(path.dirname(this.queuePath), { recursive: true });
    if (!fs.existsSync(this.queuePath)) {
      fs.writeFileSync(this.queuePath, JSON.stringify(DEFAULT_QUEUE_STATE, null, 2), 'utf-8');
    }
  }

  private readState(): WorkerQueueState {
    this.ensureQueueFile();
    try {
      const parsed = JSON.parse(fs.readFileSync(this.queuePath, 'utf-8')) as WorkerQueueState;
      if (!Array.isArray(parsed.jobs)) return { ...DEFAULT_QUEUE_STATE };
      return {
        version: Number(parsed.version || 1),
        jobs: parsed.jobs,
      };
    } catch {
      return { ...DEFAULT_QUEUE_STATE };
    }
  }

  private writeState(state: WorkerQueueState): void {
    fs.mkdirSync(path.dirname(this.queuePath), { recursive: true });
    fs.writeFileSync(this.queuePath, JSON.stringify(state, null, 2), 'utf-8');
  }

  listAll(): WorkerJob[] {
    return this.readState().jobs;
  }

  listByStatus(status: WorkerJobStatus): WorkerJob[] {
    return this.readState().jobs.filter((job) => job.status === status);
  }

  enqueue(input: Omit<WorkerJob, 'status' | 'createdAt' | 'updatedAt' | 'attempts'>): WorkerJob {
    const now = new Date().toISOString();
    const state = this.readState();
    const job: WorkerJob = {
      ...input,
      status: 'PENDING',
      createdAt: now,
      updatedAt: now,
      attempts: 0,
    };
    state.jobs.push(job);
    this.writeState(state);
    return job;
  }

  findById(id: string): WorkerJob | null {
    return this.readState().jobs.find((job) => job.id === id) ?? null;
  }

  getNextPending(): WorkerJob | null {
    const state = this.readState();
    return state.jobs.find((job) => job.status === 'PENDING') ?? null;
  }

  updateJob(id: string, patch: Partial<WorkerJob>): WorkerJob | null {
    const state = this.readState();
    const index = state.jobs.findIndex((job) => job.id === id);
    if (index < 0) return null;
    const next: WorkerJob = {
      ...state.jobs[index],
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    state.jobs[index] = next;
    this.writeState(state);
    return next;
  }

  moveBlockedToPending(): number {
    const state = this.readState();
    let count = 0;
    for (let i = 0; i < state.jobs.length; i++) {
      if (state.jobs[i].status === 'BLOCKED_LOGIN') {
        state.jobs[i] = {
          ...state.jobs[i],
          status: 'PENDING',
          updatedAt: new Date().toISOString(),
          lastError: undefined,
          reasonCode: undefined,
        };
        count += 1;
      }
    }
    if (count > 0) this.writeState(state);
    return count;
  }
}

