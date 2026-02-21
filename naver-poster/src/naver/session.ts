import { chromium, Browser, BrowserContext, Page } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';
import * as log from '../utils/logger';
import { ensureDebugRootDir } from '../common/debug_paths';
import { collectTimeoutDebugArtifacts } from './timeout_debug';

export interface SessionOptions {
  /** persistent context 사용 시 프로필 디렉토리 */
  userDataDir?: string;
  /** userDataDir 별칭: CLI profileDir/ENV NAVER_PROFILE_DIR 우선 사용 */
  profileDir?: string;
  /** storageState 파일 경로 */
  storageStatePath?: string;
  headless?: boolean;
  slowMo?: number;
}

type OriginStorage = {
  localStorage: Record<string, string>;
  sessionStorage: Record<string, string>;
};

type WebStorageSnapshot = Record<string, OriginStorage>;
const DEFAULT_STORAGE_STATE_FILENAME = 'session_storage_state.json';
const USER_DATA_DIR_LOCK_FILES = ['SingletonLock', 'SingletonSocket', 'SingletonCookie'];

type StorageStateSummary = {
  path: string;
  exists: boolean;
  fileSize: number;
  cookieCount: number;
};

type StorageStateLoadResult = StorageStateSummary & {
  loaded: boolean;
  mode: 'persistent' | 'new_context' | 'none';
  reason?: string;
};

function getWebStorageSnapshotPath(storageStatePath: string): string {
  return `${storageStatePath}.webstorage.json`;
}

function readWebStorageSnapshot(snapshotPath: string): WebStorageSnapshot {
  try {
    if (!fs.existsSync(snapshotPath)) return {};
    return JSON.parse(fs.readFileSync(snapshotPath, 'utf-8')) as WebStorageSnapshot;
  } catch {
    return {};
  }
}

/**
 * XServer(DISPLAY) 사용 가능 여부를 감지한다.
 * headed 모드 요청 시 XServer가 없으면 환경 설정 오류로 판단.
 */
function validateDisplayEnvironment(headless: boolean): void {
  if (headless) return; // headless면 DISPLAY 불필요

  const display = process.env.DISPLAY;
  const waylandDisplay = process.env.WAYLAND_DISPLAY;
  const hasDisplayEnv = Boolean(display || waylandDisplay);
  const hasWslgMount = fs.existsSync('/mnt/wslg');
  const isLikelyWsl = process.platform === 'linux'
    && (Boolean(process.env.WSL_DISTRO_NAME) || Boolean(process.env.WSL_INTEROP));
  const hasWslg = hasWslgMount || hasDisplayEnv;

  if (hasDisplayEnv) return;
  if (isLikelyWsl && !hasWslg) {
    throw new Error(
      '[WSLG_UNAVAILABLE] interactiveLogin은 GUI가 필요합니다. /mnt/wslg 또는 DISPLAY/WAYLAND_DISPLAY를 찾지 못했습니다. ' +
      'Windows 11에서 WSLg를 활성화하고 `wsl --update` 후 재시도하세요.',
    );
  }

  throw new Error(
    '[ENV_NO_GUI] headed 모드(headless=false) 실행에 필요한 DISPLAY/WAYLAND_DISPLAY가 없습니다. ' +
    'GUI 환경(예: WSLg)을 활성화한 뒤 다시 실행하세요.',
  );
}

export interface SessionResult {
  browser: Browser | null;
  context: BrowserContext;
  page: Page;
  isPersistentProfile: boolean;
  profileDir?: string;
}

type ProfileDirResolveInput = {
  profileDir?: string;
  userDataDir?: string;
};

type ProfileDirEnsureResult = {
  path: string;
  exists: boolean;
  created: boolean;
};

interface SessionPreflightResult {
  ok: boolean;
  cookies_loaded: boolean;
  login_detected: boolean;
  auto_login_triggered: boolean;
  failure_reason?: LoginBlockedReason | 'SESSION_EXPIRED_OR_MISSING' | 'UNKNOWN';
  failure_detail?: string;
  recovery_guide?: string;
}

type LoginState = 'logged_in' | 'logged_out' | 'unknown';

interface LoginStateResult {
  state: LoginState;
  url: string;
  signal: string;
}

export type LoginProbe = {
  loginDetected: boolean;
  autoLoginTriggered: boolean;
  writeUrlReached: boolean;
  frameWriteReached: boolean;
  gotoRetried?: boolean;
  loginSignal?: string;
  blockReason?: string;
};

export class SessionBlockedError extends Error {
  readonly reason: string;
  readonly loginProbe: LoginProbe;
  readonly debugDir: string | null;

  constructor(reason: string, loginProbe: LoginProbe, debugDir: string | null) {
    super('[SESSION_BLOCKED_LOGIN_STUCK] 로그인 페이지 잔류로 진행 불가');
    this.name = 'SessionBlockedError';
    this.reason = reason;
    this.loginProbe = loginProbe;
    this.debugDir = debugDir;
  }
}

const NAVER_LOGIN_INDICATORS = [
  'iframe#mainFrame',            // 로그인된 블로그 메인
  '.se-toolbar',                 // SmartEditor 툴바
  '.blog_author',                // 블로그 작성자 정보
  'a[href*="logout"]',           // 로그아웃 링크
  '.MyView',                     // 네이버 메인 마이뷰
  '.area_profile',               // 프로필 영역
  'a[href*="naver.com/profile"]', // 프로필 링크
];

const NAVER_LOGOUT_INDICATORS = [
  '[data-clk="gnb.login"]',      // 네이버 로그인 버튼
  '#id',                         // 로그인 폼 ID 입력
  '.btn_login',                  // 로그인 버튼
  'input[name="id"]',            // 로그인 ID 필드
  '.login_title',                // 로그인 페이지 제목
];

const LOGIN_FORM_INDICATORS = ['#id', '#pw', '.btn_login', 'input[name="id"]'];
const NAVER_LOGIN_COOKIE_NAMES = ['NID_AUT', 'NID_SES'];

const WRITER_IFRAME_SELECTORS = ['iframe#mainFrame', 'iframe[id*="frame"]'];
const WRITER_NAVIGATION_TIMEOUT_MS = 30_000;
const LOGIN_STUCK_TIMEOUT_MS = Math.max(
  20_000,
  parseInt(process.env.NAVER_LOGIN_STUCK_TIMEOUT_MS ?? '25_000', 10),
);

export type LoginBlockedReason =
  | 'CAPTCHA_DETECTED'
  | 'TWO_FACTOR_REQUIRED'
  | 'SECURITY_CONFIRM_REQUIRED'
  | 'AGREEMENT_REQUIRED'
  | 'LOGIN_FORM_STILL_VISIBLE'
  | 'SESSION_BLOCKED_LOGIN_STUCK'
  | 'CROSS_OS_PROFILE_UNUSABLE';

type LoginBlockSignals = {
  captcha: boolean;
  twoFactor: boolean;
  securityConfirm: boolean;
  agreement: boolean;
  loginFormVisible: boolean;
};

