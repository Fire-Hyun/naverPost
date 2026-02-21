import { TempSaveVerifier } from '../../src/naver/temp_save_verifier';

describe('draft verify flow fixture', () => {
  test('1차 성공 신호가 있어도 draft 실재 검증 실패면 최종 실패', async () => {
    const verifier = new TempSaveVerifier(
      { page: {} as any, frame: {} as any },
      '/tmp',
      '테스트 제목',
    ) as any;
    const calls: string[] = [];

    verifier.verifyToastMessage = async () => {
      calls.push('toast');
      return { success: true, message: '임시저장 완료' };
    };
    verifier.verifyDraftPersisted = async () => {
      calls.push('persist');
      return {
        success: false,
        usedKey: 'title',
        matchedCount: 0,
        listSnippet: [],
        anchorSample: [],
      };
    };
    verifier.captureFailureEvidence = async () => '/tmp/naver_editor_debug/test_draft_verify_fail';

    const result = await verifier.verifyTempSave();
    expect(calls).toEqual(['toast', 'persist']);
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('DRAFT_NOT_FOUND_AFTER_SUCCESS_SIGNAL');
    expect(result.verified_via).toBe('toast');
  });

  test('draft 실재 검증 통과 후에만 최종 성공', async () => {
    const verifier = new TempSaveVerifier(
      { page: {} as any, frame: {} as any },
      '/tmp',
      '테스트 제목',
    ) as any;

    verifier.verifyToastMessage = async () => ({ success: true, message: '임시저장 완료' });
    verifier.verifyDraftPersisted = async () => ({
      success: true,
      title: '테스트 제목',
      editUrl: 'https://blog.naver.com/PostWriteForm.naver?logNo=12345',
      draftId: '12345',
      usedKey: 'draftId',
      matchedCount: 1,
      listSnippet: ['테스트 제목'],
      anchorSample: [{ href: 'https://blog.naver.com/PostWriteForm.naver?logNo=12345', text: '편집' }],
    });

    const result = await verifier.verifyTempSave();
    expect(result.success).toBe(true);
    expect(result.reason_code).toBe('DRAFT_VERIFIED');
    expect(result.verified_via).toBe('both');
    expect(result.draft_id).toBe('12345');
  });
});
