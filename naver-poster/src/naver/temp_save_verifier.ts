import * as fs from 'fs';
import * as path from 'path';

import * as log from '../utils/logger';
import { createDebugRunDir } from '../common/debug_paths';
import { EditorContext } from './editor';
import { isTempSaveSuccessSignal } from './temp_save_state_machine';

export interface TempSaveVerificationResult {
  success: boolean;
  verified_via: 'toast' | 'draft_list' | 'both' | 'none';
  reason_code?: string;
  toast_message?: string;
  draft_found?: boolean;
  draft_title?: string;
  draft_edit_url?: string;
  draft_id?: string;
  debug_path?: string;
  error_message?: string;
  screenshots?: string[];
}

export class TempSaveVerifier {
  private readonly ctx: EditorContext;
  private readonly artifactsDir: string;
  private readonly expectedTitle: string;
  private readonly verifyTimeoutMs: number;

  constructor(
    ctx: EditorContext,
    artifactsDir: string,
    expectedTitle: string,
    options?: { verifyTimeoutMs?: number },
  ) {
    this.ctx = ctx;
    this.artifactsDir = artifactsDir;
    this.expectedTitle = expectedTitle.trim();
    this.verifyTimeoutMs = Math.max(
      100,
      Math.min(30_000, options?.verifyTimeoutMs ?? parseInt(process.env.NAVER_DRAFT_VERIFY_STAGE_TIMEOUT_MS ?? '30000', 10)),
    );
  }

  async verifyTempSave(): Promise<TempSaveVerificationResult> {
    log.info('🔍 임시저장 검증 시작...');

    const result: TempSaveVerificationResult = {
      success: false,
      verified_via: 'none',
      screenshots: [],
    };

    try {
      const toast = await this.verifyToastMessage();
      if (toast.success) {
        result.verified_via = 'toast';
        result.toast_message = toast.message;
      }

      const draft = await this.withTimeout(
        () => this.verifyDraftPersisted(),
        this.verifyTimeoutMs,
        'DRAFT_VERIFY_TIMEOUT',
      );
      if (draft.success) {
        result.draft_found = true;
        result.draft_title = draft.title;
        result.draft_edit_url = draft.editUrl;
        result.draft_id = draft.draftId;
        result.verified_via = result.verified_via === 'toast' ? 'both' : 'draft_list';
      }

      if (draft.success) {
        result.success = true;
        result.reason_code = 'DRAFT_VERIFIED';
        log.success(`🎉 임시저장 검증 완료: ${result.verified_via}`);
        return result;
      }

      if (toast.success) {
        result.reason_code = 'DRAFT_NOT_FOUND_AFTER_SUCCESS_SIGNAL';
        result.error_message = '임시저장 성공 신호는 감지했지만 임시저장함 목록에서 글이 확인되지 않음';
      } else {
        result.reason_code = 'DRAFT_SAVE_SIGNAL_MISSING';
        result.error_message = '임시저장 성공 신호/임시글함 검증 모두 실패';
      }
      result.debug_path = await this.captureFailureEvidence(result, {
        used_key: draft.usedKey,
        matched_count: draft.matchedCount,
        list_snippet: draft.listSnippet,
        anchor_sample: draft.anchorSample,
      });
      log.error('❌ 임시저장 검증 실패');
      return result;
    } catch (error: any) {
      if (error?.code === 'DRAFT_VERIFY_TIMEOUT') {
        result.reason_code = 'DRAFT_VERIFY_TIMEOUT';
        result.error_message = `임시저장 검증 단계 타임아웃 (${this.verifyTimeoutMs}ms)`;
      } else {
        result.reason_code = 'DRAFT_VERIFY_EXCEPTION';
        result.error_message = `검증 중 예외: ${error.message}`;
      }
      result.debug_path = await this.captureFailureEvidence(result);
      log.error(`❌ 임시저장 검증 예외: ${result.error_message}`);
      return result;
    }
  }