type AutoLoginAttemptResult = {
  success: boolean;
  loginDetected: boolean;
  loginSignal: string;
  writeUrlReached: boolean;
  frameWriteReached: boolean;
  gotoRetried: boolean;
  failureReason?: LoginBlockedReason;
};
export type EnsureLoginMode = 'passive' | 'interactive_if_needed';
export type SessionCooldownState = {
  lastReason: LoginBlockedReason | null;
  lastTs: number;
  cooldownUntilTs: number;
  consecutiveFailures: number;
};
const DEFAULT_COOLDOWN_STATE: SessionCooldownState = {
  lastReason: null,
  lastTs: 0,
  cooldownUntilTs: 0,
  consecutiveFailures: 0,
};
const SESSION_COOLDOWN_FILENAME = 'session_cooldown.json';
const BROWSER_LAUNCH_TIMEOUT_MS = Math.max(
  5_000,
  parseInt(process.env.NAVER_BROWSER_LAUNCH_TIMEOUT_MS ?? '20_000', 10),
);
const BROWSER_LAUNCH_RETRIES = Math.max(
  0,
  parseInt(process.env.NAVER_BROWSER_LAUNCH_RETRIES ?? '1', 10),
);
const BROWSER_LAUNCH_RETRY_DELAY_MS = Math.max(
  100,
  parseInt(process.env.NAVER_BROWSER_LAUNCH_RETRY_DELAY_MS ?? '800', 10),
);

export async function launchContextWithRetry<T>(
  launchFn: () => Promise<T>,
  opts: {
    maxRetries: number;
    retryDelayMs: number;
    stageName: string;
  },
): Promise<T> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    try {
      return await launchFn();
    } catch (error) {
      lastError = error;
      const retryable = attempt < opts.maxRetries;
      log.warn(
        `[${opts.stageName}] attempt=${attempt + 1}/${opts.maxRetries + 1} failed: ${String(error)}`,
      );
      if (!retryable) break;
      await new Promise((resolve) => setTimeout(resolve, opts.retryDelayMs));
    }
  }

  throw new Error(
    `[BROWSER_LAUNCH_TIMEOUT] waitedFor=[launchPersistentContext], timeoutMs=${BROWSER_LAUNCH_TIMEOUT_MS}, ` +
    `retries=${opts.maxRetries}, lastError=${String(lastError)}`,
  );
}

export function isLoginRedirectUrl(url: string): boolean {
  return url.includes('nid.naver.com/nidlogin') || url.includes('logins.naver.com');
}

export function inferLoginBlockedReason(signals: LoginBlockSignals): LoginBlockedReason | null {
  if (signals.captcha) return 'CAPTCHA_DETECTED';
  if (signals.twoFactor) return 'TWO_FACTOR_REQUIRED';
  if (signals.securityConfirm) return 'SECURITY_CONFIRM_REQUIRED';
  if (signals.agreement) return 'AGREEMENT_REQUIRED';
  if (signals.loginFormVisible) return 'LOGIN_FORM_STILL_VISIBLE';
  return null;
}

function isCrossOsProfilePath(profileDir?: string): boolean {
  if (!profileDir) return false;
  return process.platform === 'linux' && /^\/mnt\/c\//i.test(path.resolve(profileDir));
}

