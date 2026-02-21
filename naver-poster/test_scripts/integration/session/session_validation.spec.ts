import { detectSecurityChallengeSignal } from '../../../src/worker/session_validation';

describe('session_validation', () => {
  test('유효 세션 텍스트는 보안챌린지로 오탐하지 않는다', () => {
    const result = detectSecurityChallengeSignal({
      url: 'https://blog.naver.com/jun12310?Redirect=Write&',
      bodyText: '블로그 글쓰기 화면입니다. 임시저장 버튼이 보입니다.',
    });
    expect(result).toBe(false);
  });

  test('만료/리다이렉트는 보안챌린지와 구분된다', () => {
    const result = detectSecurityChallengeSignal({
      url: 'https://nid.naver.com/nidlogin.login',
      bodyText: '아이디 비밀번호를 입력하세요.',
    });
    expect(result).toBe(false);
  });

  test('보안확인/2FA 텍스트를 감지한다', () => {
    const result = detectSecurityChallengeSignal({
      url: 'https://nid.naver.com/user2/help',
      bodyText: '보안 확인을 위해 인증번호(OTP)를 입력하고 새로운 기기를 인증하세요.',
    });
    expect(result).toBe(true);
  });
});

