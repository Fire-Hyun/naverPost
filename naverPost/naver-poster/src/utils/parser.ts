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
  frontmatter: Record<string, string>;
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

// ────────────────────────────────────────────
// 제목 추출 전략
// ────────────────────────────────────────────
function extractTitle(
  bodyLines: string[],
  metadata: PostMetadata | null
): { title: string; bodyStartIdx: number } {
  // 전략 1: 첫 줄이 # 으로 시작
  if (bodyLines.length > 0 && bodyLines[0].startsWith('# ')) {
    return { title: bodyLines[0].slice(2).trim(), bodyStartIdx: 1 };
  }

  // 전략 2: TITLE: 라인
  for (let i = 0; i < Math.min(bodyLines.length, 5); i++) {
    if (bodyLines[i].startsWith('TITLE:')) {
      return { title: bodyLines[i].slice(6).trim(), bodyStartIdx: i + 1 };
    }
  }

  // 전략 3: 메타데이터에서 해시태그/카테고리 기반 생성
  if (metadata) {
    const tags = metadata.hashtags ?? [];
    // 해시태그에서 상호명 추출
    for (const tag of tags) {
      // "#장심도한국본점 #장심도" 같은 형태
      const names = tag.match(/#([가-힣A-Za-z0-9_]+)/g);
      if (names && names.length > 0) {
        const placeName = names[0].replace('#', '');
        const category = metadata.category ?? '';
        if (category === '맛집') return { title: `${placeName} 방문 후기`, bodyStartIdx: 0 };
        if (category === '카페') return { title: `${placeName} 카페 후기`, bodyStartIdx: 0 };
        if (category === '호텔') return { title: `${placeName} 숙박 후기`, bodyStartIdx: 0 };
        return { title: `${placeName} 후기`, bodyStartIdx: 0 };
      }
    }
  }

  // 전략 4: 첫 줄이 짧으면 제목으로 사용
  if (bodyLines.length > 0 && bodyLines[0].trim().length > 0 && bodyLines[0].trim().length <= 40) {
    return { title: bodyLines[0].trim(), bodyStartIdx: 1 };
  }

  // 전략 5: 최후 - 날짜 기반
  return { title: '블로그 포스팅', bodyStartIdx: 0 };
}

// ────────────────────────────────────────────
// blog_result.md 파싱
// ────────────────────────────────────────────
export function parseBlogResult(filePath: string, metadata: PostMetadata | null = null): ParsedPost {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const { frontmatter, content } = parseFrontmatter(raw);

  // 빈 줄 제거하지 않고 줄 단위로 분리
  const allLines = content.split('\n');

  // 앞뒤 빈 줄 제거
  let startIdx = 0;
  while (startIdx < allLines.length && allLines[startIdx].trim() === '') startIdx++;
  let endIdx = allLines.length - 1;
  while (endIdx >= 0 && allLines[endIdx].trim() === '') endIdx--;
  const trimmedLines = allLines.slice(startIdx, endIdx + 1);

  // 마지막 줄에서 해시태그 분리
  let hashtagLine = '';
  const contentLines = [...trimmedLines];
  if (contentLines.length > 0) {
    const lastLine = contentLines[contentLines.length - 1].trim();
    if (lastLine.startsWith('#') && extractHashtags(lastLine).length > 0) {
      hashtagLine = contentLines.pop()!;
    }
  }

  // 제목 추출
  const { title, bodyStartIdx } = extractTitle(contentLines, metadata);
  const bodyLines = contentLines.slice(bodyStartIdx);

  // 이미지 플레이스홀더 위치 찾기
  const imagePlaceholders: number[] = [];
  bodyLines.forEach((line, idx) => {
    if (isImagePlaceholder(line)) {
      imagePlaceholders.push(idx);
    }
  });

  const hashtags = extractHashtags(hashtagLine);
  const body = bodyLines.join('\n').trim();

  return { title, body, hashtags, imagePlaceholders, bodyLines, frontmatter };
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

  // 이미지 파일 목록
  let imagePaths: string[] = [];
  if (fs.existsSync(imagesDir)) {
    imagePaths = fs.readdirSync(imagesDir)
      .filter((f) => /\.(jpe?g|png|gif|webp|bmp)$/i.test(f))
      .sort()
      .map((f) => path.join(imagesDir, f));
  }

  const metadata = loadMetadata(absDir);
  const parsed = parseBlogResult(blogResultPath, metadata);

  log.info(`포스트 로드 완료: ${path.basename(absDir)}`);
  log.info(`  제목: ${parsed.title}`);
  log.info(`  본문: ${parsed.body.length}자`);
  log.info(`  해시태그: ${parsed.hashtags.length}개`);
  log.info(`  이미지: ${imagePaths.length}장`);
  log.info(`  플레이스홀더: ${parsed.imagePlaceholders.length}개`);

  return { dirPath: absDir, blogResultPath, imagesDir, metadataPath, imagePaths, metadata, parsed };
}