export function detectCrossOsProfileUnusable(
  platform: string,
  profileDir: string | undefined,
  cookieNames: string[],
): boolean {
  if (platform !== 'linux') return false;
  if (!profileDir || !/^\/mnt\/c\//i.test(path.resolve(profileDir))) return false;
  if (cookieNames.length === 0) return true;
  const keyCookies = new Set(['NID_AUT', 'NID_SES']);
  return !cookieNames.some((name) => keyCookies.has(name));
}

function crossOsGuidance(): string {
  return [
    'Cross-OS profile detected and unusable in WSL.',
    '해결: WSL에서 etc_scripts/auth_save_state.js 실행 후 state.json을 사용하세요.',
  ].join(' ');
}

export function getSessionCooldownPath(userDataDir?: string): string {
  const baseDir = userDataDir
    ? path.resolve(userDataDir)
    : path.resolve(process.env.NAVER_USER_DATA_DIR ?? './.secrets/naver_user_data_dir');
  return path.join(baseDir, SESSION_COOLDOWN_FILENAME);
}

export function resolveProfileDir(input: ProfileDirResolveInput = {}): string {
  if (input.profileDir && input.profileDir.trim().length > 0) {
    return path.resolve(input.profileDir);
  }
  if (process.env.NAVER_PROFILE_DIR && process.env.NAVER_PROFILE_DIR.trim().length > 0) {
    return path.resolve(process.env.NAVER_PROFILE_DIR);
  }
  if (input.userDataDir && input.userDataDir.trim().length > 0) {
    return path.resolve(input.userDataDir);
  }
  if (process.env.NAVER_USER_DATA_DIR && process.env.NAVER_USER_DATA_DIR.trim().length > 0) {
    return path.resolve(process.env.NAVER_USER_DATA_DIR);
  }
  return path.resolve('./.secrets/naver_user_data_dir');
}

export function ensureProfileDir(profileDir: string): ProfileDirEnsureResult {
  const resolvedPath = path.resolve(profileDir);
  const existedBefore = fs.existsSync(resolvedPath);
  fs.mkdirSync(resolvedPath, { recursive: true });
  const existsAfter = fs.existsSync(resolvedPath);
  return {
    path: resolvedPath,
    exists: existsAfter,
    created: !existedBefore && existsAfter,
  };
}

export function detectProfileDirLock(profileDir: string): {
  lockDetected: boolean;
  lockPaths: string[];
} {
  const lockPaths = USER_DATA_DIR_LOCK_FILES
    .map((fileName) => path.join(profileDir, fileName))
    .filter((lockPath) => fs.existsSync(lockPath));
  return {
    lockDetected: lockPaths.length > 0,
    lockPaths,
  };
}

export function getSessionBackendLabel(opts: Pick<SessionOptions, 'profileDir' | 'userDataDir' | 'storageStatePath'>): string {
  const contextMode = (process.env.NAVER_CONTEXT_MODE ?? 'persistent').toLowerCase() === 'new_context'
    ? 'new_context'
    : 'persistent';
  if (contextMode === 'persistent') return 'persistent_profile';
  const storagePath = getStorageStatePath({
    userDataDir: resolveProfileDir({ profileDir: opts.profileDir, userDataDir: opts.userDataDir }),
    storageStatePath: opts.storageStatePath,
  });
  if (fs.existsSync(storagePath)) return 'storage_state';
  return 'cookies_only';
}

export function getStorageStatePath(opts: Pick<SessionOptions, 'userDataDir' | 'storageStatePath'>): string {
  if (opts.storageStatePath && opts.storageStatePath.trim().length > 0) {
    return path.resolve(opts.storageStatePath);
  }
  const baseDir = resolveProfileDir({ userDataDir: opts.userDataDir });
  return path.join(baseDir, DEFAULT_STORAGE_STATE_FILENAME);
}

function getStorageStateSummary(storageStatePath: string): StorageStateSummary {
  const resolvedPath = path.resolve(storageStatePath);
  if (!fs.existsSync(resolvedPath)) {
    return {
      path: resolvedPath,
      exists: false,
      fileSize: 0,
      cookieCount: 0,
    };
  }

  let cookieCount = 0;
  let fileSize = 0;
  try {
    fileSize = fs.statSync(resolvedPath).size;
  } catch {
    fileSize = 0;
  }
  try {
    const parsed = JSON.parse(fs.readFileSync(resolvedPath, 'utf-8')) as { cookies?: unknown[] };
    cookieCount = Array.isArray(parsed.cookies) ? parsed.cookies.length : 0;
  } catch {
    cookieCount = 0;
  }

  return {
    path: resolvedPath,
    exists: true,
    fileSize,
    cookieCount,
  };
}

function findUserDataDirLock(userDataDir: string): string | null {
  const detected = detectProfileDirLock(userDataDir);
  return detected.lockPaths[0] ?? null;
}

function isLikelyUserDataDirLockedError(error: unknown): boolean {
  const msg = String(error ?? '');
  return /singleton|profile.*in use|already in use|process_singleton|lock/i.test(msg);
}

export function loadSessionCooldown(cooldownPath: string): SessionCooldownState {
  try {
    if (!fs.existsSync(cooldownPath)) return { ...DEFAULT_COOLDOWN_STATE };
    const raw = JSON.parse(fs.readFileSync(cooldownPath, 'utf-8')) as Partial<SessionCooldownState>;
    return {
      lastReason: (raw.lastReason ?? null) as LoginBlockedReason | null,
      lastTs: Number(raw.lastTs ?? 0),
      cooldownUntilTs: Number(raw.cooldownUntilTs ?? 0),
      consecutiveFailures: Number(raw.consecutiveFailures ?? 0),
    };
  } catch {
    return { ...DEFAULT_COOLDOWN_STATE };
  }
}

export function saveSessionCooldown(cooldownPath: string, state: SessionCooldownState): void {
  fs.mkdirSync(path.dirname(cooldownPath), { recursive: true });
  fs.writeFileSync(cooldownPath, JSON.stringify(state, null, 2), 'utf-8');
}

export function clearSessionCooldown(userDataDir?: string): string {
  const cooldownPath = getSessionCooldownPath(userDataDir);
  try {
    fs.rmSync(cooldownPath, { force: true });
  } catch {
    // ignore
  }
  return cooldownPath;
}

/**
 * CAPTCHA 차단된 storageState를 .invalid.<ts>.json으로 이름 변경하여 격리한다.
 * interactiveLogin 성공 후 새 세션으로 덮어쓸 수 있도록 기존 파일을 무효화한다.
 */
export function backupInvalidStorageState(storageStatePath: string): string | null {
  try {
    const resolved = path.resolve(storageStatePath);
    if (!fs.existsSync(resolved)) {
      log.info(`[session] storageState 없음, 백업 생략: ${resolved}`);
      return null;
    }
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const base = resolved.replace(/\.json$/, '');
    const backupPath = `${base}.invalid.${ts}.json`;
    fs.renameSync(resolved, backupPath);
    log.info(`[session] CAPTCHA 차단 storageState 백업: ${backupPath}`);
    return backupPath;
  } catch (error) {
    log.warn(`[session] storageState 백업 실패: ${error}`);
    return null;
  }
}

export function buildCooldownState(
  prev: SessionCooldownState,
  reason: LoginBlockedReason,
  nowMs: number = Date.now(),
): SessionCooldownState {
  let cooldownMs = 0;
  if (reason === 'CAPTCHA_DETECTED') cooldownMs = 12 * 60 * 60 * 1000;
  else if (reason === 'LOGIN_FORM_STILL_VISIBLE') cooldownMs = 15 * 60 * 1000;
  else if (
    reason === 'TWO_FACTOR_REQUIRED'
    || reason === 'SECURITY_CONFIRM_REQUIRED'
    || reason === 'AGREEMENT_REQUIRED'
  ) cooldownMs = 24 * 60 * 60 * 1000;
  return {
    lastReason: reason,
    lastTs: nowMs,
    cooldownUntilTs: nowMs + cooldownMs,
    consecutiveFailures: Math.max(1, prev.consecutiveFailures + 1),
  };
}

export function isCooldownActive(state: SessionCooldownState, nowMs: number = Date.now()): boolean {
  return state.cooldownUntilTs > nowMs;
}

export function getSessionCooldownStatus(userDataDir?: string): {
  active: boolean;
  state: SessionCooldownState;
  path: string;
} {
  const pathValue = getSessionCooldownPath(userDataDir);
  const state = loadSessionCooldown(pathValue);
  return { active: isCooldownActive(state), state, path: pathValue };
}

export function formatInteractiveLoginGuide(cooldownUntilTs?: number): string {
  const base = '자동화 중단: interactiveLogin 필요 (node dist/cli/post_to_naver.js --interactiveLogin)';
  if (!cooldownUntilTs || cooldownUntilTs <= Date.now()) return base;
  return `${base}, cooldownUntil=${new Date(cooldownUntilTs).toISOString()}`;
}

function describeSessionFailureReason(reason: SessionPreflightResult['failure_reason']): string {
  if (reason === 'CAPTCHA_DETECTED') return '보안문자(CAPTCHA) 확인이 필요합니다.';
  if (reason === 'TWO_FACTOR_REQUIRED') return '2단계 인증(OTP) 확인이 필요합니다.';
  if (reason === 'SECURITY_CONFIRM_REQUIRED') return '보안 확인(새 기기/본인확인)이 필요합니다.';
  if (reason === 'AGREEMENT_REQUIRED') return '약관/동의 확인이 필요합니다.';
  if (reason === 'LOGIN_FORM_STILL_VISIBLE') return '로그인 폼이 계속 노출됩니다.';
  if (reason === 'CROSS_OS_PROFILE_UNUSABLE') return 'WSL 외부 프로필을 재사용할 수 없습니다.';
  if (reason === 'SESSION_EXPIRED_OR_MISSING') return '저장된 세션이 없거나 만료되었습니다.';
  if (reason === 'SESSION_BLOCKED_LOGIN_STUCK') return '로그인 리다이렉트 상태에서 진행이 멈췄습니다.';
  return '로그인 상태를 확인하지 못했습니다.';
}

async function saveSessionFailureArtifacts(
  page: Page,
  reason: string,
  detail: string,
): Promise<string | null> {
  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const dir = path.resolve('./artifacts/session_failures', `${timestamp}_${reason}`);
    fs.mkdirSync(dir, { recursive: true });

    const screenshotPath = path.join(dir, '01_page.png');
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => undefined);

    const htmlPath = path.join(dir, '02_page.html');
    const html = await page.content().catch(() => '');
    fs.writeFileSync(htmlPath, html, 'utf-8');

    const metaPath = path.join(dir, '00_meta.json');
    const meta = {
      reason,
      detail,
      page_url: page.url(),
      at: new Date().toISOString(),
    };
    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2), 'utf-8');
    return dir;
  } catch {
    return null;
  }
}

async function selectorExists(page: Page, selector: string): Promise<boolean> {
  try {
    return (await page.locator(selector).first().count()) > 0;
  } catch {
    return false;
  }
}

async function detectAnySelector(page: Page, selectors: string[]): Promise<string | null> {
  for (const selector of selectors) {
    if (await selectorExists(page, selector)) {
      return selector;
    }
  }
  return null;
}

export function classifyLoginState(
  url: string,
  hasWriterFrame: boolean,
  matchedLoginIndicator: string | null,
  matchedLogoutIndicator: string | null,
  hasLoginCookie: boolean,
): LoginStateResult {
  if (hasWriterFrame) {
    return { state: 'logged_in', url, signal: 'writer_iframe' };
  }
  if (matchedLoginIndicator) {
    return { state: 'logged_in', url, signal: `login_indicator:${matchedLoginIndicator}` };
  }
  if (hasLoginCookie) {
    return { state: 'logged_in', url, signal: 'login_cookie_present' };
  }
  if (matchedLogoutIndicator) {
    return { state: 'logged_out', url, signal: `logout_indicator:${matchedLogoutIndicator}` };
  }
  if (isLoginRedirectUrl(url)) {
    return { state: 'unknown', url, signal: 'login_redirect_url_transient' };
  }
  return { state: 'unknown', url, signal: 'no_indicator' };
}

