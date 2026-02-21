import * as fs from 'fs';
import * as path from 'path';
import { Frame, Page } from 'playwright';
import * as log from '../utils/logger';
import { EditorContext } from './editor';
import { NAVER_SELECTORS } from './selectors';

export type PlaceAttachFailureCode =
  | 'PLACE_UI_NOT_FOUND'
  | 'PLACE_SEARCH_NO_RESULT'
  | 'PLACE_SEARCH_SELECT_FAILED'
  | 'PLACE_CONFIRM_NEVER_ENABLED'
  | 'PLACE_ATTACH_NOT_APPLIED'
  | 'PLACE_AUTH_OR_RATE_LIMIT'
  | 'PLACE_NETWORK_TIMEOUT';

export interface PlaceCandidate {
  id: string;
  title: string;
  address: string;
  roadAddress: string;
  category: string;
  telephone: string;
  mapx: string;
  mapy: string;
  link?: string;
}

export interface PlaceSelectionHint {
  region_hint?: string;
  category_hint?: string;
}

export interface PlaceAttachResult {
  success: boolean;
  selected_place?: PlaceCandidate;
  error?: string;
  reason_code?: PlaceAttachFailureCode;
  debug_path?: string;
}

type PlaceDebugMeta = {
  attempt: number;
  reason: PlaceAttachFailureCode | 'success';
  query_raw: string;
  query_normalized: string;
  response_traces: Array<{ status: number; url: string }>;
  addButtonFound: boolean;
  addButtonEnabledBeforeClick: boolean;
  addButtonClicked: boolean;
  addButtonClickError: string | null;
  attachSignalsObserved: {
    panelClosed: boolean;
    toast: boolean;
    response2xx: boolean;
    domInserted: boolean;
  };
  probe: {
    placeButtonCount: number;
    placePanelCount: number;
    searchInputCount: number;
    resultCount: number;
    placeCardCount: number;
  };
  frame_urls: Array<{ name: string; url: string }>;
};

const PLACE_SEARCH_TIMEOUT_MS = 6_000;
const PLACE_MAX_RETRY = 1;
const FRAME_SCORE_EVAL_TIMEOUT_MS = 700;