  private async withTimeout<T>(fn: () => Promise<T>, timeoutMs: number, code: string): Promise<T> {
    let handle: ReturnType<typeof setTimeout> | null = null;
    const timeoutPromise = new Promise<never>((_, reject) => {
      handle = setTimeout(() => {
        const err = new Error(`[${code}] timeout=${timeoutMs}ms`) as Error & { code?: string };
        err.code = code;
        reject(err);
      }, timeoutMs);
    });

    try {
      return await Promise.race([fn(), timeoutPromise]);
    } finally {
      if (handle) clearTimeout(handle);
    }
  }

  private async verifyToastMessage(): Promise<{ success: boolean; message?: string }> {
    log.info('1️⃣ 토스트 메시지 검증 중...');
    const { page, frame } = this.ctx;

    const selectors = [
      '[class*="toast"]',
      '[class*="snackbar"]',
      '[class*="alert"]',
      '[class*="notification"]',
      '[class*="message"]',
      '[role="alert"]',
    ].join(', ');

    // 저장 직후 바로 사라질 수 있어서 frame/page를 짧게 여러 번 폴링
    for (let i = 0; i < 8; i++) {
      const [frameMsg, pageMsg] = await Promise.all([
        this.findSuccessMessageInScope(async () => frame.$$eval(selectors, (els) => els.map((el) => el.textContent || '').filter(Boolean))),
        this.findSuccessMessageInScope(async () => page.$$eval(selectors, (els) => els.map((el) => el.textContent || '').filter(Boolean))),
      ]);

      if (frameMsg) {
        log.success(`토스트 검증 성공(frame): ${frameMsg}`);
        return { success: true, message: frameMsg };
      }
      if (pageMsg) {
        log.success(`토스트 검증 성공(page): ${pageMsg}`);
        return { success: true, message: pageMsg };
      }

      await page.waitForTimeout(500);
    }

    log.warn('토스트 메시지 검증 실패');
    return { success: false };
  }

  private async findSuccessMessageInScope(loader: () => Promise<string[]>): Promise<string | null> {
    try {
      const texts = await loader();
      for (const raw of texts) {
        const text = raw.replace(/\s+/g, ' ').trim();
        if (!text) continue;
        if (this.isFailureMessage(text)) continue;
        if (this.isSuccessMessage(text)) return text;
      }
      return null;
    } catch {
      return null;
    }
  }

  private isSuccessMessage(text: string): boolean {
    return isTempSaveSuccessSignal(text);
  }

  private isFailureMessage(text: string): boolean {
    return [
      /저장\s*실패/i,
      /저장\s*오류/i,
      /저장\s*불가/i,
      /네트워크\s*오류/i,
      /다시\s*시도/i,
    ].some((p) => p.test(text));
  }

  private async verifyDraftPersisted(): Promise<{
    success: boolean;
    title?: string;
    editUrl?: string;
    draftId?: string;
    usedKey?: 'draftId' | 'title';
    matchedCount?: number;
    listSnippet?: string[];
    anchorSample?: Array<{ href: string; text: string }>;
  }> {
    log.info('2️⃣ 임시글함 목록 검증 중...');
    const { frame } = this.ctx;

    await this.waitForSaveSignal();
    const panelResult = await this.verifyDraftPanelInEditor(frame);
    if (panelResult.success) {
      return panelResult;
    }
    log.warn('❌ 임시저장 패널에서 글을 찾을 수 없음');
    return {
      success: false,
      usedKey: panelResult.usedKey,
      matchedCount: panelResult.matchedCount,
      listSnippet: panelResult.listSnippet,
      anchorSample: panelResult.anchorSample,
    };
  }