async function navigateToWriter(page: Page, writeUrl: string): Promise<void> {
  await page.goto(writeUrl, {
    waitUntil: 'domcontentloaded',
    timeout: WRITER_NAVIGATION_TIMEOUT_MS,
  });
}

function isWriteSurfaceUrl(url: string): boolean {
  return /Redirect=Write|PostWriteForm|SmartEditor/i.test(url);
}

export async function probeWriteSurface(
  page: Page,
  writeUrl: string,
): Promise<{ writeUrlReached: boolean; frameWriteReached: boolean }> {
  let writeUrlReached = false;
  let frameWriteReached = false;
  try {
    const currentUrl = page.url();
    writeUrlReached = currentUrl.includes('Redirect=Write') || currentUrl.includes(writeUrl);
  } catch {
    writeUrlReached = false;
  }
  try {
    frameWriteReached = page.frames().some((f) => isWriteSurfaceUrl(f.url()));
  } catch {
    frameWriteReached = false;
  }
  return { writeUrlReached, frameWriteReached };
}

async function waitForWriteSurfaceReach(
  page: Page,
  writeUrl: string,
  timeoutMs: number,
): Promise<{ writeUrlReached: boolean; frameWriteReached: boolean }> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const probe = await probeWriteSurface(page, writeUrl);
    if (probe.writeUrlReached || probe.frameWriteReached) return probe;
    await page.waitForTimeout(400).catch(() => undefined);
  }
  return await probeWriteSurface(page, writeUrl);
}

async function detectLoginBlockSignals(page: Page): Promise<LoginBlockSignals> {
  const hasAny = async (selectors: string[]): Promise<boolean> => {
    for (const sel of selectors) {
      if (await selectorExists(page, sel)) return true;
    }
    return false;
  };
  const text = await page.evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' ')).catch(() => '');
  const captcha = await hasAny([
    '#captcha_image',
    '.captcha',
    'iframe[src*="captcha"]',
    'iframe[title*="captcha"]',
    'img[alt*="캡차"]',
  ]) || /캡차|보안문자|자동입력방지/i.test(text);
  const twoFactor = await hasAny([
    'input[placeholder*="인증번호"]',
    'input[name*="otp"]',
    'input[id*="otp"]',
    '.phone_verify',
  ]) || /2단계|OTP|일회용|인증번호/i.test(text);
  const securityConfirm = /본인확인|보안.*확인|새로운 기기|보호조치|추가 인증/i.test(text);
  const agreement = /약관|동의.*필요|서비스 이용약관/i.test(text);
  const loginFormVisible = await hasAny(LOGIN_FORM_INDICATORS) || isLoginRedirectUrl(page.url());
  return { captcha, twoFactor, securityConfirm, agreement, loginFormVisible };
}

async function waitForWriteSurfaceReachWithRetry(
  page: Page,
  writeUrl: string,
  timeoutMs: number,
): Promise<{ writeUrlReached: boolean; frameWriteReached: boolean; gotoRetried: boolean }> {
  const half = Math.max(1_000, Math.floor(timeoutMs / 2));
  const first = await waitForWriteSurfaceReach(page, writeUrl, half);
  if (first.writeUrlReached || first.frameWriteReached) {
    return { ...first, gotoRetried: false };
  }
  await navigateToWriter(page, writeUrl).catch(() => undefined);
  const second = await waitForWriteSurfaceReach(page, writeUrl, timeoutMs - half);
  return { ...second, gotoRetried: true };
}

async function collectSessionBlockedDebug(
  page: Page,
  reason: string,
  loginProbe: LoginProbe,
): Promise<string | null> {
  try {
    const frame = page.frame('mainFrame') ?? page.frames().find((f) => isWriteSurfaceUrl(f.url())) ?? null;
    const { debugDir } = await collectTimeoutDebugArtifacts({
      page,
      frame,
      reason,
      currentStage: 'session_login',
      lastActivityLabel: 'session_login',
      lastActivityAgeMs: 0,
      watchdogLimitSeconds: 0,
      silenceWatchdogSeconds: 0,
      editorReadyProbe: null,
      loginProbe,
      loginState: null,
      iframeProbe: null,
      debugRootDir: ensureDebugRootDir('navertimeoutdebug'),
    });
    return debugDir;
  } catch (error) {
    log.error(`[session] session blocked debug collect failed: ${error}`);
    return null;
  }
}

export async function buildSessionBlockedError(
  page: Page,
  writeUrl: string,
  loginDetected: boolean,
  autoLoginTriggered: boolean,
  reason: LoginBlockedReason = 'SESSION_BLOCKED_LOGIN_STUCK',
  extras?: Partial<LoginProbe>,
  timeoutMs: number = LOGIN_STUCK_TIMEOUT_MS,
): Promise<SessionBlockedError> {
  const writeSurface = extras?.writeUrlReached === undefined || extras?.frameWriteReached === undefined
    ? await waitForWriteSurfaceReach(page, writeUrl, timeoutMs)
    : {
      writeUrlReached: Boolean(extras.writeUrlReached),
      frameWriteReached: Boolean(extras.frameWriteReached),
    };
  const loginProbe: LoginProbe = {
    loginDetected,
    autoLoginTriggered,
    writeUrlReached: writeSurface.writeUrlReached,
    frameWriteReached: writeSurface.frameWriteReached,
    gotoRetried: extras?.gotoRetried,
    loginSignal: extras?.loginSignal,
    blockReason: extras?.blockReason ?? reason,
  };
  const debugDir = await collectSessionBlockedDebug(
    page,
    reason,
    loginProbe,
  );
  return new SessionBlockedError(reason, loginProbe, debugDir);
}

export async function detectLoginState(page: Page): Promise<LoginStateResult> {
  const url = page.url();
  const cookies = await page.context().cookies('https://www.naver.com').catch(() => []);
  const cookieNames = new Set(cookies.map((cookie) => cookie.name));
  const hasLoginCookie = NAVER_LOGIN_COOKIE_NAMES.some((cookieName) => cookieNames.has(cookieName));
  const writerFrameSelector = await detectAnySelector(page, WRITER_IFRAME_SELECTORS);
  const logoutSelector = await detectAnySelector(page, NAVER_LOGOUT_INDICATORS);
  const loginSelector = await detectAnySelector(page, NAVER_LOGIN_INDICATORS);

  return classifyLoginState(
    url,
    !!writerFrameSelector,
    loginSelector,
    logoutSelector,
    hasLoginCookie,
  );
}

