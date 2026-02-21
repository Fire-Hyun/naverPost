import type { TopicSection } from './topic_organizer';

export type SectionInterleaveItem =
  | { type: 'titleQuote'; title: string }
  | { type: 'text'; content: string; chunkId: string }
  | { type: 'image'; imageIndex: number };

export type SectionTextChunk = {
  chunkId: string;
  content: string;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function splitSentences(text: string): string[] {
  const normalized = text.replace(/\r\n/g, '\n').trim();
  if (!normalized) return [];
  return normalized
    .split(/(?<=[.!?])\s+|(?<=[다요])\s+|\n+/g)
    .map((s) => s.trim())
    .filter(Boolean);
}

function buildSentenceChunks(
  sentences: string[],
  desiredChunks: number,
  minSize: number,
  maxSize: number,
): string[] {
  if (sentences.length === 0) return [];
  const boundedDesired = clamp(desiredChunks, 1, Math.max(1, sentences.length));
  const base = clamp(Math.ceil(sentences.length / boundedDesired), minSize, maxSize);
  const chunks: string[] = [];
  let cursor = 0;
  while (cursor < sentences.length) {
    const remain = sentences.length - cursor;
    const current = clamp(base, minSize, Math.min(maxSize, remain));
    chunks.push(sentences.slice(cursor, cursor + current).join(' '));
    cursor += current;
  }
  return chunks;
}

export function splitSectionIntoTextChunks(
  section: TopicSection,
  options: {
    sentencesPerChunkMin?: number;
    sentencesPerChunkMax?: number;
    desiredTextChunks?: number;
    nextChunkNumberRef?: { value: number };
  } = {},
): SectionTextChunk[] {
  const minChunk = options.sentencesPerChunkMin ?? 1;
  const maxChunk = options.sentencesPerChunkMax ?? 5;
  const sectionText = section.paragraphs.join('\n');
  const sentences = splitSentences(sectionText);
  const desiredTextChunks = options.desiredTextChunks ?? 1;
  const chunks = buildSentenceChunks(sentences, desiredTextChunks, minChunk, maxChunk);
  const texts = chunks.length > 0 ? chunks : [sectionText.trim() || '메모'];
  const ref = options.nextChunkNumberRef ?? { value: 1 };

  return texts.map((content) => {
    const chunkId = `C${String(ref.value).padStart(3, '0')}`;
    ref.value += 1;
    return { chunkId, content };
  });
}

export function interleaveSection(
  section: TopicSection,
  imageIndexes: number[],
  options: {
    sentencesPerChunkMin?: number;
    sentencesPerChunkMax?: number;
    avoidConsecutiveImages?: boolean;
  } = {},
): SectionInterleaveItem[] {
  const avoidConsecutive = options.avoidConsecutiveImages ?? true;
  const textChunks = splitSectionIntoTextChunks(section, {
    sentencesPerChunkMin: options.sentencesPerChunkMin,
    sentencesPerChunkMax: options.sentencesPerChunkMax,
    desiredTextChunks: Math.max(imageIndexes.length + 1, 1),
  });
  const items: SectionInterleaveItem[] = [{ type: 'titleQuote', title: section.title }];
  let imgPtr = 0;

  for (let i = 0; i < textChunks.length; i++) {
    if (imgPtr < imageIndexes.length) {
      items.push({ type: 'image', imageIndex: imageIndexes[imgPtr++] });
    }
    items.push({ type: 'text', content: textChunks[i].content, chunkId: textChunks[i].chunkId });
  }

  while (imgPtr < imageIndexes.length) {
    if (avoidConsecutive) {
      const chunkId = `C${String(textChunks.length + imgPtr + 1).padStart(3, '0')}`;
      items.push({ type: 'text', content: '사진 참고', chunkId });
    }
    items.push({ type: 'image', imageIndex: imageIndexes[imgPtr++] });
  }

  return items;
}