async function withTimeout<T>(task: Promise<T>, timeoutMs: number, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    return await Promise.race<T>([
      task,
      new Promise<T>((resolve) => {
        timer = setTimeout(() => resolve(fallback), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function stripHtml(raw: string): string {
  return raw.replace(/<[^>]+>/g, '').trim();
}

function normalizeText(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^\w\s가-힣]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizePlaceQuery(raw: string): string {
  return raw
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[()[\]{}<>]/g, ' ')
    .replace(/[^\w\s가-힣-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 40);
}

function tokenizeMeaningful(raw: string): string[] {
  return normalizeText(raw).split(' ').filter((token) => token.length >= 2);
}

function hasMapApiCredentials(): boolean {
  const id = process.env.NAVER_MAP_CLIENT_ID || process.env.NAVER_CLIENT_ID || '';
  const secret = process.env.NAVER_MAP_CLIENT_SECRET || process.env.NAVER_CLIENT_SECRET || '';
  return Boolean(id && secret);
}

function buildCandidateId(item: { title: string; address: string; mapx: string; mapy: string }): string {
  const normalized = `${stripHtml(item.title)}|${item.address}|${item.mapx}|${item.mapy}`;
  return Buffer.from(normalized, 'utf8').toString('base64').slice(0, 48);
}

async function requestLocalSearch(query: string): Promise<{
  candidates: PlaceCandidate[];
  authOrRateLimit: boolean;
}> {
  const id = process.env.NAVER_MAP_CLIENT_ID || process.env.NAVER_CLIENT_ID || '';
  const secret = process.env.NAVER_MAP_CLIENT_SECRET || process.env.NAVER_CLIENT_SECRET || '';
  if (!id || !secret) {
    return { candidates: [], authOrRateLimit: false };
  }

  const endpoint = `https://openapi.naver.com/v1/search/local.json?query=${encodeURIComponent(query)}&display=10&start=1&sort=random`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3_000);
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      'X-Naver-Client-Id': id,
      'X-Naver-Client-Secret': secret,
    },
    signal: controller.signal,
  }).finally(() => clearTimeout(timeout));

  if ([401, 403, 429].includes(response.status)) {
    return { candidates: [], authOrRateLimit: true };
  }
  if (!response.ok) {
    return { candidates: [], authOrRateLimit: false };
  }

  const payload = (await response.json()) as { items?: Array<Record<string, string>> };
  const items = payload.items ?? [];
  return {
    authOrRateLimit: false,
    candidates: items.map((item) => ({
      id: buildCandidateId({
        title: item.title || '',
        address: item.address || '',
        mapx: item.mapx || '',
        mapy: item.mapy || '',
      }),
      title: stripHtml(item.title || ''),
      address: item.address || '',
      roadAddress: item.roadAddress || '',
      category: item.category || '',
      telephone: item.telephone || '',
      mapx: item.mapx || '',
      mapy: item.mapy || '',
      link: item.link,
    })),
  };
}

async function resolveToolbarFrame(ctx: EditorContext): Promise<Frame> {
  const frames = [ctx.frame, ...ctx.page.frames()];
  let best: { frame: Frame; score: number } | null = null;
  for (const frame of frames) {
    const score = await withTimeout<number>(
      frame.evaluate(() => {
        const toolbar = document.querySelectorAll('.se-toolbar, [class*="toolbar"]').length > 0 ? 3 : 0;
        const editable = document.querySelectorAll('[contenteditable="true"]').length > 0 ? 2 : 0;
        const placeBtn = document.querySelectorAll('[data-name="map"], [data-name="place"], [aria-label*="장소"], [aria-label*="지도"]').length > 0 ? 3 : 0;
        const urlScore = /(blog|editor|write|postwriteform|redirect=write)/i.test(location.href) ? 1 : 0;
        return toolbar + editable + placeBtn + urlScore;
      }).catch(() => -1),
      FRAME_SCORE_EVAL_TIMEOUT_MS,
      -1,
    );
    if (score < 0) continue;
    if (!best || score > best.score) {
      best = { frame, score };
    }
  }
  if (!best) return ctx.frame;
  ctx.frame = best.frame;
  return best.frame;
}

async function probePlaceSelectors(frame: Frame): Promise<PlaceDebugMeta['probe']> {
  return await frame.evaluate((selectors) => {
    const countVisible = (list: string[]) =>
      list.reduce((acc, selector) => {
        try {
          const nodes = Array.from(document.querySelectorAll<HTMLElement>(selector)).filter((node) => {
            const rect = node.getBoundingClientRect();
            const style = window.getComputedStyle(node);
            return rect.width > 1 && rect.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
          });
          return acc + nodes.length;
        } catch {
          return acc;
        }
      }, 0);

    return {
      placeButtonCount: countVisible(selectors.placeButton),
      placePanelCount: countVisible(selectors.placePanel),
      searchInputCount: countVisible(selectors.placeSearchInput),
      resultCount: countVisible(selectors.placeResultItem),
      placeCardCount: countVisible(selectors.placeCard),
    };
  }, NAVER_SELECTORS);
}

async function firstVisibleSelector(frame: Frame, selectors: string[]): Promise<string | undefined> {
  for (const selector of selectors) {
    const locator = frame.locator(selector).first();
    try {
      const visible = await withTimeout<boolean>(
        locator.isVisible({ timeout: 200 }).catch(() => false),
        300,
        false,
      );
      if (visible) {
        return selector;
      }
    } catch {
      // ignore
    }
  }
  return undefined;
}

async function ensurePlacePanel(frame: Frame): Promise<boolean> {
  const panelSelector = await firstVisibleSelector(frame, NAVER_SELECTORS.placePanel);
  if (panelSelector) return true;

  const buttonSelector = await firstVisibleSelector(frame, NAVER_SELECTORS.placeButton);
  if (!buttonSelector) return false;

  const btn = frame.locator(buttonSelector).first();
  await btn.scrollIntoViewIfNeeded().catch(() => undefined);
  await btn.click({ timeout: 2000 }).catch(() => undefined);

  for (let i = 0; i < 10; i++) {
    const recheck = await firstVisibleSelector(frame, NAVER_SELECTORS.placePanel);
    if (recheck) return true;
    await frame.page().waitForTimeout(150);
  }
  return false;
}

async function getSearchInput(frame: Frame): Promise<{ selector?: string; locator: ReturnType<Frame['locator']> | null }> {
  const selector = await firstVisibleSelector(frame, NAVER_SELECTORS.placeSearchInput);
  if (!selector) return { selector: undefined, locator: null };
  return { selector, locator: frame.locator(selector).first() };
}

async function waitForResultItem(frame: Frame, timeoutMs: number): Promise<string | undefined> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const selector = await firstVisibleSelector(frame, NAVER_SELECTORS.placeResultItem);
    if (selector) {
      const count = await frame.locator(selector).count().catch(() => 0);
      if (count > 0) return selector;
    }
    await frame.page().waitForTimeout(200);
  }
  return undefined;
}