async function restoreStorageStateToPersistentContext(
  context: BrowserContext,
  storageStatePath: string,
): Promise<StorageStateLoadResult> {
  const summary = getStorageStateSummary(storageStatePath);
  if (!summary.exists) {
    return { ...summary, loaded: false, mode: 'none', reason: 'file_not_found' };
  }

  try {
    const raw = JSON.parse(fs.readFileSync(summary.path, 'utf-8')) as {
      cookies?: Array<{
        name: string;
        value: string;
        domain: string;
        path: string;
        expires: number;
        httpOnly: boolean;
        secure: boolean;
        sameSite: 'Strict' | 'Lax' | 'None';
      }>;
      origins?: Array<{
        origin: string;
        localStorage: Array<{ name: string; value: string }>;
      }>;
    };

    if (Array.isArray(raw.cookies) && raw.cookies.length > 0) {
      await context.addCookies(raw.cookies);
    }
    if (Array.isArray(raw.origins) && raw.origins.length > 0) {
      const lsSnapshot: Record<string, Record<string, string>> = {};
      for (const origin of raw.origins) {
        lsSnapshot[origin.origin] = {};
        for (const entry of origin.localStorage || []) {
          lsSnapshot[origin.origin][entry.name] = entry.value;
        }
      }
      await context.addInitScript((snapshot: Record<string, Record<string, string>>) => {
        try {
          const current = snapshot[window.location.origin];
          if (!current) return;
          for (const [k, v] of Object.entries(current)) {
            localStorage.setItem(k, v);
          }
        } catch {
          // ignore
        }
      }, lsSnapshot);
    }

    return {
      ...summary,
      loaded: true,
      mode: 'persistent',
    };
  } catch (error) {
    return {
      ...summary,
      loaded: false,
      mode: 'persistent',
      reason: String(error),
    };
  }
}

export function resolveNewContextStorageStateOption(
  storageStatePath: string,
): { storageStateOption?: string; loadResult: StorageStateLoadResult } {
  const summary = getStorageStateSummary(storageStatePath);
  if (!summary.exists) {
    return {
      loadResult: {
        ...summary,
        loaded: false,
        mode: 'none',
        reason: 'file_not_found',
      },
    };
  }

  return {
    storageStateOption: summary.path,
    loadResult: {
      ...summary,
      loaded: true,
      mode: 'new_context',
    },
  };
}

/**
 * persistent context 방식으로 브라우저 세션을 생성/복원한다.
 * userDataDir에 브라우저 프로필(쿠키 포함)이 유지된다.
 */
export async function createPersistentSession(opts: SessionOptions): Promise<SessionResult> {
  const launchStarted = Date.now();
  log.info('[timing] step=browser_launch_start elapsed=0.0s');
  const userDataDir = resolveProfileDir({ profileDir: opts.profileDir, userDataDir: opts.userDataDir });
  let profileDirExists = false;
  let profileDirCreated = false;
  try {
    const ensured = ensureProfileDir(userDataDir);
    profileDirExists = ensured.exists;
    profileDirCreated = ensured.created;
    log.info(`[session] profile_dir_exists=${ensured.exists} created=${ensured.created} profile_dir=${ensured.path}`);
  } catch (error) {
    log.error(`[session] profile_dir_create_failed path=${userDataDir} reason=${String(error)}`);
    throw error;
  }
  const storageStatePath = getStorageStatePath(opts);
  const webStorageSnapshotPath = getWebStorageSnapshotPath(storageStatePath);
  const webStorageSnapshot = readWebStorageSnapshot(webStorageSnapshotPath);
  const contextMode = (process.env.NAVER_CONTEXT_MODE ?? 'persistent').toLowerCase() === 'new_context'
    ? 'new_context'
    : 'persistent';

  // 환경변수 기반 headless 결정 (기본: true)
  const headless = opts.headless ?? (process.env.HEADLESS !== 'false');
  validateDisplayEnvironment(headless);

  log.info(`세션 디렉토리: ${userDataDir}`);
  log.info(`브라우저 모드: ${headless ? 'headless' : 'headed'}`);
  const lockInfo = detectProfileDirLock(userDataDir);
  if (lockInfo.lockDetected) {
    log.warn(`[session] user_data_dir_lock_hint paths=${lockInfo.lockPaths.join(',')}`);
  }

  let browser: Browser | null = null;
  let context: BrowserContext;
  let storageStateLoad: StorageStateLoadResult;
  let isPersistentProfile = false;

  try {
    if (contextMode === 'new_context') {
      browser = await launchContextWithRetry(
        async () => chromium.launch({
          headless,
          slowMo: opts.slowMo ?? 0,
          timeout: BROWSER_LAUNCH_TIMEOUT_MS,
          args: ['--disable-blink-features=AutomationControlled'],
        }),
        {
          maxRetries: BROWSER_LAUNCH_RETRIES,
          retryDelayMs: BROWSER_LAUNCH_RETRY_DELAY_MS,
          stageName: 'browser_launch_and_session_load',
        },
      );
      const { storageStateOption, loadResult } = resolveNewContextStorageStateOption(storageStatePath);
      storageStateLoad = loadResult;
      context = await browser.newContext({
        viewport: { width: 1400, height: 900 },
        locale: 'ko-KR',
        userAgent:
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ...(storageStateOption ? { storageState: storageStateOption } : {}),
      });
      isPersistentProfile = false;
    } else {
      context = await launchContextWithRetry(
        async () => chromium.launchPersistentContext(userDataDir, {
          headless,
          slowMo: opts.slowMo ?? 0,
          timeout: BROWSER_LAUNCH_TIMEOUT_MS,
          viewport: { width: 1400, height: 900 },
          locale: 'ko-KR',
          userAgent:
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          args: [
            '--disable-blink-features=AutomationControlled',
          ],
        }),
        {
          maxRetries: BROWSER_LAUNCH_RETRIES,
          retryDelayMs: BROWSER_LAUNCH_RETRY_DELAY_MS,
          stageName: 'browser_launch_and_session_load',
        },
      );
      storageStateLoad = await restoreStorageStateToPersistentContext(context, storageStatePath);
      isPersistentProfile = true;
    }
  } catch (error) {
    const latestLockHint = findUserDataDirLock(userDataDir);
    if (latestLockHint || isLikelyUserDataDirLockedError(error)) {
      log.error('[session] reason=USER_DATA_DIR_LOCKED: 다른 크롬/자동화가 동일 프로필을 사용 중인지 확인하세요.');
      log.error('[session] guide=사용 중 프로세스를 모두 종료한 뒤 재시도하세요.');
      log.error('[session] guide=브라우저 완전 종료를 확인한 후에만 남은 Singleton* 파일 삭제를 검토하세요(자동 삭제 금지).');
      throw new Error(
        `[session] reason=USER_DATA_DIR_LOCKED userDataDir=${userDataDir} lockPath=${latestLockHint ?? 'unknown'} message=${String(error)}`,
      );
    }
    throw error;
  }

  if (Object.keys(webStorageSnapshot).length > 0) {
    await context.addInitScript((snapshot: WebStorageSnapshot) => {
      try {
        const current = snapshot[window.location.origin];
        if (!current) return;
        for (const [k, v] of Object.entries(current.localStorage || {})) {
          localStorage.setItem(k, v);
        }
        for (const [k, v] of Object.entries(current.sessionStorage || {})) {
          sessionStorage.setItem(k, v);
        }
      } catch {
        // ignore restore failures
      }
    }, webStorageSnapshot);
  }

  const page = context.pages()[0] ?? (await context.newPage());
  const cookieCount = (await context.cookies('https://www.naver.com')).length;
  log.info(`[session] backend=${contextMode === 'new_context' ? 'storage_state' : 'cookies_only'}`);
  log.info(`[session] cookies_loaded=${cookieCount > 0} cookie_count=${cookieCount}`);
  if (storageStateLoad.reason) {
    log.warn(`[session] storage_state_load_reason=${storageStateLoad.reason}`);
  }
  log.info(
    `[session] storage_state_loaded=${storageStateLoad.loaded} mode=${storageStateLoad.mode} ` +
    `path=${storageStateLoad.path} file_size=${storageStateLoad.fileSize} cookie_count=${storageStateLoad.cookieCount}`,
  );
  log.info(`[session] PERSISTENT_PROFILE_ENABLED=${isPersistentProfile} userDataDir=${userDataDir}`);
  log.info(`[session] persistent_profile=${isPersistentProfile} profile_dir=${userDataDir}`);
  log.info(`[session] profile_dir_exists=${profileDirExists} created=${profileDirCreated}`);
  if (!isPersistentProfile) {
    log.warn('[session] persistent profile disabled: backend=new_context(storageState fallback)');
  }
  log.info(`[timing] step=browser_launch_complete elapsed=${((Date.now() - launchStarted) / 1000).toFixed(1)}s`);
  return {
    browser,
    context,
    page,
    isPersistentProfile,
    profileDir: userDataDir,
  };
}

