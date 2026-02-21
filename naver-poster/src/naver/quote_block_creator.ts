import * as fs from 'fs';
import * as path from 'path';
import type { Frame, Page } from 'playwright';
import { NAVER_SELECTORS } from './selectors';

export class QuoteBlockCreateError extends Error {
  readonly attempts: number;
  readonly debugPath?: string;

  constructor(message: string, attempts: number, debugPath?: string) {
    super(message);
    this.attempts = attempts;
    this.debugPath = debugPath;
  }
}

type QuoteCreateAttemptLog = {
  attempt: number;
  strategy: 'A' | 'B' | 'C';
  frameUrl: string | null;
  reason: string;
};

type CreateQuote2Options = {
  page: Page;
  frameRef: () => Frame;
  setFrame: (frame: Frame) => void;
  title: string;
  artifactsDir?: string;
  maxRetry?: number;
};

type FrameProbe = {
  frame: Frame;
  url: string;
  hasEditable: boolean;
  hasToolbar: boolean;
  hasSaveButton: boolean;
  score: number;
};

const QUOTE_CREATE_TIMEOUT_MS = 15_000;

function isQuote2NodeClass(raw: string): boolean {
  return /(quote[-_ ]?2|quotation[-_ ]?2|type[-_ ]?2|vertical|line|blockquote)/i.test(raw);
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, reason: string): Promise<T> {
  let handle: ReturnType<typeof setTimeout> | null = null;
  const timeout = new Promise<never>((_, reject) => {
    handle = setTimeout(() => reject(new Error(reason)), timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (handle) clearTimeout(handle);
  }) as Promise<T>;
}

async function probeFrame(frame: Frame): Promise<FrameProbe> {
  const url = frame.url() || '';
  const urlHint = /(blog|editor|write|PostWriteForm|Redirect=Write)/i.test(url) ? 2 : 0;

  const dom = await frame.evaluate(() => {
    const editable = document.querySelectorAll('[contenteditable="true"], .se-text-paragraph').length;
    const toolbar = document.querySelectorAll('.se-toolbar, [class*="toolbar"]').length;
    const saveBtn = document.querySelectorAll('.btn_save, [class*="save_btn"], [data-name="save"]').length;
    return {
      editable,
      toolbar,
      saveBtn,
    };
  }).catch(() => ({ editable: 0, toolbar: 0, saveBtn: 0 }));

  const hasEditable = dom.editable > 0;
  const hasToolbar = dom.toolbar > 0;
  const hasSaveButton = dom.saveBtn > 0;
  const score = urlHint + (hasEditable ? 4 : 0) + (hasToolbar ? 2 : 0) + (hasSaveButton ? 1 : 0);

  return {
    frame,
    url,
    hasEditable,
    hasToolbar,
    hasSaveButton,
    score,
  };
}

async function rebindEditorFrame(page: Page, fallback: Frame, setFrame: (frame: Frame) => void): Promise<Frame> {
  const candidates = Array.from(new Set([page.frame('mainFrame'), ...page.frames(), fallback].filter(Boolean) as Frame[]));
  const probes: FrameProbe[] = [];
  for (const frame of candidates) {
    probes.push(await probeFrame(frame));
  }

  const best = probes
    .filter((p) => p.hasEditable)
    .sort((a, b) => b.score - a.score)[0]
    ?? probes.sort((a, b) => b.score - a.score)[0];

  if (!best) {
    throw new Error('editor_frame_not_found');
  }

  setFrame(best.frame);
  return best.frame;
}

async function waitEditorAligned(frame: Frame): Promise<void> {
  const deadline = Date.now() + 5_000;
  while (Date.now() <= deadline) {
    const state = await frame.evaluate(() => {
      const spinner = Array.from(document.querySelectorAll<HTMLElement>('[class*="saving"], [class*="save_ing"], [class*="spinner"], [class*="loading"]'))
        .some((el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        });
      const toolbarVisible = Array.from(document.querySelectorAll<HTMLElement>('.se-toolbar, [class*="toolbar"]'))
        .some((el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        });
      const editables = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"], .se-text-paragraph'))
        .filter((el) => !el.closest('.se-documentTitle'));
      const active = document.activeElement as HTMLElement | null;
      const collapse = !!window.getSelection()?.isCollapsed;
      return {
        spinner,
        toolbarVisible,
        hasEditable: editables.length > 0,
        activeEditable: !!active && (active.isContentEditable || !!active.closest('[contenteditable="true"], .se-text-paragraph')),
        collapse,
      };
    }).catch(() => ({ spinner: true, toolbarVisible: false, hasEditable: false, activeEditable: false, collapse: false }));

    if (!state.spinner && state.toolbarVisible && state.hasEditable) {
      return;
    }
    await frame.waitForTimeout(150).catch(() => undefined);
  }
}

async function focusEditableAndCollapseSelection(frame: Frame): Promise<boolean> {
  return await frame.evaluate(() => {
    const editables = Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"], .se-text-paragraph'))
      .filter((el) => !el.closest('.se-documentTitle'));
    const target = editables[editables.length - 1];
    if (!target) return false;
    target.click();
    target.focus();
    const selection = window.getSelection();
    if (!selection) return false;
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
    return !!selection.isCollapsed;
  }).catch(() => false);
}

async function verifyQuote2Applied(frame: Frame): Promise<boolean> {
  return await frame.evaluate((rootSelector) => {
    const active = document.activeElement as HTMLElement | null;
    const fromActive = active?.closest<HTMLElement>(rootSelector);
    const quoteNodes = Array.from(document.querySelectorAll<HTMLElement>(rootSelector));
    const target = fromActive || quoteNodes[quoteNodes.length - 1] || null;
    if (!target) return false;
    const cls = `${target.className || ''} ${target.getAttribute('data-type') || ''} ${target.getAttribute('data-style') || ''}`;
    return /(quote[-_ ]?2|quotation[-_ ]?2|type[-_ ]?2|blockquote|vertical|line)/i.test(cls);
  }, NAVER_SELECTORS.quoteRoot).catch(() => false);
}

async function writeTitleIntoLatestQuote(frame: Frame, title: string): Promise<boolean> {
  return await frame.evaluate(({ text, selector }) => {
    const active = document.activeElement as HTMLElement | null;
    const quoteNodes = Array.from(document.querySelectorAll<HTMLElement>(selector));
    const activeQuote = active?.closest<HTMLElement>(selector);
    const target = activeQuote || quoteNodes[quoteNodes.length - 1] || null;
    if (!target) return false;

    const editable = target.querySelector<HTMLElement>('[contenteditable="true"]')
      || target.querySelector<HTMLElement>('.se-text-paragraph')
      || (target.matches('[contenteditable="true"]') ? target : null);
    if (!editable) return false;

    editable.focus();
    const selection = window.getSelection();
    if (selection) {
      const range = document.createRange();
      range.selectNodeContents(editable);
      selection.removeAllRanges();
      selection.addRange(range);
    }

    const cleared = document.execCommand('delete', false);
    if (!cleared) editable.textContent = '';
    const inserted = document.execCommand('insertText', false, text);
    if (!inserted) editable.textContent = text;
    editable.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));

    const rendered = (editable.innerText || editable.textContent || '').replace(/\s+/g, ' ').trim();
    return rendered === text;
  }, { text: title, selector: NAVER_SELECTORS.quoteRoot }).catch(() => false);
}