async function clickFirstResult(frame: Frame, resultSelector: string): Promise<boolean> {
  const item = frame.locator(resultSelector).first();
  try {
    await item.scrollIntoViewIfNeeded();
    await item.hover({ timeout: 1000 }).catch(() => undefined);
    await item.dispatchEvent('mousedown').catch(() => undefined);
    await item.dispatchEvent('mouseup').catch(() => undefined);
    await item.click({ timeout: 2000 });
    await frame.page().waitForTimeout(350);
    const selected = await item.evaluate((el) => {
      const own = `${el.className || ''}`.toLowerCase();
      if ((el.getAttribute('aria-selected') || '').toLowerCase() === 'true') return true;
      if (/(selected|active|highlight|checked)/.test(own)) return true;
      return Boolean(el.querySelector('.se-is-selected, [aria-checked="true"], [class*="selected"], [class*="check"]'));
    }).catch(() => false);
    if (selected) return true;
  } catch {
    // fallback below
  }

  const linkSelector = await firstVisibleSelector(frame, NAVER_SELECTORS.placeResultLink);
  if (!linkSelector) return false;
  try {
    const link = frame.locator(linkSelector).first();
    await link.scrollIntoViewIfNeeded().catch(() => undefined);
    await link.hover({ timeout: 1000 }).catch(() => undefined);
    await link.dispatchEvent('mousedown').catch(() => undefined);
    await link.dispatchEvent('mouseup').catch(() => undefined);
    await link.click({ timeout: 2000 });
    await frame.page().waitForTimeout(350);
    return true;
  } catch {
    return false;
  }
}

async function waitForEnabledButton(
  frame: Frame,
  selectors: string[],
  timeoutMs: number,
): Promise<{ found: boolean; selector?: string; enabled: boolean; index?: number }> {
  const started = Date.now();
  let foundAny = false;
  while (Date.now() - started < timeoutMs) {
    for (const selector of selectors) {
      const locator = frame.locator(selector);
      const count = await withTimeout<number>(locator.count().catch(() => 0), 300, 0);
      if (count === 0) continue;
      foundAny = true;

      const maxInspect = Math.min(count, 6);
      for (let idx = 0; idx < maxInspect; idx++) {
        const candidate = locator.nth(idx);
        const visible = await withTimeout<boolean>(candidate.isVisible().catch(() => false), 300, false);
        if (!visible) continue;
        const enabled = await withTimeout<boolean>(
          candidate.evaluate((el) => {
            const cls = (el.className || '').toLowerCase();
            const disabledAttr = el.hasAttribute('disabled');
            const ariaDisabled = (el.getAttribute('aria-disabled') || '').toLowerCase() === 'true';
            const disabledClass = /(disabled|inactive|off)/.test(cls);
            const style = window.getComputedStyle(el as Element);
            const pointerBlocked = style.pointerEvents === 'none';
            return !disabledAttr && !ariaDisabled && !disabledClass && !pointerBlocked;
          }).catch(() => false),
          300,
          false,
        );
        if (!enabled) continue;
        const trial = await withTimeout<boolean>(
          candidate.click({ trial: true, timeout: 400 }).then(() => true).catch(() => false),
          500,
          false,
        );
        if (trial) return { found: true, selector, enabled: true, index: idx };
      }
    }
    await frame.page().waitForTimeout(200);
  }
  return { found: foundAny, enabled: false };
}