/**
 * 현재 페이지가 네이버에 로그인된 상태인지 확인한다.
 * 글쓰기 페이지에서 에디터 요소가 보이면 로그인된 것으로 판단.
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
  try {
    const state = await detectLoginState(page);
    log.info(`로그인 상태 확인 중 - URL: ${state.url}`);
    log.info(`[session] login_state=${state.state} signal=${state.signal}`);
    return state.state === 'logged_in';
  } catch (error) {
    log.warn(`로그인 상태 확인 중 오류: ${error}`);
    return false;
  }
}

async function attemptCredentialLoginOnCurrentPage(page: Page, writeUrl: string): Promise<AutoLoginAttemptResult> {
  const naverId = process.env.NAVER_ID;
  const naverPw = process.env.NAVER_PW;
  if (!naverId || !naverPw) {
    log.error('[session] NAVER_ID/NAVER_PW 미설정: 자동 로그인 불가');
    return {
      success: false,
      loginDetected: false,
      loginSignal: 'credentials_missing',
      writeUrlReached: false,
      frameWriteReached: false,
      gotoRetried: false,
      failureReason: 'LOGIN_FORM_STILL_VISIBLE',
    };
  }

  try {
    if (!isLoginRedirectUrl(page.url())) {
      await page.goto('https://nid.naver.com/nidlogin.login', {
        waitUntil: 'domcontentloaded',
        timeout: 30_000,
      });
    }

    await page.waitForSelector('#id', { timeout: 10_000 });
    await page.fill('#id', naverId);
    await page.waitForSelector('#pw', { timeout: 5_000 });
    await page.fill('#pw', naverPw);
    await page.click('.btn_login');
    await page.waitForURL((url) => !isLoginRedirectUrl(url.toString()), { timeout: 15_000 }).catch(() => undefined);

    const blockSignals = await detectLoginBlockSignals(page);
    const blockedReason = inferLoginBlockedReason(blockSignals);
    if (blockedReason) {
      const blockedUrl = page.url();
      const blockedTitle = await page.title().catch(() => 'title_unavailable');
      log.error(`[session] 로그인 차단 신호 감지: ${blockedReason}`);
      log.error(`[session] blocked_url=${blockedUrl} blocked_title=${blockedTitle}`);
      if (blockedReason === 'AGREEMENT_REQUIRED') {
        const agreementDebugDir = await collectSessionBlockedDebug(page, blockedReason, {
          loginDetected: false,
          autoLoginTriggered: true,
          writeUrlReached: false,
          frameWriteReached: false,
          gotoRetried: false,
          loginSignal: `blocked:${blockedReason}`,
          blockReason: blockedReason,
        });
        log.error(`[session] agreement_debug_dir=${agreementDebugDir ?? 'n/a'}`);
      }
      return {
        success: false,
        loginDetected: false,
        loginSignal: `blocked:${blockedReason}`,
        writeUrlReached: false,
        frameWriteReached: false,
        gotoRetried: false,
        failureReason: blockedReason,
      };
    }

    const loginState = await detectLoginState(page);
    const loginDetected = loginState.state === 'logged_in';
    log.info(`[session] login_state=${loginState.state} signal=${loginState.signal}`);
    if (!loginDetected) {
      return {
        success: false,
        loginDetected: false,
        loginSignal: loginState.signal,
        writeUrlReached: false,
        frameWriteReached: false,
        gotoRetried: false,
        failureReason: 'LOGIN_FORM_STILL_VISIBLE',
      };
    }

    const writeSurface = await waitForWriteSurfaceReachWithRetry(page, writeUrl, LOGIN_STUCK_TIMEOUT_MS);
    if (writeSurface.writeUrlReached || writeSurface.frameWriteReached) {
      return {
        success: true,
        loginDetected: true,
        loginSignal: loginState.signal,
        writeUrlReached: writeSurface.writeUrlReached,
        frameWriteReached: writeSurface.frameWriteReached,
        gotoRetried: writeSurface.gotoRetried,
      };
    }
    return {
      success: false,
      loginDetected: true,
      loginSignal: loginState.signal,
      writeUrlReached: false,
      frameWriteReached: false,
      gotoRetried: writeSurface.gotoRetried,
      failureReason: 'SESSION_BLOCKED_LOGIN_STUCK',
    };
  } catch (error) {
    log.warn(`현재 컨텍스트 자동 로그인 실패: ${error}`);
    return {
      success: false,
      loginDetected: false,
      loginSignal: `exception:${String(error)}`,
      writeUrlReached: false,
      frameWriteReached: false,
      gotoRetried: false,
      failureReason: 'LOGIN_FORM_STILL_VISIBLE',
    };
  }
}

export async function ensureLoggedIn(
  session: SessionResult,
  opts: SessionOptions,
  writeUrl: string,
  mode: EnsureLoginMode = 'passive',
): Promise<{
  ok: boolean;
  loginDetected: boolean;
  autoLoginAttempted: boolean;
  signal: string;
}> {
  const cooldownPath = getSessionCooldownPath(opts.userDataDir);
  const cooldownState = loadSessionCooldown(cooldownPath);
  const { page, context } = session;
  const cookieNames = (await context.cookies('https://www.naver.com').catch(() => []))
    .map((c) => c.name);
  if (detectCrossOsProfileUnusable(process.platform, session.profileDir ?? opts.userDataDir, cookieNames)) {
    log.error(`[session] reason=CROSS_OS_PROFILE_UNUSABLE profileDir=${session.profileDir ?? opts.userDataDir}`);
    log.error(`[session] guide=${crossOsGuidance()}`);
    const reason: LoginBlockedReason = 'CROSS_OS_PROFILE_UNUSABLE';
    const blockedError = await buildSessionBlockedError(
      page,
      writeUrl,
      false,
      false,
      reason,
      {
        writeUrlReached: false,
        frameWriteReached: false,
        gotoRetried: false,
        loginSignal: 'cross_os_profile_unusable',
        blockReason: reason,
      },
      1_000,
    );
    throw blockedError;
  }

  await navigateToWriter(page, writeUrl).catch(() => undefined);
  const surfaceProbeAfterNavigate = await waitForWriteSurfaceReach(page, writeUrl, 4_000).catch(() => ({
    writeUrlReached: false,
    frameWriteReached: false,
  }));
  if (surfaceProbeAfterNavigate.frameWriteReached && !isLoginRedirectUrl(page.url())) {
    saveSessionCooldown(cooldownPath, {
      ...DEFAULT_COOLDOWN_STATE,
      lastReason: cooldownState.lastReason,
      lastTs: cooldownState.lastTs,
    });
    return {
      ok: true,
      loginDetected: true,
      autoLoginAttempted: false,
      signal: 'writer_surface_fastpath',
    };
  }

  let loginState = await detectLoginState(page);
  if (loginState.state === 'logged_in') {
    saveSessionCooldown(cooldownPath, {
      ...DEFAULT_COOLDOWN_STATE,
      lastReason: cooldownState.lastReason,
      lastTs: cooldownState.lastTs,
    });
    return { ok: true, loginDetected: true, autoLoginAttempted: false, signal: loginState.signal };
  }

  if (mode === 'passive' && isCooldownActive(cooldownState)) {
    const reason = cooldownState.lastReason ?? 'SESSION_BLOCKED_LOGIN_STUCK';
    const blockedError = await buildSessionBlockedError(
      page,
      writeUrl,
      false,
      false,
      reason,
      {
        writeUrlReached: false,
        frameWriteReached: false,
        gotoRetried: false,
        loginSignal: 'cooldown_active',
        blockReason: reason,
      },
      1_000,
    );
    throw blockedError;
  }

  const attempt = await attemptCredentialLoginOnCurrentPage(page, writeUrl);
  if (!attempt.success) {
    const reason = attempt.failureReason ?? 'SESSION_BLOCKED_LOGIN_STUCK';
    const nextCooldown = buildCooldownState(cooldownState, reason);
    saveSessionCooldown(cooldownPath, nextCooldown);
    const blockedError = await buildSessionBlockedError(
      page,
      writeUrl,
      attempt.loginDetected,
      true,
      reason,
      {
        writeUrlReached: attempt.writeUrlReached,
        frameWriteReached: attempt.frameWriteReached,
        gotoRetried: attempt.gotoRetried,
        loginSignal: attempt.loginSignal,
        blockReason: reason,
      },
    );
    throw blockedError;
  }

  saveSessionCooldown(cooldownPath, {
    ...DEFAULT_COOLDOWN_STATE,
    lastReason: cooldownState.lastReason,
    lastTs: cooldownState.lastTs,
  });
  loginState = await detectLoginState(page);
  if (loginState.state === 'logged_in') {
    await persistSessionState(context, page, getStorageStatePath(opts));
    return {
      ok: true,
      loginDetected: true,
      autoLoginAttempted: true,
      signal: loginState.signal,
    };
  }

  const lateSurfaceProbe = await probeWriteSurface(page, writeUrl).catch(() => ({
    writeUrlReached: false,
    frameWriteReached: false,
  }));
  if (lateSurfaceProbe.frameWriteReached && !isLoginRedirectUrl(page.url())) {
    await persistSessionState(context, page, getStorageStatePath(opts)).catch(() => undefined);
    return {
      ok: true,
      loginDetected: true,
      autoLoginAttempted: true,
      signal: 'writer_surface_after_login_attempt',
    };
  }

  return {
    ok: false,
    loginDetected: false,
    autoLoginAttempted: true,
    signal: loginState.signal,
  };
}

export async function persistSessionState(
  context: BrowserContext,
  page: Page,
  storageStatePath?: string
): Promise<void> {
  if (!storageStatePath) return;
  try {
    const statePath = path.resolve(storageStatePath);
    fs.mkdirSync(path.dirname(statePath), { recursive: true });
    await context.storageState({ path: statePath });

    const snapshotPath = getWebStorageSnapshotPath(statePath);
    const snapshot = readWebStorageSnapshot(snapshotPath);
    const origin = new URL(page.url()).origin;
    const originStorage = await page.evaluate(() => {
      const localData: Record<string, string> = {};
      const sessionData: Record<string, string> = {};
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key) localData[key] = localStorage.getItem(key) || '';
      }
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key) sessionData[key] = sessionStorage.getItem(key) || '';
      }
      return { localStorage: localData, sessionStorage: sessionData };
    }).catch(() => ({ localStorage: {}, sessionStorage: {} }));
    snapshot[origin] = originStorage;
    fs.writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2), 'utf-8');

    const summary = getStorageStateSummary(statePath);
    if (summary.fileSize === 0) {
      log.warn(`[session] storage_state_saved_zero_bytes path=${summary.path}`);
    }
    log.info(
      `[session] storage_state_saved=true path=${summary.path} file_size=${summary.fileSize} cookie_count=${summary.cookieCount}`,
    );
  } catch (error) {
    log.warn(`[session] storage_state_saved=false reason=${error}`);
  }
}

export async function preflightSessionForUpload(
  session: SessionResult,
  opts: SessionOptions,
  writeUrl: string
): Promise<SessionPreflightResult> {
  const { context, page } = session;
  const storageStatePath = getStorageStatePath(opts);
  const storageSummary = getStorageStateSummary(storageStatePath);
  const recoveryGuide = `${describeSessionFailureReason('SESSION_EXPIRED_OR_MISSING')} ${formatInteractiveLoginGuide()}`;
  try {
    const cookieCount = (await context.cookies('https://www.naver.com')).length;
    const cookiesLoaded = cookieCount > 0;
    log.info(`[session] cookies_loaded=${cookiesLoaded}`);
    await navigateToWriter(page, writeUrl);
    const loginState = await detectLoginState(page);
    const loginDetected = loginState.state === 'logged_in';
    log.info(`[session] login_detected=${loginDetected} signal=${loginState.signal}`);
    if (!loginDetected) {
      const noSession = !cookiesLoaded && !storageSummary.exists;
      const failureReason = noSession ? 'SESSION_EXPIRED_OR_MISSING' : 'UNKNOWN';
      const failureDetail = noSession
        ? `세션 파일 없음 path=${storageSummary.path}`
        : `login_state=${loginState.state} signal=${loginState.signal}`;
      const failureArtifacts = await saveSessionFailureArtifacts(
        page,
        String(failureReason).toLowerCase(),
        failureDetail,
      );
      if (failureArtifacts) {
        log.warn(`[session] preflight_failure_artifacts=${failureArtifacts}`);
      }
      return {
        ok: false,
        cookies_loaded: cookiesLoaded,
        login_detected: false,
        auto_login_triggered: false,
        failure_reason: failureReason,
        failure_detail: failureDetail,
        recovery_guide: recoveryGuide,
      };
    }
    return {
      ok: true,
      cookies_loaded: cookiesLoaded,
      login_detected: true,
      auto_login_triggered: false,
    };
  } catch (error) {
    if (error instanceof SessionBlockedError) {
      const failureArtifacts = await saveSessionFailureArtifacts(
        page,
        String(error.reason).toLowerCase(),
        `blocked_reason=${error.reason} login_signal=${error.loginProbe.loginSignal ?? 'unknown'}`,
      );
      if (failureArtifacts) {
        log.warn(`[session] preflight_failure_artifacts=${failureArtifacts}`);
      }
      return {
        ok: false,
        cookies_loaded: false,
        login_detected: false,
        auto_login_triggered: false,
        failure_reason: error.reason as LoginBlockedReason,
        failure_detail: `blocked_reason=${error.reason} login_signal=${error.loginProbe.loginSignal ?? 'unknown'}`,
        recovery_guide: `${describeSessionFailureReason(error.reason as LoginBlockedReason)} ${formatInteractiveLoginGuide()}`,
      };
    }

    log.warn(`세션 사전 검증 실패: ${error}`);
    const failureArtifacts = await saveSessionFailureArtifacts(
      page,
      'unknown',
      String(error),
    );
    if (failureArtifacts) {
      log.warn(`[session] preflight_failure_artifacts=${failureArtifacts}`);
    }
    return {
      ok: false,
      cookies_loaded: false,
      login_detected: false,
      auto_login_triggered: false,
      failure_reason: 'UNKNOWN',
      failure_detail: String(error),
      recovery_guide: recoveryGuide,
    };
  }
}

export function formatSessionPreflightFailure(result: SessionPreflightResult): string {
  const reason = result.failure_reason ?? 'UNKNOWN';
  const reasonText = describeSessionFailureReason(reason);
  const detail = result.failure_detail ? `detail=${result.failure_detail}` : 'detail=none';
  const guide = result.recovery_guide ?? formatInteractiveLoginGuide();
  return `로그인 필요: reason=${reason} (${reasonText}) ${detail}. 해결: ${guide}`;
}

export async function recoverExpiredSession(
  session: SessionResult,
  opts: SessionOptions,
  writeUrl: string
): Promise<SessionPreflightResult> {
  const { context, page } = session;
  log.info('[session] auto_login_triggered=true');
  const recovered = await ensureLoggedIn(session, opts, writeUrl, 'passive');
  const cookiesLoaded = (await context.cookies('https://www.naver.com')).length > 0;
  const loginState = recovered.ok ? await detectLoginState(page) : { state: 'logged_out' as LoginState };
  const loginDetected = recovered.ok && loginState.state === 'logged_in';
  if (recovered.ok) {
    await persistSessionState(context, page, getStorageStatePath(opts));
  }
  return {
    ok: recovered.ok && loginDetected,
    cookies_loaded: cookiesLoaded,
    login_detected: loginDetected,
    auto_login_triggered: recovered.autoLoginAttempted,
  };
}

/**
 * 자동 로그인 기능.
 * 환경변수에서 계정 정보를 읽어 자동으로 로그인한다.
 */
