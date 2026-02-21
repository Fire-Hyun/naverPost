import * as fs from 'fs';
import * as path from 'path';

import * as log from '../utils/logger';
import { createPersistentSession, detectLoginState, isLoginRedirectUrl, SessionOptions } from '../naver/session';
import { FailureReasonCode, SessionValidationResult } from './types';

type SecuritySignalInput = {
  url: string;
  bodyText: string;
};

export function detectSecurityChallengeSignal(input: SecuritySignalInput): boolean {
  const text = `${input.url}\n${input.bodyText}`.toLowerCase();
  return [
    /captcha|캡차|보안문자/,
    /otp|2단계|인증번호|추가 인증/,
    /본인확인|보안 확인|새로운 기기|기기 인증|보호조치/,
    /약관|동의 필요/,
  ].some((pattern) => pattern.test(text));
}

async function captureValidationArtifacts(
  page: { url: () => string; content: () => Promise<string>; screenshot: (opts: { path: string; fullPage: boolean }) => Promise<unknown> },
  reasonCode: FailureReasonCode,
  detail: string,
): Promise<string | undefined> {
  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const dir = path.resolve('./artifacts/session_validation', `${timestamp}_${reasonCode.toLowerCase()}`);
    fs.mkdirSync(dir, { recursive: true });
    const screenshot = path.join(dir, '01_page.png');
    const html = path.join(dir, '02_page.html');
    const meta = path.join(dir, '00_meta.json');
    await page.screenshot({ path: screenshot, fullPage: true }).catch(() => undefined);
    fs.writeFileSync(html, await page.content().catch(() => ''), 'utf-8');
    fs.writeFileSync(meta, JSON.stringify({
      reasonCode,
      detail,
      url: page.url(),
      at: new Date().toISOString(),
    }, null, 2), 'utf-8');
    return dir;
  } catch {
    return undefined;
  }
}

function classifyErrorToReason(error: unknown): FailureReasonCode {
  const message = String((error as any)?.message ?? error ?? '');
  if (/timeout|net::|econn|network|socket|dns/i.test(message)) return 'NETWORK_ERROR';
  if (/selector|iframe|editor|not found|detached/i.test(message)) return 'SELECTOR_BROKEN';
  return 'NETWORK_ERROR';
}

export async function validateSessionForWorker(
  opts: SessionOptions,
  writeUrl: string,
): Promise<SessionValidationResult> {
  const session = await createPersistentSession({
    ...opts,
    headless: true,
  });
  const { page, context, browser } = session;
  try {
    await page.goto(writeUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    const state = await detectLoginState(page);
    const bodyText = await page.evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' ')).catch(() => '');
    if (detectSecurityChallengeSignal({ url: page.url(), bodyText })) {
      const detail = `security_signal url=${page.url()} login_signal=${state.signal}`;
      const artifactsDir = await captureValidationArtifacts(page, 'SECURITY_CHALLENGE', detail);
      return { ok: false, reasonCode: 'SECURITY_CHALLENGE', detail, artifactsDir };
    }

    if (state.state === 'logged_in') {
      return { ok: true, detail: `login_signal=${state.signal}` };
    }

    if (state.state === 'logged_out' || isLoginRedirectUrl(page.url())) {
      const detail = `login_redirect_or_logged_out url=${page.url()} login_signal=${state.signal}`;
      const artifactsDir = await captureValidationArtifacts(page, 'SESSION_EXPIRED', detail);
      return { ok: false, reasonCode: 'SESSION_EXPIRED', detail, artifactsDir };
    }

    const detail = `unknown_login_state url=${page.url()} login_signal=${state.signal}`;
    const artifactsDir = await captureValidationArtifacts(page, 'SESSION_EXPIRED', detail);
    return { ok: false, reasonCode: 'SESSION_EXPIRED', detail, artifactsDir };
  } catch (error) {
    const reasonCode = classifyErrorToReason(error);
    const detail = `validation_exception reason=${reasonCode} error=${String(error)}`;
    const artifactsDir = await captureValidationArtifacts(page, reasonCode, detail);
    log.error(`[worker] session validation failed reason=${reasonCode} detail=${detail}`);
    return { ok: false, reasonCode, detail, artifactsDir };
  } finally {
    await context.close().catch(() => undefined);
    if (browser) await browser.close().catch(() => undefined);
  }
}
