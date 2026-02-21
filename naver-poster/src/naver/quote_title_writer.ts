import { sanitizeQuoteTitle } from '../utils/quote_title_sanitizer';
import { QuoteBlockCreateError } from './quote_block_creator';

export interface QuoteAudit {
  emptyQuotes: number;
  quote1Count: number;
  quote2Count: number;
  latestTitleInQuote: boolean;
  titleOutsideQuote: boolean;
}

export interface QuoteTitleAdapter {
  createQuote2Block: (title: string) => Promise<boolean>;
  writeTitleIntoLatestQuote?: (title: string) => Promise<boolean>;
  inspect: (title: string) => Promise<QuoteAudit>;
  cleanupEmptyQuotes: () => Promise<number>;
  escapeQuoteBlock?: () => Promise<boolean>;
  isCursorInsideQuote?: () => Promise<boolean>;
}

export interface QuoteTitleWriteResult {
  success: boolean;
  reason?: string;
  audit?: QuoteAudit;
}

export async function writeSectionTitleAsQuote2(
  adapter: QuoteTitleAdapter,
  rawTitle: string,
): Promise<QuoteTitleWriteResult> {
  const title = sanitizeQuoteTitle(rawTitle, '방문후기');
  if (!title) {
    return { success: false, reason: 'empty_title' };
  }

  const created = await adapter.createQuote2Block(title);
  if (!created) {
    throw new QuoteBlockCreateError('quote2_block_create_failed', 1);
  }

  let audit = await adapter.inspect(title);
  if (audit.emptyQuotes > 0) {
    await adapter.cleanupEmptyQuotes();
    audit = await adapter.inspect(title);
  }

  if (!audit.latestTitleInQuote) {
    return { success: false, reason: 'title_not_in_quote_block', audit };
  }
  if (audit.titleOutsideQuote) {
    return { success: false, reason: 'title_leaked_outside_quote', audit };
  }
  if (audit.emptyQuotes > 0) {
    return { success: false, reason: 'empty_quote_remaining', audit };
  }
  if (audit.quote1Count > 0) {
    return { success: false, reason: 'quote1_detected', audit };
  }
  if (audit.quote2Count < 1) {
    return { success: false, reason: 'quote2_not_detected', audit };
  }

  if (adapter.escapeQuoteBlock) {
    const escaped = await adapter.escapeQuoteBlock();
    if (!escaped) {
      return { success: false, reason: 'quote_escape_failed', audit };
    }
  }

  if (adapter.isCursorInsideQuote) {
    const inside = await adapter.isCursorInsideQuote();
    if (inside) {
      return { success: false, reason: 'quote_escape_incomplete', audit };
    }
  }

  return { success: true, audit };
}
