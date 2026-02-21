import { classifyLoginState } from '../../../src/naver/session';

describe('session/login_state false-negative guard', () => {
  test('login redirect URL이라도 로그인 쿠키가 있으면 logged_in', () => {
    const state = classifyLoginState(
      'https://nid.naver.com/nidlogin.login?mode=form',
      false,
      null,
      null,
      true,
    );
    expect(state.state).toBe('logged_in');
    expect(state.signal).toBe('login_cookie_present');
  });

  test('writer iframe 신호가 logout indicator보다 우선', () => {
    const state = classifyLoginState(
      'https://blog.naver.com/test?Redirect=Write&',
      true,
      null,
      '#id',
      false,
    );
    expect(state.state).toBe('logged_in');
    expect(state.signal).toBe('writer_iframe');
  });
});
