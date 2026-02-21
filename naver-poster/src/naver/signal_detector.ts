import type { Frame, Page } from 'playwright';
import { isTempSaveSuccessSignal } from './temp_save_state_machine';
import { NAVER_SELECTORS, selectorListToQuery } from './selectors';

export type SaveSignals = {
  toast: boolean;
  spinner: boolean;
  status: boolean;
  overlay: boolean;
  sessionBlocked: boolean;
};

export type SignalDetectorOptions = {
  page: Page;
  frameRef: () => Frame;
};

export class SignalDetector {
  private readonly page: Page;
  private readonly frameRef: () => Frame;

  constructor(options: SignalDetectorOptions) {
    this.page = options.page;
    this.frameRef = options.frameRef;
  }

  async detect(): Promise<SaveSignals> {
    const frame = this.frameRef();
    const [toast, spinner, status, overlay, sessionBlocked] = await Promise.all([
      this.detectToast(frame),
      this.detectSpinner(frame),
      this.detectStatus(frame),
      this.detectOverlay(frame),
      this.detectSessionBlocked(),
    ]);

    return { toast, spinner, status, overlay, sessionBlocked };
  }

  private async detectToast(frame: Frame): Promise<boolean> {
    try {
      const text = await frame.evaluate((selectors) => {
        const hasVisibleNode = (el: HTMLElement): boolean => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };
        const bucket: string[] = [];
        for (const sel of selectors) {
          const nodes = Array.from(document.querySelectorAll<HTMLElement>(sel));
          for (const node of nodes) {
            if (!hasVisibleNode(node)) continue;
            const value = (node.textContent || '').replace(/\s+/g, ' ').trim();
            if (value) bucket.push(value);
          }
        }
        return bucket.join(' ');
      }, NAVER_SELECTORS.toast);
      if (text && isTempSaveSuccessSignal(text)) return true;
    } catch {
      // ignore stale frame and fallback to page
    }

    try {
      const text = await this.page.evaluate((query) => {
        const hasVisibleNode = (el: HTMLElement): boolean => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };
        const bucket = Array.from(document.querySelectorAll<HTMLElement>(query))
          .filter((el) => hasVisibleNode(el))
          .map((el) => (el.textContent || '').replace(/\s+/g, ' ').trim())
          .filter(Boolean);
        return bucket.join(' ');
      }, selectorListToQuery(NAVER_SELECTORS.toast));
      return Boolean(text && isTempSaveSuccessSignal(text));
    } catch {
      return false;
    }
  }

  private async detectSpinner(frame: Frame): Promise<boolean> {
    const query = selectorListToQuery(NAVER_SELECTORS.spinner);
    try {
      return await frame.evaluate((sel) => {
        const hasVisibleNode = (el: HTMLElement): boolean => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };
        const nodes = Array.from(document.querySelectorAll<HTMLElement>(sel));
        return nodes.some((node) => hasVisibleNode(node));
      }, query);
    } catch {
      try {
        return await this.page.evaluate((sel) => {
          const hasVisibleNode = (el: HTMLElement): boolean => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          };
          const nodes = Array.from(document.querySelectorAll<HTMLElement>(sel));
          return nodes.some((node) => hasVisibleNode(node));
        }, query);
      } catch {
        return false;
      }
    }
  }

  private async detectStatus(frame: Frame): Promise<boolean> {
    try {
      const text = await frame.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '));
      return NAVER_SELECTORS.statusTextRegex.test(text);
    } catch {
      return false;
    }
  }

  private async detectOverlay(frame: Frame): Promise<boolean> {
    const query = selectorListToQuery(NAVER_SELECTORS.overlay);
    try {
      const inFrame = await frame.evaluate((sel) => {
        const nodes = Array.from(document.querySelectorAll<HTMLElement>(sel));
        return nodes.some((node) => {
          const style = window.getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 10 && rect.height > 10;
        });
      }, query);
      if (inFrame) return true;
    } catch {
      // ignore
    }

    try {
      return await this.page.evaluate((sel) => {
        const nodes = Array.from(document.querySelectorAll<HTMLElement>(sel));
        return nodes.some((node) => {
          const style = window.getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 10 && rect.height > 10;
        });
      }, query);
    } catch {
      return false;
    }
  }

  private async detectSessionBlocked(): Promise<boolean> {
    try {
      for (const sel of NAVER_SELECTORS.sessionBlocked) {
        const loc = this.page.locator(sel).first();
        if ((await loc.count()) > 0 && await loc.isVisible().catch(() => true)) {
          return true;
        }
      }
      const url = this.page.url();
      if (/nid\.naver\.com|captcha|auth/i.test(url)) return true;
      const body = await this.page.evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' '));
      return /권한이\s*없|로그인|인증|캡차|보안문자/i.test(body);
    } catch {
      return false;
    }
  }
}