async function clickButtonWithFallback(frame: Frame, selector: string, index = 0): Promise<{ ok: boolean; error?: string }> {
  const button = frame.locator(selector).nth(index);
  try {
    await button.scrollIntoViewIfNeeded();
    await button.hover({ timeout: 1000 }).catch(() => undefined);
    await button.click({ trial: true, timeout: 500 });
    await button.click({ timeout: 1500 });
    return { ok: true };
  } catch (e1: any) {
    try {
      await button.click({ timeout: 1500, force: true });
      return { ok: true };
    } catch (e2: any) {
      return { ok: false, error: String(e2?.message || e1?.message || e2 || e1) };
    }
  }
}

async function countPlaceCards(frame: Frame): Promise<number> {
  for (const selector of NAVER_SELECTORS.placeCard) {
    const count = await withTimeout<number>(frame.locator(selector).count().catch(() => 0), 300, 0);
    if (count > 0) return count;
  }
  return 0;
}

async function editorText(frame: Frame): Promise<string> {
  return withTimeout<string>(
    frame.evaluate(() => {
      const root = document.querySelector('[contenteditable="true"]') || document.body;
      return (root?.textContent || '').replace(/\s+/g, ' ').trim();
    }).catch(() => ''),
    400,
    '',
  );
}

async function waitForAttachment(
  frame: Frame,
  baselineCardCount: number,
  beforeText: string,
  query: string,
  timeoutMs: number,
): Promise<{ domInserted: boolean; panelClosed: boolean }> {
  const tokens = tokenizeMeaningful(query).slice(0, 3);
  const normalizedBefore = normalizeText(beforeText);
  const started = Date.now();

  while (Date.now() - started < timeoutMs) {
    const cardCount = await countPlaceCards(frame);
    if (cardCount > baselineCardCount) {
      return { domInserted: true, panelClosed: false };
    }

    const text = await editorText(frame);
    const normalizedNow = normalizeText(text);
    if (normalizedNow.length > normalizedBefore.length && tokens.some((token) => normalizedNow.includes(token))) {
      return { domInserted: true, panelClosed: false };
    }

    const keywordSignal = /(길찾기|지도|장소|전화|영업시간)/.test(text);
    if (keywordSignal && tokens.some((token) => normalizedNow.includes(token))) {
      return { domInserted: true, panelClosed: false };
    }

    const panelVisible = await firstVisibleSelector(frame, NAVER_SELECTORS.placePanel);
    if (!panelVisible) {
      return { domInserted: false, panelClosed: true };
    }

    await frame.page().waitForTimeout(200);
  }
  const panelVisible = await firstVisibleSelector(frame, NAVER_SELECTORS.placePanel);
  return { domInserted: false, panelClosed: !panelVisible };
}

async function detectToastSignal(page: Page): Promise<boolean> {
  for (const selector of NAVER_SELECTORS.toast) {
    const text = await page.locator(selector).first().innerText().catch(() => '');
    if (!text) continue;
    if (/(추가|첨부|삽입|지도|장소)/.test(text)) {
      return true;
    }
  }
  return false;
}

function hasAttachResponse2xx(responses: Array<{ status: number; url: string }>, fromIndex: number): boolean {
  return responses.slice(fromIndex).some((resp) => {
    if (resp.status < 200 || resp.status >= 300) return false;
    if (!/(map|place)/i.test(resp.url)) return false;
    if (/\/ac\?|\/places\?/.test(resp.url)) return false;
    return /(attach|insert|apply|save|publish|component|place|map)/i.test(resp.url);
  });
}

