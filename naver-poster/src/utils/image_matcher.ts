import * as fs from 'fs';
import * as path from 'path';
import * as log from './logger';
import type { PostBlock } from './parser';

export type BlockType = 'heading' | 'list' | 'paragraph';

export interface TextBlockUnit {
  id: string;
  rawText: string;
  summaryText: string;
  type: BlockType;
  startIdx: number;
  endIdx: number;
}

export interface ImageMatchDecision {
  blockId: string | 'UNKNOWN';
  confidence: number;
}

type MatcherConfig = {
  visionModel: string;
  visionDetail: 'low' | 'high' | 'auto';
  matchThreshold: number;
  maxSummaryChars: number;
  shortlistTriggerCount: number;
  shortlistCount: number;
};

type OpenAIResponse = {
  choices?: Array<{
    message?: {
      content?: string;
    };
  }>;
};

export type ImageMatcher = (
  imageSource: string,
  blocks: TextBlockUnit[],
) => Promise<ImageMatchDecision>;

export type PlacementDecision = {
  imageIndex: number;
  imageSource: string;
  chosenBlockId: string | null;
  confidence: number;
  strategy: 'semantic' | 'fallback';
};

const DEFAULT_CONFIG: MatcherConfig = {
  visionModel: resolveVisionModelForImageMatcher(),
  visionDetail: (process.env.VISION_DETAIL as 'low' | 'high' | 'auto') ?? 'low',
  matchThreshold: Number(process.env.MATCH_THRESHOLD ?? '0.55'),
  maxSummaryChars: 800,
  shortlistTriggerCount: 60,
  shortlistCount: 20,
};

export function resolveVisionModelForImageMatcher(): string {
  return process.env.OPENAI_VISION_MODEL ?? process.env.VISION_MODEL ?? 'gpt-5.2';
}

const IMAGE_MARKER_PATTERN = /(\[사진\d+\]|\(사진\d+\)|\(사진\)|!\[[^\]]*?\]\([^)]+\)|<!--\s*IMG:.*?-->)/gi;

