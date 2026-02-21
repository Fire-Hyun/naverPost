import { isTempSaveSuccessSignal } from '../../../src/naver/temp_save_state_machine';

describe('post/draft_save success signal detection', () => {
  test('임시저장 성공 토스트를 감지한다', () => {
    expect(isTempSaveSuccessSignal('임시 저장 완료')).toBe(true);
    expect(isTempSaveSuccessSignal('저장되었습니다.')).toBe(true);
    expect(isTempSaveSuccessSignal('자동저장')).toBe(true);
  });

  test('실패/무관 문구는 성공으로 오탐하지 않는다', () => {
    expect(isTempSaveSuccessSignal('저장 실패')).toBe(false);
    expect(isTempSaveSuccessSignal('네트워크 오류로 다시 시도')).toBe(false);
    expect(isTempSaveSuccessSignal('')).toBe(false);
  });
});
