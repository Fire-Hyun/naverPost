/**
 * T1: baselineCount 전달 시 DUPLICATED 오탐 방지 (에디터 잔존 이미지 차감)
 * T2: Step G 폴링 — 첫 번째 쿼리에서 0이어도 재시도 후 성공
 * T3: Step G 프레임 재탐색 — 전달받은 frame이 stale일 때 page.frames()에서 올바른 frame 탐색
 * T4: Step G 판정 완화 — 폴링 + 재탐색 모두 0/N이면 IMAGE_VERIFY_POSTSAVE_FAILED (경고)
 */

import { verifyImageReferencesInEditor, getEditorImageState } from '../../src/naver/editor';
import type { Frame, Page } from 'playwright';

// ────────────────────────────────────────────────────────────────
// mock helpers
// ────────────────────────────────────────────────────────────────

function makeFrame(imgCountSeq: number[]): Frame {
  let callIdx = 0;
  const frame = {
    evaluate: jest.fn().mockImplementation(() => {
      const n = imgCountSeq[Math.min(callIdx++, imgCountSeq.length - 1)];
      const refs = Array.from({ length: n }, (_, i) => `https://blogfiles.naver.net/img${i}.jpg`);
      return Promise.resolve({ count: n, refs: refs.slice(0, 10) });
    }),
    $: jest.fn().mockResolvedValue(null),
    waitForTimeout: jest.fn().mockResolvedValue(undefined),
  } as unknown as Frame;
  return frame;
}

function makePage(frames: Frame[]): Page {
  return {
    frames: jest.fn().mockReturnValue(frames),
  } as unknown as Page;
}

/** 에디터 selector를 가진 frame 모의 */
function makeEditorFrame(imgCount: number): Frame {
  const frame = {
    evaluate: jest.fn().mockResolvedValue({
      count: imgCount,
      refs: Array.from({ length: imgCount }, (_, i) => `https://blogfiles.naver.net/img${i}.jpg`),
    }),
    $: jest.fn().mockImplementation((sel: string) => {
      if (sel.includes('se-content-area') || sel.includes('se-viewer') || sel.includes('se-editor') || sel.includes('smarteditor_editor')) {
        return Promise.resolve({ tagName: 'DIV' }); // element found
      }
      return Promise.resolve(null);
    }),
    waitForTimeout: jest.fn().mockResolvedValue(undefined),
  } as unknown as Frame;
  return frame;
}

// ────────────────────────────────────────────────────────────────
// T1: baselineCount 전달 시 DUPLICATED 오탐 방지
// ────────────────────────────────────────────────────────────────
describe('T1: baselineCount 전달 시 DUPLICATED 오탐 방지', () => {
  test('에디터에 2개 잔존(baseline=2) + 7개 업로드 → 조정 후 7/7 성공', async () => {
    // 총 9개(잔존2 + 신규7), expected=7, baseline=2 → adjusted=9-2=7 → 성공
    const frame = makeFrame([9]);
    const result = await verifyImageReferencesInEditor(frame, 7, { baselineCount: 2 });
    expect(result.success).toBe(true);
    expect(result.image_count).toBe(7);
    expect(result.message).toContain('검증 성공');
    expect(result.message).toContain('기준값 차감');
  });

  test('baseline=0, count=7, expected=7 → 기존 동작 그대로 성공', async () => {
    const frame = makeFrame([7]);
    const result = await verifyImageReferencesInEditor(frame, 7, { baselineCount: 0 });
    expect(result.success).toBe(true);
    expect(result.image_count).toBe(7);
  });

  test('baseline=0, count=9, expected=7 → IMAGE_UPLOAD_DUPLICATED', async () => {
    // 첫 번째 쿼리 = 9, 폴링 후에도 9
    const frame = makeFrame([9, 9, 9, 9, 9]);
    const result = await verifyImageReferencesInEditor(frame, 7, { baselineCount: 0 });
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('IMAGE_UPLOAD_DUPLICATED');
  });
});

