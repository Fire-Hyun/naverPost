import * as fs from 'fs';
import * as path from 'path';

export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS' | 'STEP';

const LOG_FILES = ['app.log', 'error.log', 'telegram.log', 'naver.log'] as const;
type LogFile = typeof LOG_FILES[number];

let lastUsedDate = '';
let currentLogDir = '';
let fileDescriptors: Record<LogFile, number> | null = null;
let shutdownHookRegistered = false;

function pad(value: number, width: number = 2): string {
  return String(value).padStart(width, '0');
}

export function getDateKey(now: Date = new Date()): string {
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
}

function getTimestamp(now: Date): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${pad(now.getMilliseconds(), 3)}`;
}

function closeStreams(): void {
  if (!fileDescriptors) return;
  for (const fd of Object.values(fileDescriptors)) {
    fs.closeSync(fd);
  }
  fileDescriptors = null;
}

function registerShutdownHook(): void {
  if (shutdownHookRegistered) return;
  shutdownHookRegistered = true;
  process.once('beforeExit', closeStreams);
  process.once('exit', closeStreams);
  process.once('SIGINT', () => {
    closeStreams();
    process.exit(130);
  });
  process.once('SIGTERM', () => {
    closeStreams();
    process.exit(143);
  });
}

export function getLogBaseDir(): string {
  return path.resolve(process.cwd(), 'logs');
}

export function getCurrentLogDir(now: Date = new Date()): string {
  const dateKey = getDateKey(now);
  return path.join(getLogBaseDir(), dateKey);
}

export function resolveTodayLogFile(file: LogFile, now: Date = new Date()): string {
  return path.join(getCurrentLogDir(now), file);
}

function ensureTodayDir(now: Date): string {
  registerShutdownHook();
  const dateKey = getDateKey(now);
  const nextLogDir = getCurrentLogDir(now);

  if (dateKey !== lastUsedDate || !fileDescriptors || currentLogDir !== nextLogDir) {
    closeStreams();
    fs.mkdirSync(nextLogDir, { recursive: true });
    fileDescriptors = {
      'app.log': fs.openSync(path.join(nextLogDir, 'app.log'), 'a'),
      'error.log': fs.openSync(path.join(nextLogDir, 'error.log'), 'a'),
      'telegram.log': fs.openSync(path.join(nextLogDir, 'telegram.log'), 'a'),
      'naver.log': fs.openSync(path.join(nextLogDir, 'naver.log'), 'a'),
    };
    currentLogDir = nextLogDir;
    lastUsedDate = dateKey;
  } else if (!fs.existsSync(nextLogDir)) {
    fs.mkdirSync(nextLogDir, { recursive: true });
  }

  return currentLogDir;
}

function filesFor(level: LogLevel, moduleName: string): LogFile[] {
  const files = new Set<LogFile>(['app.log', 'naver.log']);
  if (moduleName.toLowerCase().includes('telegram')) {
    files.add('telegram.log');
  }
  if (level === 'ERROR') {
    files.add('error.log');
  }
  return [...files];
}

function stringifyMessage(message: unknown): string {
  if (typeof message === 'string') return message;
  try {
    return JSON.stringify(message);
  } catch {
    return String(message);
  }
}

export function writeLog(level: LogLevel, moduleName: string, message: unknown): void {
  const now = new Date();
  ensureTodayDir(now);
  const line = `[${getTimestamp(now)}] [${level}] [${moduleName}] ${stringifyMessage(message)}`;
  if (!fileDescriptors) {
    throw new Error('logger stream is not initialized');
  }
  for (const file of filesFor(level, moduleName)) {
    fs.writeSync(fileDescriptors[file], `${line}\n`);
  }
  if (level === 'ERROR') {
    process.stderr.write(`${line}\n`);
    return;
  }
  process.stdout.write(`${line}\n`);
}