  private async verifyDraftPanelInEditor(
    frame: EditorContext['frame'],
  ): Promise<{
    success: boolean;
    title?: string;
    editUrl?: string;
    draftId?: string;
    usedKey?: 'draftId' | 'title';
    matchedCount?: number;
    listSnippet?: string[];
    anchorSample?: Array<{ href: string; text: string }>;
  }> {
    try {
      const countBtn = frame.locator('button[class*="save_count_btn"], [class*="save_count_btn"]').first();
      if (await countBtn.count() === 0) {
        log.warn('임시저장 패널 검증 실패: count_button_not_found');
        return { success: false };
      }

      for (let attempt = 1; attempt <= 3; attempt++) {
        await countBtn.click({ force: true });
        await frame.waitForTimeout(500);

        const panel = await frame.evaluate(() => {
          const raw = (document.body.innerText || '')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean);

          const sectionIdx = raw.findIndex((line) => line.includes('임시저장 글'));
          if (sectionIdx < 0) {
          return { ok: false, reason: 'panel_text_not_found', count: null, titles: [] as string[] };
          }

          const panelLines = raw.slice(sectionIdx, Math.min(sectionIdx + 40, raw.length));
          const countLine = panelLines.find((line) => /^총\s*\d+개$/.test(line)) || null;
          const count = countLine ? Number((countLine.match(/\d+/) || [])[0]) : null;

          const titles = panelLines.filter(
            (line) =>
              line !== '임시저장 글' &&
              !/^총\s*\d+개$/.test(line) &&
              !/^\d{4}\.\d{2}\.\d{2}/.test(line) &&
              line !== '편집' &&
              line !== '팝업닫기' &&
              line !== '임시저장' &&
              line !== '저장',
          );

          const anchors = Array.from(document.querySelectorAll('a[href]'))
            .map((a) => ({
              href: (a as HTMLAnchorElement).href,
              text: (a.textContent || '').trim(),
            }))
            .filter((item) =>
              /PostWriteForm|Redirect=Write|logNo=|draft|temporary|tmp/i.test(item.href) ||
              /편집|임시저장/.test(item.text),
            );

          return { ok: true, reason: 'ok', count, titles, anchors };
        });

        if (!panel.ok) {
          log.warn(`임시저장 패널 시도 ${attempt}/3 실패: ${panel.reason}`);
          continue;
        }

        const matched = panel.titles.find((title: string) => this.matchExpectedTitle(title));
        if (matched) {
          const matchedAnchor = (panel.anchors || []).find((anchor: { href: string; text: string }) =>
            this.matchExpectedTitle(anchor.text) || /PostWriteForm|Redirect=Write|logNo=|draft|temporary|tmp/i.test(anchor.href),
          );
          const editUrl = matchedAnchor?.href;
          const queryIdMatch = editUrl?.match(/[?&](logNo|documentNo|draftId|postNo)=([^&#]+)/i);
          const pathIdMatch = editUrl?.match(/\/(\d{5,})$/);
          const draftId = queryIdMatch?.[2] ?? pathIdMatch?.[1];
          log.success(`✅ 임시저장 패널에서 글 발견: "${matched}" (count=${panel.count ?? 'n/a'})`);
          return {
            success: true,
            title: matched,
            editUrl,
            draftId,
            usedKey: draftId ? 'draftId' : 'title',
            matchedCount: 1,
            listSnippet: panel.titles.slice(0, 12),
            anchorSample: (panel.anchors || []).slice(0, 12),
          };
        }

        log.warn(`임시저장 패널 제목 미검출 (attempt=${attempt}, count=${panel.count ?? 'n/a'}, titles=${JSON.stringify(panel.titles)})`);
        await frame.waitForTimeout(600);
      }

      return { success: false, usedKey: 'title', matchedCount: 0, listSnippet: [], anchorSample: [] };
    } catch (error: any) {
      log.warn(`임시저장 패널 검증 예외: ${error.message}`);
      return { success: false, usedKey: 'title', matchedCount: 0, listSnippet: [], anchorSample: [] };
    }
  }

  private matchExpectedTitle(candidate: string): boolean {
    const normalizedCandidate = candidate.replace(/\s+/g, ' ').trim();
    const normalizedExpected = this.expectedTitle.replace(/\s+/g, ' ').trim();
    if (!normalizedCandidate || !normalizedExpected) return false;
    if (normalizedCandidate === normalizedExpected) return true;

    const pivot = normalizedExpected.slice(0, Math.min(12, normalizedExpected.length));
    return pivot.length >= 6 && normalizedCandidate.includes(pivot);
  }

  private async waitForSaveSignal(): Promise<void> {
    const { frame, page } = this.ctx;
    for (let i = 0; i < 8; i++) {
      const found = await frame
        .evaluate(() => {
          const text = (document.body.innerText || '').replace(/\s+/g, ' ');
          return /자동저장|저장됨|저장 완료|저장되었습니다/.test(text);
        })
        .catch(() => false);
      if (found) return;
      await page.waitForTimeout(500);
    }
  }

  private async captureFailureEvidence(
    result: TempSaveVerificationResult,
    extra?: {
      used_key?: string;
      matched_count?: number;
      list_snippet?: string[];
      anchor_sample?: Array<{ href: string; text: string }>;
    },
  ): Promise<string | undefined> {
    const { page } = this.ctx;

    try {
      const timestamp = new Date().toISOString();
      const dir = createDebugRunDir('navertimeoutdebug', 'draft_verify_fail');

      const mainPng = path.join(dir, 'draft_verify.png');
      await page.screenshot({ path: mainPng, fullPage: true });
      result.screenshots?.push(mainPng);

      const reportPath = path.join(dir, 'draft_verify.json');
      const report = {
        timestamp,
        expected_title: this.expectedTitle,
        used_key: extra?.used_key ?? 'title',
        matched_count: extra?.matched_count ?? 0,
        list_snippet: extra?.list_snippet ?? [],
        anchor_sample: extra?.anchor_sample ?? [],
        verification_result: result,
        page_url: page.url(),
      };
      fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

      log.info(`📊 실패 보고서 생성: ${reportPath}`);
      return dir;
    } catch (error: any) {
      log.error(`디버깅 정보 수집 실패: ${error.message}`);
      return undefined;
    }
  }
}

export async function verifyTempSaveWithRetry(
  ctx: EditorContext,
  artifactsDir: string,
  expectedTitle: string,
  _expectedBodyPreview: string,
  maxRetries: number = 1,
  retryAction?: () => Promise<boolean>,
): Promise<TempSaveVerificationResult> {
  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    log.info(`임시저장 검증 시도 ${attempt}/${maxRetries + 1}`);

    const verifier = new TempSaveVerifier(ctx, artifactsDir, expectedTitle);
    const result = await verifier.verifyTempSave();
    if (result.success) return result;

    if (attempt > maxRetries) {
      log.error('❌ 최대 재시도 횟수 초과 - 최종 실패');
      return result;
    }

    log.warn(`❌ 검증 실패, ${attempt}/${maxRetries} 재시도...`);
    await stabilizePageState(ctx, artifactsDir);

    if (retryAction) {
      const clicked = await retryAction();
      if (!clicked) log.error('재시도용 임시저장 버튼 클릭 실패');
    }

    await ctx.page.waitForTimeout(2000);
  }

  return {
    success: false,
    verified_via: 'none',
    error_message: '알 수 없는 오류로 검증 실패',
  };
}

export async function stabilizePageState(ctx: EditorContext, artifactsDir: string): Promise<void> {
  const { page } = ctx;

  try {
    log.info('페이지 상태 안정화 중...');
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15_000 });

    const { getEditorFrame, waitForEditorReady, dismissPopups } = await import('./editor');
    const freshFrame = await getEditorFrame(page, artifactsDir);
    if (!freshFrame) {
      log.warn('안정화: 에디터 iframe 재획득 실패');
      return;
    }

    const ready = await waitForEditorReady(freshFrame, artifactsDir, page);
    if (!ready) {
      log.warn('안정화: 에디터 준비 실패');
      return;
    }

    ctx.frame = freshFrame;
    await dismissPopups(freshFrame);
    log.success('페이지 상태 안정화 완료');
  } catch (error: any) {
    log.error(`페이지 안정화 실패: ${error.message}`);
  }
}
