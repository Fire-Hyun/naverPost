export enum UploadState {
  INIT = 'INIT',
  OPEN_EDITOR = 'OPEN_EDITOR',
  WRITE_CONTENT = 'WRITE_CONTENT',
  CLICK_SAVE = 'CLICK_SAVE',
  WAIT_SAVE = 'WAIT_SAVE',
  RECOVERY = 'RECOVERY',
  SUCCESS = 'SUCCESS',
  FAILED = 'FAILED',
}

export type StateActionResult = {
  ok: boolean;
  reason?: string;
};

export type WaitSaveResult = {
  success: boolean;
  timeout: boolean;
  sessionBlocked: boolean;
};

export type UploadPipelineDeps = {
  openEditor: () => Promise<StateActionResult>;
  writeContent: () => Promise<StateActionResult>;
  clickSave: () => Promise<StateActionResult>;
  waitSave: () => Promise<WaitSaveResult>;
  recover: () => Promise<StateActionResult>;
};

export type UploadPipelineOptions = {
  maxRecoveryCount: number;
  stateTimeoutMs: Record<Exclude<UploadState, UploadState.SUCCESS | UploadState.FAILED>, number>;
};

export type UploadPipelineResult = {
  success: boolean;
  state: UploadState;
  history: UploadState[];
  recoveryCount: number;
  failureReason?: string;
};

export class UploadPipeline {
  private readonly deps: UploadPipelineDeps;
  private readonly options: UploadPipelineOptions;

  constructor(deps: UploadPipelineDeps, options: UploadPipelineOptions) {
    this.deps = deps;
    this.options = options;
  }

  async run(): Promise<UploadPipelineResult> {
    let state: UploadState = UploadState.INIT;
    const history: UploadState[] = [];
    let recoveryCount = 0;
    let failureReason: string | undefined;

    while (state !== UploadState.SUCCESS && state !== UploadState.FAILED) {
      history.push(state);
      try {
        switch (state) {
          case UploadState.INIT:
            state = UploadState.OPEN_EDITOR;
            break;
          case UploadState.OPEN_EDITOR: {
            const result = await this.runAction(state, this.deps.openEditor);
            state = result.ok ? UploadState.WRITE_CONTENT : UploadState.FAILED;
            if (!result.ok) failureReason = result.reason || 'open_editor_failed';
            break;
          }
          case UploadState.WRITE_CONTENT: {
            const result = await this.runAction(state, this.deps.writeContent);
            state = result.ok ? UploadState.CLICK_SAVE : UploadState.FAILED;
            if (!result.ok) failureReason = result.reason || 'write_content_failed';
            break;
          }
          case UploadState.CLICK_SAVE: {
            const result = await this.runAction(state, this.deps.clickSave);
            state = result.ok ? UploadState.WAIT_SAVE : UploadState.FAILED;
            if (!result.ok) failureReason = result.reason || 'click_save_failed';
            break;
          }
          case UploadState.WAIT_SAVE: {
            const result = await this.runWaitSave(state, this.deps.waitSave);
            if (result.success) {
              state = UploadState.SUCCESS;
            } else if (result.sessionBlocked) {
              state = UploadState.FAILED;
              failureReason = 'session_blocked';
            } else if (result.timeout && recoveryCount < this.options.maxRecoveryCount) {
              state = UploadState.RECOVERY;
            } else {
              state = UploadState.FAILED;
              failureReason = result.timeout ? 'save_timeout' : 'save_failed';
            }
            break;
          }
          case UploadState.RECOVERY: {
            recoveryCount += 1;
            const result = await this.runAction(state, this.deps.recover);
            if (result.ok) {
              state = UploadState.CLICK_SAVE;
            } else {
              state = UploadState.FAILED;
              failureReason = result.reason || 'recovery_failed';
            }
            break;
          }
          default:
            state = UploadState.FAILED;
            failureReason = 'invalid_state';
        }
      } catch (error) {
        state = UploadState.FAILED;
        failureReason = error instanceof Error ? error.message : String(error);
      }
    }

    history.push(state);
    return {
      success: state === UploadState.SUCCESS,
      state,
      history,
      recoveryCount,
      failureReason,
    };
  }

  private async runAction(
    state: Exclude<UploadState, UploadState.SUCCESS | UploadState.FAILED>,
    fn: () => Promise<StateActionResult>,
  ): Promise<StateActionResult> {
    const timeoutMs = this.options.stateTimeoutMs[state];
    return await withTimeout(fn, timeoutMs, `[STATE_TIMEOUT] state=${state} timeoutMs=${timeoutMs}`);
  }

  private async runWaitSave(
    state: Exclude<UploadState, UploadState.SUCCESS | UploadState.FAILED>,
    fn: () => Promise<WaitSaveResult>,
  ): Promise<WaitSaveResult> {
    const timeoutMs = this.options.stateTimeoutMs[state];
    return await withTimeout(fn, timeoutMs, `[STATE_TIMEOUT] state=${state} timeoutMs=${timeoutMs}`);
  }
}

async function withTimeout<T>(fn: () => Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let handle: ReturnType<typeof setTimeout> | null = null;
  const timeoutPromise = new Promise<never>((_, reject) => {
    handle = setTimeout(() => reject(new Error(message)), timeoutMs);
  });

  try {
    return await Promise.race([fn(), timeoutPromise]);
  } finally {
    if (handle) clearTimeout(handle);
  }
}
