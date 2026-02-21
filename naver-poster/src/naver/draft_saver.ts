import * as fs from 'fs';
import * as path from 'path';
import * as log from '../utils/logger';
import { ensureDebugRootDir } from '../common/debug_paths';
import type { EditorContext, TempSaveClickResult } from './editor';
import { RecoveryManager } from './recovery_manager';
import { SignalDetector } from './signal_detector';
import { UploadPipeline, UploadState } from './upload_pipeline';
import { collectTimeoutDebugArtifacts } from './timeout_debug';

export class DraftSaveTimeoutError extends Error {
  constructor(message: string) {
    super(message);
  }
}

export class SessionBlockedError extends Error {
  constructor(message: string) {
    super(message);
  }
}

type DraftSaverOptions = {
  ctx: EditorContext;
  clickSave: () => Promise<boolean>;
  prepare: () => Promise<void>;
  detectOverlay: () => Promise<boolean>;
  closeOverlay: () => Promise<void>;
  reacquireFrame: () => Promise<boolean>;
  signalTimeBudgetMs: number;
  pollIntervalMs?: number;
  maxRecoveryCount?: number;
  debugPath?: string;
  stepName?: string;
  verifyPersisted?: (meta: {
    via?: TempSaveClickResult['via'];
    detectedDraftId?: string;
    detectedDraftEditUrl?: string;
  }) => Promise<{ ok: boolean; reason?: string; debugPath?: string }>;
};

export class DraftSaver {
  private readonly options: DraftSaverOptions;

  constructor(options: DraftSaverOptions) {
    this.options = options;
  }