// ────────────────────────────────────────────────────────────────
// T2: Step G 폴링 — 첫 번째 쿼리 0, 재시도 후 성공
// ────────────────────────────────────────────────────────────────
describe('T2: Step G 폴링 — 지연 후 이미지 등장', () => {
  test('1차 0, 2차 7 → 폴링으로 성공', async () => {
    // 첫 evaluate 호출: 0, 두 번째: 7
    const frame = makeFrame([0, 7]);
    const result = await verifyImageReferencesInEditor(frame, 7, { baselineCount: 0 });
    expect(result.success).toBe(true);
    expect(result.image_count).toBe(7);
  });

  test('1차 3, 2차 7 → 폴링으로 성공 (STUCK 아님)', async () => {
    const frame = makeFrame([3, 7]);
    const result = await verifyImageReferencesInEditor(frame, 7, { baselineCount: 0 });
    expect(result.success).toBe(true);
    expect(result.image_count).toBe(7);
  });
});

// ────────────────────────────────────────────────────────────────
// T3: Step G 프레임 재탐색 — stale frame 복구
// ────────────────────────────────────────────────────────────────
describe('T3: Step G 프레임 재탐색 — stale frame 시 page.frames() 사용', () => {
  test('전달받은 frame이 항상 0반환 → page.frames()의 에디터 frame에서 7 발견 → 성공', async () => {
    // 전달받은 frame은 항상 0 반환
    const staleFrame = makeFrame([0, 0, 0, 0, 0]);

    // page.frames()에 에디터 frame (7개) 포함
    const editorFrame = makeEditorFrame(7);
    const dummyFrame = makeFrame([0, 0, 0, 0, 0]); // 에디터 아닌 frame
    const page = makePage([dummyFrame, editorFrame]);

    const result = await verifyImageReferencesInEditor(staleFrame, 7, { page, baselineCount: 0 });
    expect(result.success).toBe(true);
    expect(result.image_count).toBe(7);
  });
});

// ────────────────────────────────────────────────────────────────
// T4: Step G 판정 완화 — 폴링 + 재탐색 모두 0/N → IMAGE_VERIFY_POSTSAVE_FAILED
// ────────────────────────────────────────────────────────────────
describe('T4: Step G 판정 완화 — 0/N은 FAIL이 아닌 WARNING', () => {
  test('모든 폴링 + 재탐색에서 0 → IMAGE_VERIFY_POSTSAVE_FAILED, success=false', async () => {
    const staleFrame = makeFrame([0, 0, 0, 0, 0]);
    // page.frames()에도 에디터 DOM 없음 (모두 dummyFrame)
    const dummyFrame = {
      evaluate: jest.fn().mockResolvedValue({ count: 0, refs: [] }),
      $: jest.fn().mockResolvedValue(null), // 에디터 selector 없음
      waitForTimeout: jest.fn().mockResolvedValue(undefined),
    } as unknown as Frame;
    const page = makePage([dummyFrame]);

    const result = await verifyImageReferencesInEditor(staleFrame, 7, { page, baselineCount: 0 });
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('IMAGE_VERIFY_POSTSAVE_FAILED');
    expect(result.image_count).toBe(0);
    expect(result.message).toContain('임시저장은 성공');
  });

  test('expectedCount=0이면 항상 성공 (이미지 없는 포스트)', async () => {
    const frame = makeFrame([0]);
    const result = await verifyImageReferencesInEditor(frame, 0, {});
    expect(result.success).toBe(true);
    expect(result.message).toContain('미요청');
  });
});

// ────────────────────────────────────────────────────────────────
// getEditorImageState export 확인
// ────────────────────────────────────────────────────────────────
describe('getEditorImageState export 확인', () => {
  test('frame.evaluate 결과를 그대로 반환', async () => {
    const frame = {
      evaluate: jest.fn().mockResolvedValue({ count: 3, refs: ['a', 'b', 'c'] }),
    } as unknown as Frame;
    const state = await getEditorImageState(frame);
    expect(state.count).toBe(3);
    expect(state.refs).toHaveLength(3);
  });

  test('frame.evaluate 예외 시 { count:0, refs:[] } 반환', async () => {
    const frame = {
      evaluate: jest.fn().mockRejectedValue(new Error('stale')),
    } as unknown as Frame;
    const state = await getEditorImageState(frame);
    expect(state.count).toBe(0);
    expect(state.refs).toHaveLength(0);
  });
});