async function capturePlaceDebug(page: Page, frame: Frame, debugMeta: PlaceDebugMeta): Promise<string | undefined> {
  try {
    const base = '/tmp/naver_editor_debug';
    const dirName = `${new Date().toISOString().replace(/[:.]/g, '-')}_place_attach_${debugMeta.reason === 'success' ? 'success' : 'fail'}`;
    const debugDir = path.join(base, dirName);
    fs.mkdirSync(debugDir, { recursive: true });

    const payload = {
      ...debugMeta,
      page_url: page.url(),
      frame_url: frame.url(),
      captured_at: new Date().toISOString(),
    };

    fs.writeFileSync(path.join(debugDir, 'place_debug.json'), JSON.stringify(payload, null, 2), 'utf8');
    await page.screenshot({ path: path.join(debugDir, 'page.png'), fullPage: true }).catch(() => undefined);
    const html = await frame.content().catch(() => '');
    if (html) {
      fs.writeFileSync(path.join(debugDir, 'frame.html'), html, 'utf8');
    }

    return debugDir;
  } catch (error) {
    log.warn(`[place] debug capture failed: ${String(error)}`);
    return undefined;
  }
}

function buildSearchQueries(raw: string, hint: PlaceSelectionHint): string[] {
  const base = normalizePlaceQuery(raw);
  if (!base) return [];

  const queries = [base];
  if (hint.region_hint?.trim()) {
    queries.push(normalizePlaceQuery(`${base} ${hint.region_hint.trim()}`));
  }
  if (hint.category_hint?.trim()) {
    queries.push(normalizePlaceQuery(`${base} ${hint.category_hint.trim()}`));
  }

  return Array.from(new Set(queries.filter(Boolean)));
}

