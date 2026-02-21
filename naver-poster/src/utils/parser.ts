import * as fs from 'fs';
import * as path from 'path';
import * as log from './logger';

export interface ParsedPost {
  title: string;
  body: string;
  hashtags: string[];
  /** 본문 내 이미지 플레이스홀더 위치 (줄 인덱스 배열) */
  imagePlaceholders: number[];
  /** body를 줄 단위로 분리한 배열 (플레이스홀더 포함) */
  bodyLines: string[];
  /** 업로드 순서 제어를 위한 본문 블록 배열 */
  blocks: PostBlock[];
  frontmatter: Record<string, string>;
}

export type PostBlock = TextBlock | ImageBlock | SectionTitleBlock;

export interface TextBlock {
  type: 'text';
  content: string;
}

export interface SectionTitleBlock {
  type: 'section_title';
  content: string;
}

export interface ImageBlock {
  type: 'image';
  /** 1-based index, images[] 순번과 매핑 */
  index: number;
  marker?: string;
}

export interface PostMetadata {
  category?: string;
  visitDate?: string;
  rating?: number;
  companion?: string;
  personalReview?: string;
  hashtags?: string[];
  images?: string[];
  placeName?: string;
  storeName?: string;
  regionHint?: string;
  [key: string]: unknown;
}

export interface PostDirectory {
  dirPath: string;
  blogResultPath: string;
  imagesDir: string;
  metadataPath: string;
  imagePaths: string[];
  metadata: PostMetadata | null;
  parsed: ParsedPost;
}

// ────────────────────────────────────────────
// frontmatter (YAML) 파싱
// ────────────────────────────────────────────
function parseFrontmatter(raw: string): { frontmatter: Record<string, string>; content: string } {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!match) return { frontmatter: {}, content: raw };

  const fm: Record<string, string> = {};
  for (const line of match[1].split('\n')) {
    const idx = line.indexOf(':');
    if (idx > 0) {
      fm[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    }
  }
  return { frontmatter: fm, content: match[2] };
}

// ────────────────────────────────────────────
// 이미지 플레이스홀더 패턴
// ────────────────────────────────────────────
const PLACEHOLDER_PATTERNS = [
  /^\(사진\)$/,                      // (사진)
  /^\(사진\d+\)$/,                  // (사진1)
  /^\[사진\d+\]$/,                  // [사진1]
  /^!\[.*?\]\(.*?\)$/,              // ![alt](path)
  /^<!--\s*IMG:.*?-->$/,            // <!--IMG:xxx.jpg-->
];

function isImagePlaceholder(line: string): boolean {
  const trimmed = line.trim();
  return PLACEHOLDER_PATTERNS.some((p) => p.test(trimmed));
}

// ────────────────────────────────────────────
// 해시태그 추출
// ────────────────────────────────────────────
function extractHashtags(text: string): string[] {
  const matches = text.match(/#[가-힣A-Za-z0-9_]+/g);
  return matches ?? [];
}

function normalizeTextContent(content: string): string {
  return content
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function normalizeTitleLine(line: string): string {
  const trimmed = line.trim();
  const withoutHeading = trimmed.replace(/^#\s+/, '');
  const withoutTitlePrefix = withoutHeading.replace(/^title:\s*/i, '');
  return withoutTitlePrefix.trim();
}

function resolveImageIndexFromToken(token: string): number | null {
  const explicit = token.match(/(?:사진|photo)\s*(\d+)/i);
  if (explicit) {
    return Number(explicit[1]);
  }

  const markdownAlt = token.match(/!\[[^\]]*?(\d+)[^\]]*\]\(.*?\)/i);
  if (markdownAlt) {
    return Number(markdownAlt[1]);
  }

  const htmlComment = token.match(/IMG:[^\d]*(\d+)/i);
  if (htmlComment) {
    return Number(htmlComment[1]);
  }

  return null;
}

function normalizeSectionTitle(line: string): string | null {
  const match = line.trim().match(/^\*\*(.+?)\*\*\s*$/);
  if (!match) return null;
  const title = match[1].trim();
  if (!title) return null;
  if (title.length < 2 || title.length > 20) return null;
  if (/[.!?]/.test(title)) return null;
  return title;
}

function pushTextWithQuote2Sections(content: string, blocks: PostBlock[]): void {
  const normalized = normalizeTextContent(content);
  if (normalized) {
    blocks.push({ type: 'text', content: normalized });
  }
}

function pushTextAndImages(content: string, blocks: PostBlock[], unnamedCounterRef: { value: number }): void {
  const tokenPattern = /(\[사진\d+\]|\(사진\d+\)|\(사진\)|!\[[^\]]*?\]\([^)]+\)|<!--\s*IMG:.*?-->)/gi;
  let lastIndex = 0;
  for (const match of content.matchAll(tokenPattern)) {
    const token = match[0];
    const start = match.index ?? 0;
    const before = content.slice(lastIndex, start);
    pushTextWithQuote2Sections(before, blocks);
    const explicitIndex = resolveImageIndexFromToken(token);
    const imageIndex = explicitIndex && explicitIndex > 0 ? explicitIndex : unnamedCounterRef.value++;
    blocks.push({ type: 'image', index: imageIndex, marker: token });
    lastIndex = start + token.length;
  }
  pushTextWithQuote2Sections(content.slice(lastIndex), blocks);
}

