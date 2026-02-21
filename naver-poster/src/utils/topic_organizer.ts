import { enforceOutlineAndConclusionRules } from './outline_validator';
import { sanitizeQuoteTitle } from './quote_title_sanitizer';

export interface TopicSection {
  title: string;
  paragraphs: string[];
}

export interface TopicOrganizeResult {
  sections: TopicSection[];
  orderedText: string;
  debugInfo: {
    paragraphCount: number;
    sectionCount: number;
    appliedDefaultOrder: boolean;
    outlineFixNote: string;
    movedConclusionParagraphs: number;
  };
}

const DEFAULT_SECTION_ORDER = [
  '서론',
  '방문후기',
  '위치/교통',
  '주차정보',
  '체크인/시설',
  '객실/뷰',
  '조식/편의',
  '비용정보',
  '꿀팁',
  '총평',
];

const SECTION_KEYWORDS: Array<{ title: string; keywords: RegExp[] }> = [
  { title: '주차정보', keywords: [/주차|parking|주차장|공영|발렛/i] },
  { title: '비용정보', keywords: [/비용|가격|요금|원|만원|결제|가성비|추가금/i] },
  { title: '위치/교통', keywords: [/위치|교통|가는\s*법|거리|도보|지하철|버스|택시|공항/i] },
  { title: '체크인/시설', keywords: [/체크인|체크아웃|프론트|시설|부대시설|수영장|사우나|헬스장/i] },
  { title: '객실/뷰', keywords: [/객실|룸|침대|전망|뷰|야경|테라스/i] },
  { title: '조식/편의', keywords: [/조식|라운지|편의|어메니티|와이파이|wifi|서비스/i] },
  { title: '꿀팁', keywords: [/팁|추천|주의|체크포인트|노하우/i] },
  { title: '총평', keywords: [/총평|재방문|추천|아쉬움|결론|마무리/i] },
];

function normalizeParagraph(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

function classifyParagraph(paragraph: string): string {
  for (const entry of SECTION_KEYWORDS) {
    if (entry.keywords.some((k) => k.test(paragraph))) return entry.title;
  }
  return '방문후기';
}

function splitParagraphs(draftText: string): string[] {
  return normalizeParagraph(draftText)
    .split(/\n{2,}/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export function organizeTopics(
  draftText: string,
  options: {
    useDefaultOrder?: boolean;
  } = {},
): TopicOrganizeResult {
  const useDefaultOrder = options.useDefaultOrder ?? true;
  const paragraphs = splitParagraphs(draftText);
  const sectionMap = new Map<string, string[]>();

  if (paragraphs.length === 0) {
    return {
      sections: [],
      orderedText: '',
      debugInfo: {
        paragraphCount: 0,
        sectionCount: 0,
        appliedDefaultOrder: useDefaultOrder,
        outlineFixNote: 'empty-input',
        movedConclusionParagraphs: 0,
      },
    };
  }

  const introParagraphCount = Math.min(2, paragraphs.length);
  const introParagraphs = paragraphs.slice(0, introParagraphCount);
  const bodyParagraphs = paragraphs.slice(introParagraphCount);
  if (introParagraphs.length > 0) {
    sectionMap.set('서론', introParagraphs);
  }

  for (const paragraph of bodyParagraphs) {
    const title = classifyParagraph(paragraph);
    const list = sectionMap.get(title) ?? [];
    list.push(paragraph);
    sectionMap.set(title, list);
  }

  const sections: TopicSection[] = [];
  if (useDefaultOrder) {
    for (const sectionTitle of DEFAULT_SECTION_ORDER) {
      const paras = sectionMap.get(sectionTitle);
      if (paras && paras.length > 0) {
        const normalizedTitle = sectionTitle === '총평'
          ? '총평'
          : sanitizeQuoteTitle(sectionTitle, '방문후기');
        sections.push({ title: normalizedTitle, paragraphs: paras });
      }
    }
    for (const [title, paras] of sectionMap.entries()) {
      if (!DEFAULT_SECTION_ORDER.includes(title)) {
        sections.push({ title: sanitizeQuoteTitle(title, '방문후기'), paragraphs: paras });
      }
    }
  } else {
    for (const [title, paras] of sectionMap.entries()) {
      sections.push({ title: sanitizeQuoteTitle(title, '방문후기'), paragraphs: paras });
    }
  }

  const outline = enforceOutlineAndConclusionRules(sections);
  const orderedText = outline.sections
    .map((section) => [`"${section.title}"`, ...section.paragraphs].join('\n\n'))
    .join('\n\n');

  return {
    sections: outline.sections,
    orderedText,
    debugInfo: {
      paragraphCount: paragraphs.length,
      sectionCount: outline.sections.length,
      appliedDefaultOrder: useDefaultOrder,
      outlineFixNote: outline.note,
      movedConclusionParagraphs: outline.movedParagraphs,
    },
  };
}