async function clickSelectorIfVisible(frame: Frame, selector: string): Promise<boolean> {
  const locator = frame.locator(selector).first();
  if ((await locator.count().catch(() => 0)) === 0) return false;
  if (!(await locator.isVisible().catch(() => false))) return false;
  await locator.click({ force: true, timeout: 2_000 }).catch(() => undefined);
  return true;
}

async function clickByText(frame: Frame, pattern: RegExp): Promise<boolean> {
  return await frame.evaluate(({ source, flags }) => {
    const regex = new RegExp(source, flags);
    const nodes = Array.from(document.querySelectorAll<HTMLElement>('button, [role="button"], a, [aria-label], [title], li'));
    for (const node of nodes) {
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 2 || rect.height < 2) continue;
      const text = `${node.textContent || ''} ${node.getAttribute('aria-label') || ''} ${node.getAttribute('title') || ''}`;
      if (!regex.test(text)) continue;
      node.click();
      return true;
    }
    return false;
  }, { source: pattern.source, flags: pattern.flags }).catch(() => false);
}

async function strategyA(frame: Frame): Promise<boolean> {
  // 정석 UI: 인용구/서식 버튼 -> 인용구2 옵션
  const menuSelectors = [
    '.se-document-toolbar-select-option-button[data-name="quotation"]',
    '[data-name="insert-quotation"] .se-document-toolbar-select-option-button',
    ...NAVER_SELECTORS.quoteMenu,
    '[aria-label*="서식"]',
    '[aria-label*="스타일"]',
    '[title*="서식"]',
    '[title*="스타일"]',
  ];
  const optionSelectors = [...NAVER_SELECTORS.quote2Option, '[aria-label*="인용구 2"]', '[title*="인용구2"]'];

  for (const menuSel of menuSelectors) {
    const clickedMenu = await clickSelectorIfVisible(frame, menuSel) || await clickByText(frame, /(인용구|인용|서식|스타일)/i);
    if (!clickedMenu) continue;
    await frame.waitForTimeout(120).catch(() => undefined);

    for (const optionSel of optionSelectors) {
      const clickedOption = await clickSelectorIfVisible(frame, optionSel) || await clickByText(frame, /(인용구\s*2|인용구2|quote\s*2|quote2)/i);
      if (!clickedOption) continue;
      await frame.waitForTimeout(160).catch(() => undefined);
      if (await verifyQuote2Applied(frame)) return true;
    }

    // 텍스트가 없는 드롭다운 항목 fallback: quotation 메뉴 2번째 옵션 시도
    const clickedByIndex = await frame.evaluate(() => {
      const menuRoots = Array.from(document.querySelectorAll<HTMLElement>('[role="menu"], [class*="menu"], [class*="dropdown"], [class*="select"]'))
        .filter((el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        });
      const nodes: HTMLElement[] = [];
      for (const root of menuRoots) {
        nodes.push(...Array.from(root.querySelectorAll<HTMLElement>('button, li, [role="menuitem"], [data-value], [class*="option"]')));
      }
      const visible = nodes.filter((el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      });
      const quote2Candidate = visible.find((el) => {
        const attrs = `${el.getAttribute('data-value') || ''} ${el.className || ''} ${el.getAttribute('aria-label') || ''}`.toLowerCase();
        return /quote2|quotation2|quote-2|quotation-2/.test(attrs);
      });
      if (quote2Candidate) {
        quote2Candidate.click();
        return true;
      }
      if (visible.length >= 2) {
        visible[1].click();
        return true;
      }
      return false;
    }).catch(() => false);
    if (clickedByIndex) {
      await frame.waitForTimeout(180).catch(() => undefined);
      if (await verifyQuote2Applied(frame)) return true;
    }
  }

  return false;
}

