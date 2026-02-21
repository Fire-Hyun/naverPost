import { detectCrossOsProfileUnusable } from '../../src/naver/session';

describe('cross OS profile usability detection', () => {
  test('linux + /mnt/c + empty cookies 이면 unusable', () => {
    expect(detectCrossOsProfileUnusable('linux', '/mnt/c/naverProfile_bot', [])).toBe(true);
  });

  test('linux + /mnt/c + NID 쿠키 없음이면 unusable', () => {
    expect(
      detectCrossOsProfileUnusable('linux', '/mnt/c/naverProfile_bot', ['NNB', 'NID_JKL']),
    ).toBe(true);
  });

  test('linux + /mnt/c + NID_SES 있으면 usable', () => {
    expect(
      detectCrossOsProfileUnusable('linux', '/mnt/c/naverProfile_bot', ['NID_SES', 'NNB']),
    ).toBe(false);
  });

  test('linux라도 /mnt/c가 아니면 cross OS unusable로 보지 않음', () => {
    expect(
      detectCrossOsProfileUnusable('linux', '/home/mini/.secrets/naver_user_data_dir', []),
    ).toBe(false);
  });

  test('windows 플랫폼이면 false', () => {
    expect(detectCrossOsProfileUnusable('win32', '/mnt/c/naverProfile_bot', [])).toBe(false);
  });
});