  async save(): Promise<TempSaveClickResult> {
    const pollIntervalMs = this.options.pollIntervalMs ?? 300;
    let spinnerSeen = false;
    const stepName = this.options.stepName ?? 'draft_save_wait';
    const debugRoot = ensureDebugRootDir('navertimeoutdebug');
    const expectedConditions = ['toast_text', 'status_text_change', 'autosave_network_2xx', 'spinner_cycle', 'dialog_accept'];
    const responsePattern = /(autosave|temp|temporary|draft|save|postwrite|PostWriteForm)/i;
    let networkSuccess = false;
    let networkSignal = '';
    let detectedDraftId = '';
    let detectedDraftEditUrl = '';
    let dialogAccepted = false;
    let dialogMessage = '';
    const consoleLogs: string[] = [];
    const frameStatuses = new Map<string, string>();
    const statusRegex = /임시|저장|자동저장/i;
    let baselineStatusText = '';
    let lastObservedStatusText = '';
    const tracePath = path.join(debugRoot, `trace_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`);
    let traceStarted = false;

    const detector = new SignalDetector({
      page: this.options.ctx.page,
      frameRef: () => this.options.ctx.frame,
    });

    const onDialog = async (dialog: import('playwright').Dialog) => {
      dialogAccepted = true;
      dialogMessage = dialog.message();
      try {
        await dialog.accept();
      } catch {
        // ignore
      }
    };
    const onResponse = (res: import('playwright').Response) => {
      try {
        const url = res.url();
        if (!responsePattern.test(url)) return;
        const idMatch = url.match(/[?&](logNo|documentNo|draftId|postNo)=([^&#]+)/i);
        if (idMatch) {
          detectedDraftId = detectedDraftId || idMatch[2];
          detectedDraftEditUrl = detectedDraftEditUrl || url;
        }
        if (res.status() === 200 || res.status() === 201) {
          networkSuccess = true;
          networkSignal = `${res.status()} ${url}`;
        }
      } catch {
        // ignore
      }
    };
    const onConsole = (msg: import('playwright').ConsoleMessage) => {
      const text = `[${msg.type()}] ${msg.text()}`.slice(0, 500);
      if (consoleLogs.length >= 50) consoleLogs.shift();
      consoleLogs.push(text);
    };

    const captureDebug = async (reason: string): Promise<string | null> => {
      try {
        fs.mkdirSync(debugRoot, { recursive: true });
        const result = await collectTimeoutDebugArtifacts({
          page: this.options.ctx.page as any,
          frame: this.options.ctx.frame as any,
          reason,
          currentStage: stepName,
          lastActivityLabel: stepName,
          lastActivityAgeMs: 0,
          watchdogLimitSeconds: Math.ceil(this.options.signalTimeBudgetMs / 1000),
          silenceWatchdogSeconds: Math.max(1, Math.ceil((this.options.pollIntervalMs ?? 300) / 1000)),
          editorReadyProbe: null,
          debugRootDir: debugRoot,
        });
        const frameList = this.options.ctx.page.frames().map((frame) => ({
          name: frame.name(),
          url: frame.url(),
          save_btn_hint: frameStatuses.get(frame.url()) ?? 'unknown',
        }));
        const extraPath = path.join(result.debugDir, 'draft_wait_debug.json');
        fs.writeFileSync(extraPath, JSON.stringify({
          stepName,
          expected_conditions: expectedConditions,
          observed: {
            networkSuccess,
            networkSignal,
            dialogAccepted,
            dialogMessage,
            spinnerSeen,
            baselineStatusText,
            lastObservedStatusText,
          },
          page_url: this.options.ctx.page.url(),
          frame_list: frameList,
          console_logs: consoleLogs,
          trace_path: traceStarted ? tracePath : null,
          timestamp: new Date().toISOString(),
        }, null, 2), 'utf-8');
        return result.debugDir;
      } catch (error) {
        log.warn(`[draft] debug capture failed: ${String(error)}`);
        return null;
      }
    };

    const recoveryManager = new RecoveryManager({
      detectOverlay: this.options.detectOverlay,
      closeOverlay: this.options.closeOverlay,
      reacquireFrame: this.options.reacquireFrame,
    });

    const readStatusText = async () => {
      try {
        const text = await this.options.ctx.frame.evaluate(() => {
          const body = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
          return body.slice(0, 2000);
        });
        const match = text.match(/(임시저장[^.\n]{0,40}|자동저장[^.\n]{0,40}|저장[^.\n]{0,40})/i);
        return match?.[1]?.trim() ?? '';
      } catch {
        return '';
      }
    };

    const waitForSignals = async () => {
      const deadline = Date.now() + this.options.signalTimeBudgetMs;
      while (Date.now() < deadline) {
        for (const frame of this.options.ctx.page.frames()) {
          if (frameStatuses.has(frame.url())) continue;
          try {
            const hit = await frame.evaluate((selectors) => {
              return selectors.some((sel) => !!document.querySelector(sel));
            }, ['.btn_save', '[class*="save_btn"]', '[data-name="save"]', 'button[aria-label*="저장"]']);
            frameStatuses.set(frame.url(), hit ? 'found' : 'not_found');
          } catch {
            frameStatuses.set(frame.url(), 'eval_failed');
          }
        }

        if (!baselineStatusText) {
          baselineStatusText = await readStatusText();
        }
        const currentStatus = await readStatusText();
        if (currentStatus) {
          lastObservedStatusText = currentStatus;
        }

        const signals = await detector.detect();
        if (signals.sessionBlocked) {
          return { success: false, timeout: false, sessionBlocked: true };
        }
        if (signals.toast) {
          return { success: true, timeout: false, sessionBlocked: false, via: 'toast' as const };
        }
        if (networkSuccess) {
          return { success: true, timeout: false, sessionBlocked: false, via: 'network_2xx' as const };
        }
        if (dialogAccepted && statusRegex.test(dialogMessage)) {
          return { success: true, timeout: false, sessionBlocked: false, via: 'dialog' as const };
        }
        if (currentStatus && statusRegex.test(currentStatus) && currentStatus !== baselineStatusText) {
          return { success: true, timeout: false, sessionBlocked: false, via: 'status_text' as const };
        }
        if (signals.spinner) {
          spinnerSeen = true;
        } else if (spinnerSeen) {
          return { success: true, timeout: false, sessionBlocked: false, via: 'spinner_cycle' as const };
        }
        if (signals.status) {
          return { success: true, timeout: false, sessionBlocked: false, via: 'status_text' as const };
        }
        await this.options.ctx.frame.waitForTimeout(pollIntervalMs).catch(() => undefined);
      }
      return { success: false, timeout: true, sessionBlocked: false };
    };

    let lastSignalVia: TempSaveClickResult['via'];

    const pipeline = new UploadPipeline(
      {
        openEditor: async () => ({ ok: true }),
        writeContent: async () => ({ ok: true }),
        clickSave: async () => {
          await this.options.prepare();
          const clicked = await this.options.clickSave();
          return clicked ? { ok: true } : { ok: false, reason: 'save_button_not_found' };
        },
        waitSave: async () => {
          const result = await waitForSignals();
          if (result.success) {
            lastSignalVia = result.via;
            return { success: true, timeout: false, sessionBlocked: false };
          }
          return result;
        },
        recover: async () => {
          const recovered = await recoveryManager.recover();
          return recovered.recovered
            ? { ok: true }
            : { ok: false, reason: 'recovery_failed_overlay_or_frame' };
        },
      },
      {
        maxRecoveryCount: this.options.maxRecoveryCount ?? 1,
        stateTimeoutMs: {
          [UploadState.INIT]: 1_000,
          [UploadState.OPEN_EDITOR]: 5_000,
          [UploadState.WRITE_CONTENT]: 5_000,
          [UploadState.CLICK_SAVE]: 8_000,
          [UploadState.WAIT_SAVE]: this.options.signalTimeBudgetMs,
          [UploadState.RECOVERY]: 6_000,
        },
      },
    );

    try {
      this.options.ctx.page.on('dialog', onDialog);
      this.options.ctx.page.on('response', onResponse);
      this.options.ctx.page.on('console', onConsole);
      await this.options.ctx.page.context().tracing.start({
        screenshots: true,
        snapshots: true,
        sources: false,
      }).then(() => {
        traceStarted = true;
      }).catch(() => undefined);

      const result = await pipeline.run();
      if (result.success) {
        if (this.options.verifyPersisted) {
          const persisted = await this.options.verifyPersisted({
            via: lastSignalVia,
            detectedDraftId: detectedDraftId || undefined,
            detectedDraftEditUrl: detectedDraftEditUrl || undefined,
          });
          if (!persisted.ok) {
            return {
              success: false,
              error: `DRAFT_NOT_FOUND_AFTER_SUCCESS_SIGNAL reason=${persisted.reason ?? 'unknown'} debugPath=${persisted.debugPath ?? 'n/a'}`,
              via: lastSignalVia,
              retries: result.recoveryCount,
              draftId: detectedDraftId || undefined,
              draftEditUrl: detectedDraftEditUrl || undefined,
            };
          }
        }
        if (traceStarted) {
          await this.options.ctx.page.context().tracing.stop().catch(() => undefined);
        }
        return {
          success: true,
          via: lastSignalVia,
          retries: result.recoveryCount,
          draftId: detectedDraftId || undefined,
          draftEditUrl: detectedDraftEditUrl || undefined,
        };
      }
      if (result.failureReason === 'session_blocked') {
        await captureDebug('session_blocked');
        if (traceStarted) {
          await this.options.ctx.page.context().tracing.stop({ path: tracePath }).catch(() => undefined);
        }
        throw new SessionBlockedError('SessionBlockedError: login/captcha/permission detected');
      }
      const debugDir = await captureDebug(result.failureReason || 'save_timeout');
      if (traceStarted) {
        await this.options.ctx.page.context().tracing.stop({ path: tracePath }).catch(() => undefined);
      }
      throw new DraftSaveTimeoutError(
        `DraftSaveTimeout: ${JSON.stringify({
          waitedFor: ['toast', 'statusTextChanged', 'draftApi200', 'spinnerCycle', 'dialog'],
          observed: {
            popup: await this.options.detectOverlay().catch(() => false),
            overlay: await this.options.detectOverlay().catch(() => false),
            frameReattached: result.recoveryCount > 0,
            toastDetected: lastSignalVia === 'toast',
            networkSignal,
            statusText: lastObservedStatusText || null,
            dialogAccepted,
          },
          retryCount: result.recoveryCount,
          debugPath: debugDir ?? this.options.debugPath ?? null,
        })}`,
      );
    } catch (error) {
      if (error instanceof SessionBlockedError) {
        return { success: false, error: error.message };
      }
      if (error instanceof DraftSaveTimeoutError) {
        log.error(error.message);
        return { success: false, error: error.message };
      }
      return { success: false, error: String(error) };
    } finally {
      this.options.ctx.page.off('dialog', onDialog);
      this.options.ctx.page.off('response', onResponse);
      this.options.ctx.page.off('console', onConsole);
    }
  }
}