async function strategyB(page: Page, frame: Frame): Promise<boolean> {
  // 키보드 + 포맷 드롭다운 fallback
  await page.keyboard.press('Control+a').catch(() => undefined);
  await frame.waitForTimeout(80).catch(() => undefined);

  const formatOpen = await clickByText(frame, /(서식|스타일|포맷|format)/i)
    || await clickSelectorIfVisible(frame, '[aria-label*="서식"]')
    || await clickSelectorIfVisible(frame, '[title*="서식"]');
  if (formatOpen) {
    await frame.waitForTimeout(120).catch(() => undefined);
    const choseQuote2 = await clickByText(frame, /(인용구\s*2|인용구2|quote\s*2|quote2)/i)
      || await clickSelectorIfVisible(frame, NAVER_SELECTORS.quote2Option[0]);
    if (choseQuote2) {
      await frame.waitForTimeout(160).catch(() => undefined);
      if (await verifyQuote2Applied(frame)) return true;
    }
  }

  return false;
}

async function strategyC(frame: Frame): Promise<boolean> {
  // DOM 강제 변환 fallback
  const applied = await frame.evaluate((rootSelector) => {
    const active = document.activeElement as HTMLElement | null;
    const editable = active?.closest<HTMLElement>('[contenteditable="true"], .se-text-paragraph')
      || Array.from(document.querySelectorAll<HTMLElement>('[contenteditable="true"], .se-text-paragraph'))
        .filter((el) => !el.closest('.se-documentTitle'))
        .slice(-1)[0]
      || null;
    if (!editable) return false;

    const component = editable.closest<HTMLElement>('.se-component') || editable.parentElement || editable;
    const quoteHost = editable.closest<HTMLElement>(rootSelector) || component;
    quoteHost.setAttribute('data-type', 'quote2');
    quoteHost.setAttribute('data-style', 'quote2');
    quoteHost.classList.add('se-component-quotation', 'se-quotation-container', 'quote2', 'se-l-quotation');
    editable.setAttribute('data-style', 'quote2');
    editable.classList.add('quote2', 'se-quote2-text');
    return true;
  }, NAVER_SELECTORS.quoteRoot).catch(() => false);

  if (!applied) return false;
  await frame.waitForTimeout(100).catch(() => undefined);
  return verifyQuote2Applied(frame);
}

