import * as fs from 'fs';
import * as path from 'path';
import type { TopicSection } from './topic_organizer';
import * as log from './logger';

export interface ImagePlacement {
  imageIndex: number;
  sectionIndex: number;
  paragraphIndex: number;
  confidence: number;
  mode: 'vision' | 'fallback';
}

type SectionDecision = {
  sectionTitle: string | 'UNKNOWN';
  confidence: number;
  scoreGap?: number;
};

export type SectionMatcher = (
  imageSource: string,
  sections: TopicSection[],
) => Promise<SectionDecision>;

type VisionMatcherOptions = {
  model?: string;
  detail?: 'low' | 'high' | 'auto';
};

type OpenAIResponse = {
  choices?: Array<{
    message?: {
      content?: string;
    };
  }>;
};

export function resolveVisionModel(defaultModel: string = 'gpt-5.2'): string {
  return process.env.OPENAI_VISION_MODEL ?? process.env.VISION_MODEL ?? defaultModel;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function imageToInputPart(imageSource: string, detail: 'low' | 'high' | 'auto'): Record<string, unknown> {
  if (/^https?:\/\//i.test(imageSource)) {
    return { type: 'image_url', image_url: { url: imageSource, detail } };
  }
  const absPath = path.resolve(imageSource);
  const ext = path.extname(absPath).toLowerCase();
  const mime = ext === '.png'
    ? 'image/png'
    : ext === '.webp'
      ? 'image/webp'
      : ext === '.gif'
        ? 'image/gif'
        : 'image/jpeg';
  const raw = fs.readFileSync(absPath).toString('base64');
  return { type: 'image_url', image_url: { url: `data:${mime};base64,${raw}`, detail } };
}

function parseDecision(raw: string): SectionDecision {
  try {
    const parsed = JSON.parse(raw) as { sectionTitle?: string; confidence?: number; scoreGap?: number };
    const sectionTitle = typeof parsed.sectionTitle === 'string' ? parsed.sectionTitle : 'UNKNOWN';
    const confidence = clamp01(Number(parsed.confidence ?? 0));
    const scoreGap = parsed.scoreGap === undefined ? undefined : clamp01(Number(parsed.scoreGap));
    return { sectionTitle, confidence, scoreGap };
  } catch {
    return { sectionTitle: 'UNKNOWN', confidence: 0 };
  }
}

async function callOpenAIJsonOnly(apiKey: string, body: Record<string, unknown>): Promise<string> {
  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(`openai_http_${response.status}:${err.slice(0, 180)}`);
  }
  const payload = (await response.json()) as OpenAIResponse;
  return payload.choices?.[0]?.message?.content ?? '';
}

export function createSectionVisionMatcher(options: VisionMatcherOptions = {}): SectionMatcher {
  return async (imageSource, sections) => {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey || sections.length === 0) {
      return { sectionTitle: 'UNKNOWN', confidence: 0 };
    }
    const model = options.model ?? resolveVisionModel('gpt-5.2');
    const detail = options.detail ?? (process.env.VISION_DETAIL as 'low' | 'high' | 'auto') ?? 'low';
    const sectionPayload = sections.map((section) => ({
      title: section.title,
      summary: (section.paragraphs[0] ?? '').slice(0, 300),
    }));
    const prompt = [
      '이미지 상세 묘사는 금지.',
      '입력된 섹션 제목 중 가장 관련 있는 sectionTitle 1개만 선택.',
      '불확실하면 UNKNOWN.',
      '반드시 JSON만 반환.',
      '형식: {"sectionTitle":"주차정보"|"UNKNOWN","confidence":0.0,"scoreGap":0.0}',
      'scoreGap은 1위 후보와 2위 후보 점수 차(0~1)이며, 모르면 0으로 둔다.',
    ].join('\n');
    try {
      const content = await callOpenAIJsonOnly(apiKey, {
        model,
        temperature: 0,
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: prompt },
          {
            role: 'user',
            content: [
              { type: 'text', text: JSON.stringify({ sections: sectionPayload }) },
              imageToInputPart(imageSource, detail),
            ],
          },
        ],
      });
      return parseDecision(content);
    } catch {
      return { sectionTitle: 'UNKNOWN', confidence: 0 };
    }
  };
}

function shouldEscalateDecision(
  decision: SectionDecision,
  threshold: number,
  minScoreGap: number,
): boolean {
  if (decision.sectionTitle === 'UNKNOWN') return true;
  if (decision.confidence < threshold) return true;
  if (typeof decision.scoreGap === 'number' && decision.scoreGap < minScoreGap) return true;
  return false;
}