export async function attach_place_in_editor(
  ctx: EditorContext,
  place_name: string,
  place_hint: PlaceSelectionHint = {},
  _artifactsDir?: string,
): Promise<PlaceAttachResult> {
  const page = ctx.page;
  const responses: Array<{ status: number; url: string }> = [];

  const localQueries = buildSearchQueries(place_name, place_hint);
  if (localQueries.length === 0) {
    return { success: false, reason_code: 'PLACE_UI_NOT_FOUND', error: '장소명이 비어 있습니다.' };
  }

  let resolvedCandidate: PlaceCandidate | undefined;
  let authOrRateLimit = false;

  if (hasMapApiCredentials()) {
    for (const query of localQueries) {
      try {
        const search = await requestLocalSearch(query);
        if (search.authOrRateLimit) {
          authOrRateLimit = true;
          break;
        }
        if (search.candidates.length > 0) {
          resolvedCandidate = search.candidates[0];
          break;
        }
      } catch {
        // fallback to editor-dom search
      }
    }
  }

  if (authOrRateLimit) {
    return {
      success: false,
      reason_code: 'PLACE_AUTH_OR_RATE_LIMIT',
      error: '장소 검색 API 인증 또는 호출 제한 상태입니다.',
    };
  }

  const query = normalizePlaceQuery(resolvedCandidate?.title || localQueries[0]);
  if (!query) {
    return { success: false, reason_code: 'PLACE_UI_NOT_FOUND', error: '유효한 장소 검색어가 없습니다.' };
  }
  const overallDeadline = Date.now() + 24_000;
  const remainingMs = () => Math.max(0, overallDeadline - Date.now());

  for (let attempt = 1; attempt <= PLACE_MAX_RETRY; attempt++) {
    const frame = await resolveToolbarFrame(ctx);
    let addButtonFound = false;
    let addButtonEnabledBeforeClick = false;
    let addButtonClicked = false;
    let addButtonClickError: string | null = null;
    const attachSignalsObserved = {
      panelClosed: false,
      toast: false,
      response2xx: false,
      domInserted: false,
    };

    const onResponse = (response: { status(): number; url(): string }) => {
      const status = response.status();
      const url = response.url();
      if (/map|place|search|local/i.test(url)) {
        responses.push({ status, url });
      }
    };

    page.on('response', onResponse as any);
    let reason: PlaceAttachFailureCode | 'success' = 'PLACE_UI_NOT_FOUND';

    try {
      log.info(`[place] attempt=${attempt} start query="${query}" remainingMs=${remainingMs()}`);
      const panelReady = await ensurePlacePanel(frame);
      if (!panelReady) {
        reason = 'PLACE_UI_NOT_FOUND';
        throw new Error(reason);
      }
      log.info('[place] panel_ready=true');

      const inputRef = await getSearchInput(frame);
      if (!inputRef.locator) {
        reason = 'PLACE_UI_NOT_FOUND';
        throw new Error(reason);
      }

      await inputRef.locator.click({ timeout: 2000 });
      await inputRef.locator.fill(query, { timeout: 2000 });
      await inputRef.locator.press('Enter', { timeout: 1000 });

      const resultSelector = await waitForResultItem(frame, Math.min(PLACE_SEARCH_TIMEOUT_MS, remainingMs()));
      if (!resultSelector) {
        reason = 'PLACE_SEARCH_NO_RESULT';
        throw new Error(reason);
      }
      log.info(`[place] result_ready selector="${resultSelector}"`);

      const beforeCards = await countPlaceCards(frame);
      const beforeText = await editorText(frame);

      const selected = await clickFirstResult(frame, resultSelector);
      if (!selected) {
        reason = 'PLACE_SEARCH_SELECT_FAILED';
        throw new Error(reason);
      }
      log.info('[place] result_selected=true');

      let addButton = await waitForEnabledButton(frame, NAVER_SELECTORS.placeAddButton, Math.min(8_000, remainingMs()));
      addButtonFound = addButton.found;
      addButtonEnabledBeforeClick = addButton.enabled;
      if (!addButton.enabled) {
        const reselected = await clickFirstResult(frame, resultSelector);
        if (!reselected) {
          reason = 'PLACE_SEARCH_SELECT_FAILED';
          throw new Error(reason);
        }
        addButton = await waitForEnabledButton(frame, NAVER_SELECTORS.placeAddButton, Math.min(2_000, remainingMs()));
        addButtonFound = addButtonFound || addButton.found;
        addButtonEnabledBeforeClick = addButton.enabled;
      }

      if (!addButton.enabled || !addButton.selector) {
        addButton = await waitForEnabledButton(frame, NAVER_SELECTORS.placeConfirmButton, Math.min(2_000, remainingMs()));
        addButtonFound = addButtonFound || addButton.found;
        addButtonEnabledBeforeClick = addButton.enabled;
      }

      if (!addButton.enabled || !addButton.selector) {
        reason = 'PLACE_CONFIRM_NEVER_ENABLED';
        throw new Error(reason);
      }
      log.info(`[place] add_button_ready selector="${addButton.selector}" enabled=${addButton.enabled}`);

      const beforeResponseCount = responses.length;
      const addClicked = await clickButtonWithFallback(frame, addButton.selector, addButton.index ?? 0);
      addButtonClicked = addClicked.ok;
      addButtonClickError = addClicked.error || null;
      if (!addClicked.ok) {
        reason = 'PLACE_ATTACH_NOT_APPLIED';
        throw new Error(reason);
      }
      log.info('[place] add_button_clicked=true');

      const attached = await waitForAttachment(frame, beforeCards, beforeText, query, Math.min(6_000, remainingMs()));
      attachSignalsObserved.domInserted = attached.domInserted;
      attachSignalsObserved.panelClosed = attached.panelClosed;
      attachSignalsObserved.response2xx = hasAttachResponse2xx(responses, beforeResponseCount);
      attachSignalsObserved.toast = await detectToastSignal(page);

      const attachedByAnySignal = (
        attachSignalsObserved.domInserted
        || attachSignalsObserved.panelClosed
        || attachSignalsObserved.response2xx
        || attachSignalsObserved.toast
      );
      if (!attachedByAnySignal) {
        reason = 'PLACE_ATTACH_NOT_APPLIED';
        throw new Error(reason);
      }
      log.info(`[place] attach_signals domInserted=${attachSignalsObserved.domInserted} panelClosed=${attachSignalsObserved.panelClosed} response2xx=${attachSignalsObserved.response2xx} toast=${attachSignalsObserved.toast}`);

      const probe = await probePlaceSelectors(frame);
      const debugPath = await capturePlaceDebug(page, frame, {
        attempt,
        reason: 'success',
        query_raw: place_name,
        query_normalized: query,
        response_traces: responses.slice(-20),
        addButtonFound,
        addButtonEnabledBeforeClick,
        addButtonClicked,
        addButtonClickError,
        attachSignalsObserved,
        probe,
        frame_urls: page.frames().map((f) => ({ name: f.name(), url: f.url() })),
      });

      page.off('response', onResponse as any);
      return {
        success: true,
        selected_place: resolvedCandidate,
        debug_path: debugPath,
      };
    } catch (error) {
      const message = String((error as Error)?.message || error || '');
      if ([401, 403, 429].some((status) => responses.some((r) => r.status === status))) {
        reason = 'PLACE_AUTH_OR_RATE_LIMIT';
      } else if (message.includes('Timeout')) {
        reason = 'PLACE_NETWORK_TIMEOUT';
      } else if ((message as PlaceAttachFailureCode) in {
        PLACE_UI_NOT_FOUND: 1,
        PLACE_SEARCH_NO_RESULT: 1,
        PLACE_SEARCH_SELECT_FAILED: 1,
        PLACE_CONFIRM_NEVER_ENABLED: 1,
        PLACE_ATTACH_NOT_APPLIED: 1,
        PLACE_AUTH_OR_RATE_LIMIT: 1,
        PLACE_NETWORK_TIMEOUT: 1,
      }) {
        reason = message as PlaceAttachFailureCode;
      }

      const probe = await probePlaceSelectors(frame);
      const debugPath = await capturePlaceDebug(page, frame, {
        attempt,
        reason,
        query_raw: place_name,
        query_normalized: query,
        response_traces: responses.slice(-20),
        addButtonFound,
        addButtonEnabledBeforeClick,
        addButtonClicked,
        addButtonClickError,
        attachSignalsObserved,
        probe,
        frame_urls: page.frames().map((f) => ({ name: f.name(), url: f.url() })),
      });

      page.off('response', onResponse as any);
      if (reason === 'PLACE_AUTH_OR_RATE_LIMIT') {
        return {
          success: false,
          reason_code: reason,
          debug_path: debugPath,
          error: `장소 첨부 실패(${reason})`,
        };
      }

      if (attempt === PLACE_MAX_RETRY) {
        return {
          success: false,
          reason_code: reason,
          debug_path: debugPath,
          error: `장소 첨부 실패(${reason})`,
        };
      }

      if (remainingMs() < 1_000) {
        return {
          success: false,
          reason_code: 'PLACE_NETWORK_TIMEOUT',
          debug_path: debugPath,
          error: '장소 첨부 실패(PLACE_NETWORK_TIMEOUT): 전체 타임박스 초과',
        };
      }

      await page.waitForTimeout(300);
    }
  }

  return {
    success: false,
    reason_code: 'PLACE_ATTACH_NOT_APPLIED',
    error: '장소 첨부 실패(PLACE_ATTACH_NOT_APPLIED)',
  };
}

export async function attachPlace(
  ctx: EditorContext,
  storeName: string,
  artifactsDir: string,
  placeHint: PlaceSelectionHint = {},
): Promise<boolean> {
  const result = await attach_place_in_editor(ctx, storeName, placeHint, artifactsDir);
  return result.success;
}

export async function clickPlaceAddButtonForTest(frame: Frame, timeoutMs = 2_000): Promise<boolean> {
  const addButton = await waitForEnabledButton(frame, NAVER_SELECTORS.placeAddButton, timeoutMs);
  if (!addButton.enabled || !addButton.selector) return false;
  const clicked = await clickButtonWithFallback(frame, addButton.selector, addButton.index ?? 0);
  return clicked.ok;
}
