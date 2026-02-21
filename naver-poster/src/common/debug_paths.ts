import * as fs from 'fs';
import * as path from 'path';
import { getCurrentLogDir } from './logger';

function timestamp(now: Date = new Date()): string {
  return now.toISOString().replace(/[:.]/g, '-');
}

export function getDebugRootDir(name: string, now: Date = new Date()): string {
  if (name === 'navertimeoutdebug') {
    const override = (process.env.NAVER_TIMEOUT_DEBUG_DIR || '').trim();
    if (override) return path.resolve(override);
  }
  return path.resolve(path.join(getCurrentLogDir(now), name));
}

export function ensureDebugRootDir(name: string, now: Date = new Date()): string {
  const root = getDebugRootDir(name, now);
  fs.mkdirSync(root, { recursive: true });
  return root;
}

export function createDebugRunDir(name: string, suffix?: string, now: Date = new Date()): string {
  const root = ensureDebugRootDir(name, now);
  const folderName = suffix ? `${timestamp(now)}_${suffix}` : timestamp(now);
  const runDir = path.join(root, folderName);
  fs.mkdirSync(runDir, { recursive: true });
  return runDir;
}
