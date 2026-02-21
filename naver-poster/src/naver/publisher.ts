/**
 * 네이버 블로그 직접 발행 기능
 * 임시저장 대신 바로 게시하는 함수들
 */

import * as log from '../utils/logger';
import { EditorContext } from './editor';
import { captureFailure } from '../utils/logger';

/**
 * 발행 버튼 클릭 시도
 */
export async function clickPublish(
  ctx: EditorContext,
  artifactsDir: string
): Promise<boolean> {
  log.info('직접 발행 시작...');
  const { page, frame } = ctx;

  const strategies = [
    // 전략 1: iframe 내 "발행" 텍스트 버튼 찾기
    async () => {
      log.info('전략 1: 발행 텍스트 버튼 검색');
      const buttons = await frame.$$('button, a, span[role="button"], div[role="button"]');
      for (const btn of buttons) {
        const text = await btn.textContent();
        if (text && (text.includes('발행') || text.includes('게시') || text.includes('등록')) && await btn.isVisible()) {
          log.info(`발행 버튼 발견: "${text}"`);
          await btn.click();
          return true;
        }
      }
      return false;
    },

    // 전략 2: 발행 관련 CSS 클래스/ID 검색
    async () => {
      log.info('전략 2: 발행 관련 셀렉터 검색');
      const selectors = [
        '.btn_post', '.btn_publish', '.btn_complete',
        '#btn_post', '#btn_publish', '#btn_complete',
        '[class*="publish"]', '[class*="post"]', '[class*="complete"]',
        '.se-toolbar-publish-button', '.se-publish-button',
        '.toolbar_publish', '.toolbar_post'
      ];

      for (const selector of selectors) {
        try {
          const element = await frame.$(selector);
          if (element && await element.isVisible()) {
            log.info(`발행 버튼 발견 (${selector})`);
            await element.click();
            return true;
          }
        } catch (error) {
          // 계속 진행
        }
      }
      return false;
    },

    // 전략 3: 페이지 레벨에서 발행 버튼 찾기 (iframe 외부)
    async () => {
      log.info('전략 3: 메인 페이지에서 발행 버튼 검색');
      const buttons = await page.$$('button, a, span[role="button"], div[role="button"]');
      for (const btn of buttons) {
        const text = await btn.textContent();
        if (text && (text.includes('발행') || text.includes('게시') || text.includes('등록')) && await btn.isVisible()) {
          log.info(`발행 버튼 발견 (메인 페이지): "${text}"`);
          await btn.click();
          return true;
        }
      }
      return false;
    },

    // 전략 4: 임시저장 버튼 근처의 발행 버튼 찾기
    async () => {
      log.info('전략 4: 임시저장 근처 발행 버튼 검색');

      // 먼저 임시저장 버튼을 찾고
      const tempSaveButtons = await frame.$$('button, a, span[role="button"]');
      for (const tempBtn of tempSaveButtons) {
        const text = await tempBtn.textContent();
        if (text && (text.includes('임시저장') || text.includes('저장'))) {
          // 임시저장 버튼 근처의 발행 버튼 찾기
          const nearbyButtons = await tempBtn.evaluate((el) => {
            const parent = el.parentElement?.parentElement;
            if (!parent) return [];
            const buttons = parent.querySelectorAll('button, a, span[role="button"]');
            return Array.from(buttons).map(btn => ({
              text: btn.textContent || '',
              element: btn
            }));
          });

          for (const btnInfo of nearbyButtons) {
            if (btnInfo.text && (btnInfo.text.includes('발행') || btnInfo.text.includes('게시'))) {
              // 실제 버튼 요소를 가져와서 클릭
              const publishBtn = await frame.evaluateHandle((btnText) => {
                const buttons = Array.from(document.querySelectorAll('button, a, span[role="button"]'));
                for (const btn of buttons) {
                  if (btn.textContent?.includes(btnText)) {
                    return btn;
                  }
                }
                return null;
              }, btnInfo.text);

              if (publishBtn && await publishBtn.asElement()?.isVisible()) {
                log.info(`발행 버튼 발견 (임시저장 근처): "${btnInfo.text}"`);
                await publishBtn.asElement()?.click();
                return true;
              }
            }
          }
        }
      }
      return false;
    }
  ];

  // 각 전략 시도
  for (let i = 0; i < strategies.length; i++) {
    try {
      log.info(`발행 전략 ${i + 1} 시도`);
      const result = await strategies[i]();
      if (result) {
        log.success(`발행 버튼 클릭 완료 (전략 ${i + 1})`);
        return true;
      }
      log.warn(`발행 전략 ${i + 1} 실패`);
    } catch (error) {
      log.warn(`발행 전략 ${i + 1} 실패: ${error}`);
    }

    // 각 전략 사이 잠시 대기
    await page.waitForTimeout(1000);
  }

  // 모든 전략 실패
  log.error('모든 발행 전략 실패');
  await captureFailure(page, 'publish_button_not_found', artifactsDir);

  return false;
}

/**
 * 발행 완료 확인
 */
export async function verifyPublished(
  ctx: EditorContext,
  postTitle: string
): Promise<boolean> {
  const { page } = ctx;

  try {
    // 발행 성공 토스트 메시지 확인
    const toastSelectors = [
      '.toast', '.alert', '.notification',
      '[class*="success"]', '[class*="complete"]'
    ];

    for (const selector of toastSelectors) {
      try {
        const toast = await page.waitForSelector(selector, { timeout: 5000 });
        if (toast) {
          const text = await toast.textContent();
          if (text && (text.includes('발행') || text.includes('완료') || text.includes('성공'))) {
            log.success('발행 완료 토스트 메시지 확인');
            return true;
          }
        }
      } catch {
        // 계속 진행
      }
    }

    // URL 변경 확인 (발행 후 블로그 메인으로 리다이렉트될 수 있음)
    await page.waitForTimeout(3000);
    const currentUrl = page.url();
    if (!currentUrl.includes('Write') && !currentUrl.includes('write')) {
      log.success('발행 후 URL 변경 확인');
      return true;
    }

    return false;
  } catch (error) {
    log.error(`발행 확인 중 오류: ${error}`);
    return false;
  }
}