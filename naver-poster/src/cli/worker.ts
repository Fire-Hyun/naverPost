#!/usr/bin/env node

import { Command } from 'commander';
import * as dotenv from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';

import * as log from '../utils/logger';
import { WorkerService } from '../worker/worker_service';

const envPath = path.resolve(process.cwd(), '.env');
if (fs.existsSync(envPath)) {
  dotenv.config({ path: envPath });
}

const program = new Command();
program
  .name('naver-worker')
  .description('텔레그램 요청 큐를 소비하는 무인 업로더(worker)')
  .option('--headless', '무인 headless 모드 (필수)', true)
  .option('--poll <sec>', '큐/텔레그램 폴링 주기(초)', '15')
  .option('--resume', 'BLOCKED_LOGIN 작업 재개 검사 실행(기본: 활성)', true)
  .option('--once', '1회 처리 후 종료', false)
  .action(async (opts) => {
    try {
      const pollSec = Math.max(1, parseInt(String(opts.poll ?? '15'), 10));
      const headless = String(process.env.HEADLESS ?? 'true').toLowerCase() !== 'false';
      if (!opts.headless || !headless) {
        throw new Error('worker는 headless=true 고정입니다. GUI/interactiveLogin 경로는 금지됩니다.');
      }
      process.env.HEADLESS = 'true';

      const token = process.env.TELEGRAM_BOT_TOKEN;
      const adminChatId = process.env.TELEGRAM_ADMIN_CHAT_ID;
      if (!token) {
        log.warn('[worker] TELEGRAM_BOT_TOKEN 미설정: 큐 소비만 수행하고 텔레그램 수신/알림은 비활성화됩니다.');
      }
      if (!adminChatId) {
        log.warn('[worker] TELEGRAM_ADMIN_CHAT_ID 미설정: 관리자 알림 전송이 비활성화됩니다.');
      }

      const service = new WorkerService({
        pollSec,
        headless: true,
        resume: Boolean(opts.resume),
        telegramToken: token,
        adminChatId,
      });

      if (opts.once) {
        await service.runOnce();
        process.exit(0);
      }
      await service.runLoop();
    } catch (error: any) {
      log.error(`[worker] 실행 실패: ${error?.message ?? String(error)}`);
      process.exit(1);
    }
  });

program.parse(process.argv);