function fallbackPlacement(
  imageIndex: number,
  sections: TopicSection[],
  cursor: { section: number },
): ImagePlacement {
  if (sections.length === 0) {
    return {
      imageIndex,
      sectionIndex: 0,
      paragraphIndex: 0,
      confidence: 0,
      mode: 'fallback',
    };
  }
  const sectionIndex = cursor.section % sections.length;
  cursor.section += 1;
  return {
    imageIndex,
    sectionIndex,
    paragraphIndex: 0,
    confidence: 0,
    mode: 'fallback',
  };
}

export async function placeImagesBySection(
  sections: TopicSection[],
  images: string[],
  options: {
    matcher?: SectionMatcher;
    escalationMatcher?: SectionMatcher;
    threshold?: number;
    minScoreGap?: number;
  } = {},
): Promise<ImagePlacement[]> {
  const matcher = options.matcher ?? createSectionVisionMatcher();
  const escalationMatcher = options.escalationMatcher ?? createSectionVisionMatcher({
    model: process.env.OPENAI_VISION_MODEL_ESCALATED ?? process.env.VISION_MODEL_ESCALATED ?? resolveVisionModel('gpt-5.2'),
    detail: (process.env.VISION_DETAIL_ESCALATED as 'low' | 'high' | 'auto') ?? 'high',
  });
  const threshold = options.threshold ?? Number(process.env.MATCH_THRESHOLD ?? '0.55');
  const minScoreGap = options.minScoreGap ?? Number(process.env.MATCH_SCORE_GAP_THRESHOLD ?? '0.12');
  const escalationEnabled = (process.env.VISION_ESCALATION_ENABLED ?? 'true').toLowerCase() !== 'false';
  const cursor = { section: 0 };
  const placements: ImagePlacement[] = [];
  const visionModel = resolveVisionModel('gpt-5.2');
  log.info(`[image-place] visionModel=${visionModel}`);

  const analyzedResults = await Promise.all(images.map(async (imageSource, idx) => {
    const imageIndex = idx + 1;
    try {
      let decision = await matcher(imageSource, sections);
      let escalated = false;
      if (escalationEnabled && shouldEscalateDecision(decision, threshold, minScoreGap)) {
        decision = await escalationMatcher(imageSource, sections);
        escalated = true;
      }
      return { imageIndex, decision, escalated, reasonCode: undefined as string | undefined };
    } catch {
      return {
        imageIndex,
        decision: { sectionTitle: 'UNKNOWN' as const, confidence: 0 },
        escalated: false,
        reasonCode: 'VISION_ANALYSIS_FAILED',
      };
    }
  }));
  const analysisMap = new Map<number, { decision: SectionDecision; escalated: boolean; reasonCode?: string }>();
  for (const analyzed of analyzedResults) {
    analysisMap.set(analyzed.imageIndex, {
      decision: analyzed.decision,
      escalated: analyzed.escalated,
      reasonCode: analyzed.reasonCode,
    });
  }

  for (let i = 0; i < images.length; i++) {
    const imageIndex = i + 1;
    const analyzed = analysisMap.get(imageIndex);
    if (!analyzed) {
      const fallback = fallbackPlacement(imageIndex, sections, cursor);
      placements.push(fallback);
      log.warn(`[image-place] reason_code=VISION_ANALYSIS_FAILED image_index=${imageIndex} mode=fallback`);
      continue;
    }

    const decision = analyzed.decision;
    const sectionIndex = sections.findIndex((s) => s.title === decision.sectionTitle);
    const isVision = sectionIndex >= 0 && decision.sectionTitle !== 'UNKNOWN' && decision.confidence >= threshold;
    if (isVision) {
      placements.push({
        imageIndex,
        sectionIndex,
        paragraphIndex: 0,
        confidence: decision.confidence,
        mode: 'vision',
      });
    } else {
      placements.push(fallbackPlacement(imageIndex, sections, cursor));
    }
    const chosen = placements[placements.length - 1];
    const reasonSuffix = analyzed.reasonCode ? ` reason_code=${analyzed.reasonCode}` : '';
    log.info(
      `[image-place] image_index=${imageIndex} section_index=${chosen.sectionIndex} confidence=${(chosen.confidence ?? 0).toFixed(2)} mode=${chosen.mode} escalated=${analyzed.escalated}${reasonSuffix}`,
    );
  }

  return placements;
}
