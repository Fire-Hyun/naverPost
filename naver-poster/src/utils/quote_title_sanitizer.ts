const DEFAULT_FALLBACK_TITLE = '방문후기';

function normalizeWhitespace(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\t/g, ' ').trim();
}

export function sanitizeQuoteTitle(rawTitle: string, fallbackTitle = DEFAULT_FALLBACK_TITLE): string {
  const normalized = normalizeWhitespace(rawTitle).replace(/^"+|"+$/g, '');
  const firstLine = normalized.split('\n').map((line) => line.trim()).find(Boolean) ?? '';
  const compact = firstLine.replace(/[“”"'`]/g, '').trim();
  const cleaned = compact.replace(/[.!?]+$/g, '').trim();
  const tooLong = cleaned.length > 20;
  const looksLikeSentence = /[.!?]/.test(cleaned);
  if (!cleaned || cleaned.length < 2 || tooLong || looksLikeSentence) {
    return fallbackTitle;
  }
  return cleaned;
}