export async function autoLogin(opts: SessionOptions): Promise<boolean> {
  const loginStarted = Date.now();
  log.info('[timing] step=login_start elapsed=0.0s');
  if (!process.env.NAVER_ID || !process.env.NAVER_PW) {
    log.error('자동 로그인을 위한 환경변수가 설정되지 않았습니다: NAVER_ID, NAVER_PW');
    return false;
  }

  log.info('=== 자동 로그인 시작 ===');

  const { context, page, browser } = await createPersistentSession({
    ...opts,
    headless: opts.headless ?? true, // 자동 로그인은 기본적으로 headless
  });

  try {
    const writeUrl =
      process.env.NAVER_WRITE_URL ??
      `https://blog.naver.com/${process.env.NAVER_BLOG_ID || 'jun12310'}?Redirect=Write&`;
    const loggedIn = await attemptCredentialLoginOnCurrentPage(page, writeUrl);
    if (loggedIn.success) {
      log.success('자동 로그인 성공! 세션이 저장되었습니다.');
      log.info(`[timing] step=login_complete elapsed=${((Date.now() - loginStarted) / 1000).toFixed(1)}s`);
      log.info('[session] auto_login_triggered=true');
      await persistSessionState(context, page, getStorageStatePath(opts));
      await context.close();
      if (browser) await browser.close().catch(() => undefined);
      return true;
    } else {
      // 실패 시 스크린샷 캡처 (디버깅용)
      try {
        await page.screenshot({ path: './artifacts/auto_login_failure.png' });
        log.error('로그인 실패 스크린샷: ./artifacts/auto_login_failure.png');
      } catch {
        // 스크린샷 실패는 무시
      }

      log.error('자동 로그인 실패 - 수동 인증이 필요할 수 있습니다');
      log.info('다음 명령어로 수동 로그인을 시도해보세요:');
      log.info('node dist/cli/post_to_naver.js --interactiveLogin');
      await context.close();
      if (browser) await browser.close().catch(() => undefined);
      return false;
    }

  } catch (error) {
    log.error(`자동 로그인 중 오류 발생: ${error}`);
    await context.close();
    if (browser) await browser.close().catch(() => undefined);
    return false;
  }
}

