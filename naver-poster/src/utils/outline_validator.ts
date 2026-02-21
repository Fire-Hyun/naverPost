import type { TopicSection } from './topic_organizer';

const ENDING_PATTERNS = [
  /다음에\s*만나요/i,
  /총평/i,
  /마무리/i,
  /결론/i,
  /정리/i,
  /끝\b/i,
  /감사합니다/i,
];

function hasEndingCue(text: string): boolean {
  return ENDING_PATTERNS.some((pattern) => pattern.test(text));
}

function stripEndingPhrase(text: string): string {
  return text
    .replace(/다음에\s*만나요!?/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

export interface OutlineFixResult {
  sections: TopicSection[];
  movedParagraphs: number;
  applied: boolean;
  note: string;
}

export function enforceOutlineAndConclusionRules(
  inputSections: TopicSection[],
  endingPhrase = '다음에 만나요!',
): OutlineFixResult {
  const sectionCopies: TopicSection[] = inputSections.map((section) => ({
    title: section.title,
    paragraphs: [...section.paragraphs],
  }));
  const intro: TopicSection = { title: '서론', paragraphs: [] };
  const conclusion: TopicSection = { title: '총평', paragraphs: [] };
  const body: TopicSection[] = [];
  let movedParagraphs = 0;
  let endingCueFound = false;

  for (const section of sectionCopies) {
    if (section.title === '서론') {
      intro.paragraphs.push(...section.paragraphs.map((p) => p.trim()).filter(Boolean));
      continue;
    }
    const isConclusionSection = section.title === '총평' || section.title === '마무리';
    if (isConclusionSection) {
      for (const paragraph of section.paragraphs) {
        if (!paragraph.trim()) continue;
        endingCueFound = endingCueFound || hasEndingCue(paragraph);
        const stripped = stripEndingPhrase(paragraph);
        if (stripped) conclusion.paragraphs.push(stripped);
      }
      continue;
    }

    const kept: string[] = [];
    for (const paragraph of section.paragraphs) {
      if (!paragraph.trim()) continue;
      if (hasEndingCue(paragraph)) {
        movedParagraphs += 1;
        endingCueFound = true;
        const stripped = stripEndingPhrase(paragraph);
        if (stripped) conclusion.paragraphs.push(stripped);
        continue;
      }
      kept.push(paragraph);
    }
    if (kept.length > 0) {
      body.push({ title: section.title, paragraphs: kept });
    }
  }

  if (intro.paragraphs.length === 0 && body.length > 0) {
    const firstBody = body[0];
    const take = Math.min(2, firstBody.paragraphs.length);
    intro.paragraphs.push(...firstBody.paragraphs.splice(0, take));
    if (firstBody.paragraphs.length === 0) {
      body.shift();
    }
  }

  const cleanedConclusion: string[] = [];
  for (const paragraph of conclusion.paragraphs) {
    const stripped = stripEndingPhrase(paragraph);
    if (stripped) cleanedConclusion.push(stripped);
  }
  if (cleanedConclusion.length === 0) {
    cleanedConclusion.push('이번 방문 경험을 기준으로 다시 방문할 의사가 있습니다.');
  }
  cleanedConclusion.push(endingPhrase);
  conclusion.paragraphs = cleanedConclusion;

  const ordered: TopicSection[] = [];
  if (intro.paragraphs.length > 0) ordered.push(intro);
  ordered.push(...body);
  ordered.push(conclusion);

  return {
    sections: ordered,
    movedParagraphs,
    applied: movedParagraphs > 0 || endingCueFound || ordered.length !== inputSections.length,
    note:
      movedParagraphs > 0
        ? `early-conclusion paragraphs moved=${movedParagraphs}`
        : (endingCueFound ? 'ending phrase normalized to final conclusion' : 'no-outline-fix'),
  };
}