function buildBlocks(rawBody: string): PostBlock[] {
  const blocks: PostBlock[] = [];
  const unnamedCounterRef = { value: 1 };

  // **소제목** 라인을 section_title로 보존하고, 나머지 라인은 기존 텍스트/이미지 토큰 파싱 적용
  const lines = rawBody.split('\n');
  let textBuffer: string[] = [];
  for (const line of lines) {
    const maybeHeading = normalizeSectionTitle(line);
    if (maybeHeading) {
      const buffered = normalizeTextContent(textBuffer.join('\n'));
      if (buffered) {
        pushTextAndImages(buffered, blocks, unnamedCounterRef);
      }
      textBuffer = [];
      blocks.push({ type: 'section_title', content: maybeHeading });
      continue;
    }
    textBuffer.push(line);
  }

  const bufferedTail = normalizeTextContent(textBuffer.join('\n'));
  if (bufferedTail) {
    pushTextAndImages(bufferedTail, blocks, unnamedCounterRef);
  }

  if (blocks.length === 0 && normalizeTextContent(rawBody)) {
    blocks.push({ type: 'text', content: normalizeTextContent(rawBody) });
  }

  return blocks;
}

function extractMarkdownImagePaths(markdown: string): string[] {
  const paths: string[] = [];
  const markdownPattern = /!\[[^\]]*?\]\(([^)]+)\)/g;
  for (const match of markdown.matchAll(markdownPattern)) {
    const rawPath = (match[1] || '').trim().replace(/^["']|["']$/g, '');
    if (!rawPath) continue;
    if (/^(https?:|data:|blob:)/i.test(rawPath)) continue;
    paths.push(rawPath);
  }

  const htmlPattern = /<img[^>]*src=["']([^"']+)["'][^>]*>/gi;
  for (const match of markdown.matchAll(htmlPattern)) {
    const rawPath = (match[1] || '').trim();
    if (!rawPath) continue;
    if (/^(https?:|data:|blob:)/i.test(rawPath)) continue;
    paths.push(rawPath);
  }

  return paths;
}

// ────────────────────────────────────────────
// blog_result.md 파싱
// ────────────────────────────────────────────
export function parseBlogResult(filePath: string, metadata: PostMetadata | null = null): ParsedPost {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const { frontmatter, content } = parseFrontmatter(raw);

  const allLines = content
    .split('\n')
    .filter((line, idx) => !(idx <= 2 && /^\s*<!--\s*RUN_ID:\s*[A-Za-z0-9_\-]+\s*-->\s*$/.test(line.trim())));
  const titleLineIndex = allLines.findIndex((line) => line.trim().length > 0);
  const title = titleLineIndex >= 0 ? normalizeTitleLine(allLines[titleLineIndex]) : '블로그 포스팅';

  // 제목 줄 이후가 본문(원문 순서 유지)
  const bodyLines = titleLineIndex >= 0 ? allLines.slice(titleLineIndex + 1) : [];

  // 마지막 줄 해시태그 분리
  let hashtagLine = '';
  let lastNonEmptyIndex = -1;
  for (let i = bodyLines.length - 1; i >= 0; i--) {
    if (bodyLines[i].trim().length > 0) {
      lastNonEmptyIndex = i;
      break;
    }
  }
  if (lastNonEmptyIndex >= 0) {
    const lastLine = bodyLines[lastNonEmptyIndex].trim();
    if (lastLine.startsWith('#') && extractHashtags(lastLine).length > 0) {
      hashtagLine = bodyLines[lastNonEmptyIndex];
      bodyLines.splice(lastNonEmptyIndex, 1);
    }
  }

  const hashtags = extractHashtags(hashtagLine);
  const body = bodyLines.join('\n').trim();
  const blocks = buildBlocks(body);
  const imagePlaceholders = blocks
    .map((block, idx) => ({ block, idx }))
    .filter((entry) => entry.block.type === 'image')
    .map((entry) => entry.idx);

  return { title, body, hashtags, imagePlaceholders, bodyLines, blocks, frontmatter };
}

// ────────────────────────────────────────────
// metadata.json 로드
// ────────────────────────────────────────────
export function loadMetadata(dirPath: string): PostMetadata | null {
  const metaPath = path.join(dirPath, 'metadata.json');
  if (!fs.existsSync(metaPath)) return null;

  try {
    const raw = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
    const userInput = raw.user_input ?? {};
    return {
      category: userInput.category,
      visitDate: userInput.visit_date,
      rating: userInput.rating,
      companion: userInput.companion,
      personalReview: userInput.personal_review,
      hashtags: userInput.hashtags,
      images: raw.images,
      placeName: userInput.place_name ?? userInput.store_name,
      storeName: userInput.store_name,
      regionHint: userInput.region_hint ?? userInput.region ?? userInput.location_hint,
    };
  } catch (e) {
    log.warn(`metadata.json 파싱 실패: ${e}`);
    return null;
  }
}

// ────────────────────────────────────────────
// 포스팅 디렉토리 로드
// ────────────────────────────────────────────
export function loadPostDirectory(dirPath: string): PostDirectory {
  const absDir = path.resolve(dirPath);

  if (!fs.existsSync(absDir)) {
    throw new Error(`디렉토리가 존재하지 않습니다: ${absDir}`);
  }

  const blogResultPath = path.join(absDir, 'blog_result.md');
  if (!fs.existsSync(blogResultPath)) {
    throw new Error(`blog_result.md가 없습니다: ${blogResultPath}`);
  }

  const imagesDir = path.join(absDir, 'images');
  const metadataPath = path.join(absDir, 'metadata.json');
  const metadata = loadMetadata(absDir);

  // 이미지 파일 목록 (markdown 경로 우선 + images 디렉토리 보강)
  let imagePaths: string[] = [];
  const resolveImageCandidate = (rawPath: string): string => {
    if (path.isAbsolute(rawPath)) return path.resolve(rawPath);
    const fromRoot = path.resolve(absDir, rawPath);
    if (fs.existsSync(fromRoot)) return fromRoot;
    const fromImagesDir = path.resolve(imagesDir, path.basename(rawPath));
    if (fs.existsSync(fromImagesDir)) return fromImagesDir;
    return fromRoot;
  };

  const markdownRaw = fs.readFileSync(blogResultPath, 'utf-8');
  const markdownImagePaths = extractMarkdownImagePaths(markdownRaw).map((p) => resolveImageCandidate(p));
  const orderedUnique: string[] = [];
  const seen = new Set<string>();
  const pushOrdered = (candidate: string) => {
    const resolved = path.resolve(candidate);
    if (seen.has(resolved)) return;
    seen.add(resolved);
    orderedUnique.push(resolved);
  };
  for (const p of markdownImagePaths) {
    pushOrdered(p);
  }

  const metadataImages = Array.isArray(metadata?.images) ? metadata.images : [];
  for (const raw of metadataImages) {
    if (typeof raw !== 'string' || !raw.trim()) continue;
    pushOrdered(resolveImageCandidate(raw));
  }

  if (fs.existsSync(imagesDir)) {
    const fromImageDir = fs.readdirSync(imagesDir)
      .filter((f) => /\.(jpe?g|png|gif|webp|bmp)$/i.test(f))
      .sort()
      .map((f) => path.join(imagesDir, f));
    for (const p of fromImageDir) {
      pushOrdered(p);
    }
  }
  imagePaths = orderedUnique;

  const parsed = parseBlogResult(blogResultPath, metadata);

  log.info(`포스트 로드 완료: ${path.basename(absDir)}`);
  log.info(`  제목: ${parsed.title}`);
  log.info(`  본문: ${parsed.body.length}자`);
  log.info(`  해시태그: ${parsed.hashtags.length}개`);
  log.info(`  이미지: ${imagePaths.length}장`);
  log.info(`  플레이스홀더: ${parsed.imagePlaceholders.length}개`);
  for (const [idx, imagePath] of imagePaths.entries()) {
    const exists = fs.existsSync(imagePath);
    const size = exists ? fs.statSync(imagePath).size : 0;
    log.info(`  이미지경로[${idx + 1}] exists=${exists} size=${size} path=${imagePath}`);
  }

  return { dirPath: absDir, blogResultPath, imagesDir, metadataPath, imagePaths, metadata, parsed };
}
