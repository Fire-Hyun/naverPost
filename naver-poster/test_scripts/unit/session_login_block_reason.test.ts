import { inferLoginBlockedReason } from '../../src/naver/session';

describe('session login block reason classification', () => {
  test('captcha 신호는 CAPTCHA_DETECTED로 분류', () => {
    const reason = inferLoginBlockedReason({
      captcha: true,
      twoFactor: false,
      securityConfirm: false,
      agreement: false,
      loginFormVisible: false,
    });
    expect(reason).toBe('CAPTCHA_DETECTED');
  });

  test('2FA 신호는 TWO_FACTOR_REQUIRED로 분류', () => {
    const reason = inferLoginBlockedReason({
      captcha: false,
      twoFactor: true,
      securityConfirm: false,
      agreement: false,
      loginFormVisible: false,
    });
    expect(reason).toBe('TWO_FACTOR_REQUIRED');
  });

  test('보안확인 신호는 SECURITY_CONFIRM_REQUIRED로 분류', () => {
    const reason = inferLoginBlockedReason({
      captcha: false,
      twoFactor: false,
      securityConfirm: true,
      agreement: false,
      loginFormVisible: false,
    });
    expect(reason).toBe('SECURITY_CONFIRM_REQUIRED');
  });

  test('약관 신호는 AGREEMENT_REQUIRED로 분류', () => {
    const reason = inferLoginBlockedReason({
      captcha: false,
      twoFactor: false,
      securityConfirm: false,
      agreement: true,
      loginFormVisible: false,
    });
    expect(reason).toBe('AGREEMENT_REQUIRED');
  });

  test('로그인 폼 노출은 LOGIN_FORM_STILL_VISIBLE로 분류', () => {
    const reason = inferLoginBlockedReason({
      captcha: false,
      twoFactor: false,
      securityConfirm: false,
      agreement: false,
      loginFormVisible: true,
    });
    expect(reason).toBe('LOGIN_FORM_STILL_VISIBLE');
  });
});
