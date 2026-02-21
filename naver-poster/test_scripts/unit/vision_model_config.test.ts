import { resolveVisionModelForImageMatcher } from '../../src/utils/image_matcher';
import { resolveVisionModel } from '../../src/utils/image_placer';

describe('vision model config', () => {
  const originalOpenAiVision = process.env.OPENAI_VISION_MODEL;
  const originalVision = process.env.VISION_MODEL;

  afterEach(() => {
    if (originalOpenAiVision === undefined) {
      delete process.env.OPENAI_VISION_MODEL;
    } else {
      process.env.OPENAI_VISION_MODEL = originalOpenAiVision;
    }
    if (originalVision === undefined) {
      delete process.env.VISION_MODEL;
    } else {
      process.env.VISION_MODEL = originalVision;
    }
  });

  test('T4: env 미설정이면 기본 모델은 gpt-5.2', () => {
    delete process.env.OPENAI_VISION_MODEL;
    delete process.env.VISION_MODEL;
    expect(resolveVisionModelForImageMatcher()).toBe('gpt-5.2');
    expect(resolveVisionModel()).toBe('gpt-5.2');
  });

  test('T4: OPENAI_VISION_MODEL 설정값을 우선 사용한다', () => {
    process.env.OPENAI_VISION_MODEL = 'gpt-5.2';
    process.env.VISION_MODEL = 'gpt-4.1-mini';
    expect(resolveVisionModelForImageMatcher()).toBe('gpt-5.2');
    expect(resolveVisionModel()).toBe('gpt-5.2');
  });
});