async function captureQuoteFailureDebug(page: Page, frame: Frame, logs: QuoteCreateAttemptLog[]): Promise<string | undefined> {
  try {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const dir = path.join('/tmp/naver_editor_debug', `${ts}_section_title_quote2_fail`);
    fs.mkdirSync(dir, { recursive: true });

    await page.screenshot({ path: path.join(dir, 'page.png'), fullPage: true }).catch(() => undefined);

    const frameList = page.frames().map((f) => ({
      name: f.name(),
      url: f.url(),
    }));

    const probe = await frame.evaluate((rootSelector) => {
      const active = document.activeElement as HTMLElement | null;
      const block = active?.closest<HTMLElement>('.se-component, [class*="se-component"], [contenteditable="true"]') || null;
      const toolbar = document.querySelector<HTMLElement>('.se-toolbar, [class*="toolbar"]');
      return {
        active: active ? {
          tag: active.tagName,
          className: active.className,
        } : null,
        blockOuterHTML: block?.outerHTML?.slice(0, 6000) || null,
        toolbarHTML: toolbar?.outerHTML?.slice(0, 6000) || null,
        quoteCount: document.querySelectorAll(rootSelector).length,
      };
    }, NAVER_SELECTORS.quoteRoot).catch(() => ({ active: null, blockOuterHTML: null, toolbarHTML: null, quoteCount: 0 }));

    fs.writeFileSync(path.join(dir, 'quote2_debug.json'), JSON.stringify({
      at: new Date().toISOString(),
      frameList,
      probe,
      attempts: logs,
      pageUrl: page.url(),
      frameUrl: frame.url(),
    }, null, 2), 'utf-8');

    return dir;
  } catch {
    return undefined;
  }
}

export async function createQuote2BlockOrThrow(options: CreateQuote2Options): Promise<void> {
  const maxRetry = options.maxRetry ?? 2;
  const maxAttempts = Math.max(1, maxRetry + 1);
  const title = options.title.trim();
  const logs: QuoteCreateAttemptLog[] = [];

  try {
    await withTimeout((async () => {
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        let frame: Frame;
        try {
          frame = await rebindEditorFrame(options.page, options.frameRef(), options.setFrame);
        } catch (error) {
          logs.push({
            attempt,
            strategy: 'A',
            frameUrl: null,
            reason: `frame_rebind_failed:${String(error)}`,
          });
          continue;
        }

        await waitEditorAligned(frame).catch(() => undefined);
        const focused = await focusEditableAndCollapseSelection(frame);
        if (!focused) {
          logs.push({
            attempt,
            strategy: 'A',
            frameUrl: frame.url() || null,
            reason: 'focus_or_selection_not_ready',
          });
        }

        const a = await strategyA(frame);
        if (a && await writeTitleIntoLatestQuote(frame, title)) {
          return;
        }
        logs.push({ attempt, strategy: 'A', frameUrl: frame.url() || null, reason: 'strategy_a_failed' });

        await waitEditorAligned(frame).catch(() => undefined);
        const b = await strategyB(options.page, frame);
        if (b && await writeTitleIntoLatestQuote(frame, title)) {
          return;
        }
        logs.push({ attempt, strategy: 'B', frameUrl: frame.url() || null, reason: 'strategy_b_failed' });

        await waitEditorAligned(frame).catch(() => undefined);
        const c = await strategyC(frame);
        if (c && await writeTitleIntoLatestQuote(frame, title)) {
          return;
        }
        logs.push({ attempt, strategy: 'C', frameUrl: frame.url() || null, reason: 'strategy_c_failed' });
      }

      throw new Error('quote2_all_strategies_failed');
    })(), QUOTE_CREATE_TIMEOUT_MS, 'quote2 create timeout');
  } catch (error) {
    const debugPath = await captureQuoteFailureDebug(options.page, options.frameRef(), logs);
    throw new QuoteBlockCreateError(`quote2_block_create_failed:${String(error)}`, maxAttempts, debugPath);
  }
}

export function isQuote2ClassName(raw: string): boolean {
  return isQuote2NodeClass(raw);
}