function detectBlockType(rawText: string): BlockType {
  const firstLine = rawText.trim().split('\n')[0] ?? '';
  if (/^#{1,6}\s+/.test(firstLine)) return 'heading';
  if (/^([-*+]\s+|\d+\.\s+)/.test(firstLine)) return 'list';
  return 'paragraph';
}

function toSummaryText(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}...`;
}

function sanitizeTextForMatching(blogText: string): string {
  return blogText.replace(/\r\n/g, '\n').replace(IMAGE_MARKER_PATTERN, '\n').trim();
}

function toBlockId(index: number): string {
  return `B${String(index + 1).padStart(3, '0')}`;
}

export function splitIntoBlocks(blogText: string, maxSummaryChars: number = DEFAULT_CONFIG.maxSummaryChars): TextBlockUnit[] {
  const sanitized = sanitizeTextForMatching(blogText);
  if (!sanitized) return [];

  const chunks = sanitized.split(/\n{2,}/).map((x) => x.trim()).filter(Boolean);
  const blocks: TextBlockUnit[] = [];
  let searchOffset = 0;

  for (let i = 0; i < chunks.length; i++) {
    const rawText = chunks[i];
    const id = toBlockId(i);
    const startIdx = sanitized.indexOf(rawText, searchOffset);
    const safeStart = startIdx >= 0 ? startIdx : searchOffset;
    const endIdx = safeStart + rawText.length;
    searchOffset = endIdx;

    blocks.push({
      id,
      rawText,
      summaryText: toSummaryText(rawText, maxSummaryChars),
      type: detectBlockType(rawText),
      startIdx: safeStart,
      endIdx,
    });
  }

  return blocks;
}

function clampConfidence(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function parseJsonDecision(raw: string): ImageMatchDecision {
  try {
    const parsed = JSON.parse(raw) as { blockId?: string; confidence?: number };
    const blockId = typeof parsed.blockId === 'string' ? parsed.blockId : 'UNKNOWN';
    const confidence = clampConfidence(Number(parsed.confidence ?? 0));
    return { blockId, confidence };
  } catch {
    return { blockId: 'UNKNOWN', confidence: 0 };
  }
}

function parseShortlist(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw) as { candidateBlockIds?: string[] };
    if (!Array.isArray(parsed.candidateBlockIds)) return [];
    return parsed.candidateBlockIds.filter((x) => typeof x === 'string');
  } catch {
    return [];
  }
}

async function callOpenAIJsonOnly(
  apiKey: string,
  body: Record<string, unknown>,
): Promise<string> {
  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const brief = await response.text();
    throw new Error(`openai_http_${response.status}:${brief.slice(0, 180)}`);
  }

  const payload = (await response.json()) as OpenAIResponse;
  return payload.choices?.[0]?.message?.content ?? '';
}

function imageToInputPart(imageSource: string, detail: 'low' | 'high' | 'auto'): Record<string, unknown> {
  if (/^https?:\/\//i.test(imageSource)) {
    return { type: 'image_url', image_url: { url: imageSource, detail } };
  }

  const absPath = path.resolve(imageSource);
  const binary = fs.readFileSync(absPath);
  const ext = path.extname(absPath).toLowerCase();
  const mime = ext === '.png'
    ? 'image/png'
    : ext === '.webp'
      ? 'image/webp'
      : ext === '.gif'
        ? 'image/gif'
        : 'image/jpeg';
  const base64 = binary.toString('base64');
  return { type: 'image_url', image_url: { url: `data:${mime};base64,${base64}`, detail } };
}

async function shortlistBlockIds(
  apiKey: string,
  config: MatcherConfig,
  imageSource: string,
  blocks: TextBlockUnit[],
): Promise<string[]> {
  const blockPayload = blocks.map((b) => ({
    id: b.id,
    type: b.type,
    text: b.summaryText,
  }));
  const prompt = [
    '다음 블로그 블록 목록에서, 첨부된 이미지 파일명/URL과 주제상 관련 가능성이 높은 blockId를 최대 20개 고르세요.',
    '이미지 상세 묘사/설명은 금지합니다.',
    '반드시 JSON만 반환하세요.',
    '형식: {"candidateBlockIds":["B001","B002"]}',
  ].join('\n');
  const content = await callOpenAIJsonOnly(apiKey, {
    model: config.visionModel,
    temperature: 0,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: prompt },
      {
        role: 'user',
        content: JSON.stringify({
          imageHint: path.basename(imageSource),
          blocks: blockPayload,
        }),
      },
    ],
  });
  const parsed = parseShortlist(content);
  if (!parsed.length) return blocks.slice(0, config.shortlistCount).map((b) => b.id);
  return parsed.slice(0, config.shortlistCount);
}

export function createOpenAIImageMatcher(configOverrides: Partial<MatcherConfig> = {}): ImageMatcher {
  const config: MatcherConfig = { ...DEFAULT_CONFIG, ...configOverrides };
  return async (imageSource: string, blocks: TextBlockUnit[]): Promise<ImageMatchDecision> => {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) return { blockId: 'UNKNOWN', confidence: 0 };
    if (!blocks.length) return { blockId: 'UNKNOWN', confidence: 0 };
    log.info(`[image-match] visionModel=${config.visionModel}`);

    try {
      let candidateBlocks = blocks;
      if (blocks.length > config.shortlistTriggerCount) {
        const shortlistIds = await shortlistBlockIds(apiKey, config, imageSource, blocks);
        const shortlistSet = new Set(shortlistIds);
        const narrowed = blocks.filter((b) => shortlistSet.has(b.id));
        candidateBlocks = narrowed.length > 0 ? narrowed : blocks.slice(0, config.shortlistCount);
      }

      const prompt = [
        '이미지 상세 설명은 금지.',
        '주어진 블로그 텍스트 블록 중 가장 관련 높은 blockId 하나만 선택.',
        '불확실하면 UNKNOWN.',
        '반드시 JSON만 반환.',
        '형식: {"blockId":"B012"|"UNKNOWN","confidence":0.0}',
      ].join('\n');
      const content = await callOpenAIJsonOnly(apiKey, {
        model: config.visionModel,
        temperature: 0,
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: prompt },
          {
            role: 'user',
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  blocks: candidateBlocks.map((b) => ({
                    id: b.id,
                    type: b.type,
                    text: b.summaryText,
                  })),
                }),
              },
              imageToInputPart(imageSource, config.visionDetail),
            ],
          },
        ],
      });
      const parsed = parseJsonDecision(content);
      return parsed;
    } catch {
      return { blockId: 'UNKNOWN', confidence: 0 };
    }
  };
}

function findFallbackBlockId(
  blocks: TextBlockUnit[],
  usedBlockIds: Set<string>,
  cursorRef: { index: number },
): string | null {
  if (!blocks.length) return null;
  for (let i = 0; i < blocks.length; i++) {
    const idx = (cursorRef.index + i) % blocks.length;
    const candidateId = blocks[idx].id;
    if (!usedBlockIds.has(candidateId)) {
      cursorRef.index = idx + 1;
      return candidateId;
    }
  }
  return null;
}

function composePostBlocks(
  blocks: TextBlockUnit[],
  placements: PlacementDecision[],
): PostBlock[] {
  const imagesByBlock = new Map<string, number[]>();
  const tailImages: number[] = [];

  for (const decision of placements) {
    if (!decision.chosenBlockId) {
      tailImages.push(decision.imageIndex);
      continue;
    }
    const list = imagesByBlock.get(decision.chosenBlockId) ?? [];
    list.push(decision.imageIndex);
    imagesByBlock.set(decision.chosenBlockId, list);
  }

  const result: PostBlock[] = [];
  for (const block of blocks) {
    const imageIndexes = imagesByBlock.get(block.id) ?? [];
    for (const imageIndex of imageIndexes) {
      result.push({ type: 'image', index: imageIndex, marker: 'SEMANTIC_MATCH' });
    }
    result.push({ type: 'text', content: block.rawText });
  }

  for (const imageIndex of tailImages) {
    result.push({ type: 'image', index: imageIndex, marker: 'FALLBACK_TAIL' });
  }
  return result;
}

export function renderMarkdownWithImages(
  blocks: TextBlockUnit[],
  placements: PlacementDecision[],
  images: string[],
): string {
  const imagesByBlock = new Map<string, number[]>();
  const tailImages: number[] = [];

  for (const decision of placements) {
    if (!decision.chosenBlockId) {
      tailImages.push(decision.imageIndex);
      continue;
    }
    const list = imagesByBlock.get(decision.chosenBlockId) ?? [];
    list.push(decision.imageIndex);
    imagesByBlock.set(decision.chosenBlockId, list);
  }

  const lines: string[] = [];
  for (const block of blocks) {
    const imageIndexes = imagesByBlock.get(block.id) ?? [];
    for (const imageIndex of imageIndexes) {
      const imageSrc = images[imageIndex - 1] ?? '';
      const alt = path.basename(imageSrc || `image-${String(imageIndex).padStart(2, '0')}`);
      lines.push(`![${alt}](${imageSrc})`);
      lines.push('');
    }
    lines.push(block.rawText);
    lines.push('');
  }

  for (const imageIndex of tailImages) {
    const imageSrc = images[imageIndex - 1] ?? '';
    const alt = path.basename(imageSrc || `image-${String(imageIndex).padStart(2, '0')}`);
    lines.push(`![${alt}](${imageSrc})`);
    lines.push('');
  }
  return lines.join('\n').trim();
}

export async function buildSemanticImageBlockSequence(
  blogText: string,
  images: string[],
  options: {
    matcher?: ImageMatcher;
    matchThreshold?: number;
    maxSummaryChars?: number;
  } = {},
): Promise<{
  blocks: PostBlock[];
  placements: PlacementDecision[];
  markdown: string;
}> {
  const textBlocks = splitIntoBlocks(blogText, options.maxSummaryChars ?? DEFAULT_CONFIG.maxSummaryChars);
  const matcher = options.matcher ?? createOpenAIImageMatcher();
  const threshold = options.matchThreshold ?? DEFAULT_CONFIG.matchThreshold;
  const placements: PlacementDecision[] = [];
  const usedByFallback = new Set<string>();
  const fallbackCursor = { index: 0 };

  for (let i = 0; i < images.length; i++) {
    const imageSource = images[i];
    const imageIndex = i + 1;
    const result = await matcher(imageSource, textBlocks);

    const blockExists = textBlocks.some((b) => b.id === result.blockId);
    const semanticOk = blockExists && result.blockId !== 'UNKNOWN' && result.confidence >= threshold;

    let chosenBlockId: string | null = semanticOk ? result.blockId : null;
    let strategy: 'semantic' | 'fallback' = semanticOk ? 'semantic' : 'fallback';

    if (!chosenBlockId) {
      const fallbackId = findFallbackBlockId(textBlocks, usedByFallback, fallbackCursor);
      chosenBlockId = fallbackId;
      strategy = 'fallback';
      if (fallbackId) usedByFallback.add(fallbackId);
    }

    placements.push({
      imageIndex,
      imageSource,
      chosenBlockId,
      confidence: result.confidence,
      strategy,
    });

    log.info(
      `[image-match] image_index=${imageIndex} block_id=${chosenBlockId ?? 'END'} confidence=${result.confidence.toFixed(2)} strategy=${strategy}`,
    );
  }

  const postBlocks = composePostBlocks(textBlocks, placements);
  return {
    blocks: postBlocks,
    placements,
    markdown: renderMarkdownWithImages(textBlocks, placements, images),
  };
}
