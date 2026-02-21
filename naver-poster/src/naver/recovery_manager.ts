export class OverlayBlockingError extends Error {
  constructor(message = 'Overlay blocking editor interaction') {
    super(message);
  }
}

export type RecoveryContext = {
  detectOverlay: () => Promise<boolean>;
  closeOverlay: () => Promise<void>;
  reacquireFrame: () => Promise<boolean>;
};

export type RecoveryResult = {
  attempted: boolean;
  overlayHandled: boolean;
  frameReattached: boolean;
  recovered: boolean;
};

export class RecoveryManager {
  private readonly context: RecoveryContext;

  constructor(context: RecoveryContext) {
    this.context = context;
  }

  async recover(): Promise<RecoveryResult> {
    let overlayHandled = false;
    let frameReattached = false;

    const overlay = await this.context.detectOverlay();
    if (overlay) {
      await this.context.closeOverlay();
      overlayHandled = true;
    }

    frameReattached = await this.context.reacquireFrame();

    return {
      attempted: true,
      overlayHandled,
      frameReattached,
      recovered: overlayHandled || frameReattached,
    };
  }
}