/**
 * 인터랙티브 로그인 모드.
 * 브라우저를 띄워 사용자가 직접 로그인하도록 안내한다.
 */
export async function interactiveLogin(opts: SessionOptions): Promise<void> {
  log.info('=== 인터랙티브 로그인 모드 ===');
  log.info('브라우저가 열리면 네이버에 직접 로그인해주세요.');
  log.info('로그인 완료 후 이 터미널에서 Enter를 누르세요.');

  const { context, page, browser } = await createPersistentSession({
    ...opts,
    headless: false,
  });

  await page.goto('https://nid.naver.com/nidlogin.login', { waitUntil: 'domcontentloaded' });

  // 사용자 입력 대기
  await new Promise<void>((resolve) => {
    process.stdout.write('\n로그인 완료 후 Enter를 누르세요... ');
    process.stdin.once('data', () => resolve());
  });

  const writeUrl =
    process.env.NAVER_WRITE_URL ??
    `https://blog.naver.com/${process.env.NAVER_BLOG_ID || 'jun12310'}?Redirect=Write&`;
  await page.goto(writeUrl, { waitUntil: 'domcontentloaded' }).catch(() => undefined);
  const loggedIn = await isLoggedIn(page);
  await persistSessionState(context, page, getStorageStatePath(opts));
  if (loggedIn) {
    log.success('로그인 확인됨');
    log.success('세션 저장 완료');
  } else {
    const state = await detectLoginState(page).catch(() => ({ state: 'unknown', signal: 'detect_error' }));
    log.warn(`로그인 확인 실패: login_state=${state.state} signal=${state.signal}`);
    log.warn(`해결: ${formatInteractiveLoginGuide()}`);
  }

  await context.close();
  if (browser) await browser.close().catch(() => undefined);
}

/**
 * 세션을 로드하거나 생성한다 (메인 진입점).
 * 로그인이 안 되어 있으면 에러를 던진다.
 */
export async function loadOrCreateSession(
  opts: SessionOptions,
  writeUrl: string
): Promise<SessionResult> {
  const session = await createPersistentSession(opts);

  const writePageStarted = Date.now();
  log.info(`글쓰기 페이지로 이동: ${writeUrl}`);
  await navigateToWriter(session.page, writeUrl);
  log.info(`[timing] step=write_page_enter_complete elapsed=${((Date.now() - writePageStarted) / 1000).toFixed(1)}s`);

  const loginCheckStarted = Date.now();
  log.info('[timing] step=login_start elapsed=0.0s');
  let ensured: {
    ok: boolean;
    loginDetected: boolean;
    autoLoginAttempted: boolean;
    signal: string;
  };
  try {
    ensured = await ensureLoggedIn(session, opts, writeUrl, 'passive');
  } catch (error) {
    await session.context.close();
    if (session.browser) await session.browser.close().catch(() => undefined);
    throw error;
  }
  const loggedIn = ensured.ok;
  log.info(`[session] login_detected=${loggedIn}`);
  log.info(`[session] auto_login_triggered=${ensured.autoLoginAttempted}`);

  log.info(`[timing] step=login_complete elapsed=${((Date.now() - loginCheckStarted) / 1000).toFixed(1)}s`);
  await persistSessionState(session.context, session.page, getStorageStatePath(opts));
  log.success('세션 로드 완료');
  return session;
}
