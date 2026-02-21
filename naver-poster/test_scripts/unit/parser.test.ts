import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { parseBlogResult, loadMetadata, loadPostDirectory } from '../../src/utils/parser';

// 임시 디렉토리 헬퍼
function createTempDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'naver-poster-test-'));
}

function cleanup(dir: string) {
  fs.rmSync(dir, { recursive: true, force: true });
}

describe('parseBlogResult', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = createTempDir();
  });
  afterEach(() => {
    cleanup(tmpDir);
  });

  test('frontmatter + 본문 파싱 (플레이스홀더 포함)', () => {
    const content = `---
generated_at: 2026-02-12T22:46:55
generation_model: gpt-4
---

장어 땡길 때는 장어집이 최고지.
장어집에 방문했어요.

(사진)

내부 분위기는 깔끔하고 따뜻해요.

(사진)

맛있었습니다.
#장심도한국본점 #장심도`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const metadata = { hashtags: ['#장심도한국본점 #장심도'], category: '맛집' };
    const result = parseBlogResult(filePath, metadata);

    // 제목: frontmatter 이후 첫 non-empty 라인
    expect(result.title).toBe('장어 땡길 때는 장어집이 최고지.');
    // 본문에 내용 있음
    expect(result.body.length).toBeGreaterThan(0);
    // 해시태그 추출
    expect(result.hashtags).toContain('#장심도한국본점');
    expect(result.hashtags).toContain('#장심도');
    // 이미지 플레이스홀더
    expect(result.imagePlaceholders.length).toBe(2);
    expect(result.blocks.filter((b) => b.type === 'image')).toHaveLength(2);
    // frontmatter
    expect(result.frontmatter['generation_model']).toBe('gpt-4');
  });

  test('# 제목 형식 파싱', () => {
    const content = `# 오늘의 맛집 후기

정말 맛있었습니다.
또 가고 싶어요.`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    expect(result.title).toBe('오늘의 맛집 후기');
    expect(result.body).toContain('정말 맛있었습니다');
    expect(result.body).not.toContain('# 오늘의');
  });

  test('TITLE: 형식 파싱', () => {
    const content = `TITLE: 강남 파스타 맛집
BODY:
여기는 정말 맛있어요.
크림소스가 일품!`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    expect(result.title).toBe('강남 파스타 맛집');
  });

  test('이미지 플레이스홀더 - 마크다운 형식', () => {
    const content = `# 테스트

첫 문장.

![사진1](images/photo1.jpg)

두 번째 문장.

<!--IMG:photo2.jpg-->

마지막.`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    expect(result.imagePlaceholders.length).toBe(2);
    expect(result.blocks.filter((b) => b.type === 'image')).toHaveLength(2);
  });

  test('레거시 마커 (사진1), [사진2]를 블록으로 변환', () => {
    const content = `TITLE: 마커 테스트
첫 문단입니다. (사진1) 다음 문장.

[사진2]

마지막 문단`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    const imageBlocks = result.blocks.filter((block) => block.type === 'image');
    expect(imageBlocks).toHaveLength(2);
    expect(imageBlocks[0]).toMatchObject({ type: 'image', index: 1 });
    expect(imageBlocks[1]).toMatchObject({ type: 'image', index: 2 });
    expect(result.blocks.some((block) => block.type === 'text' && block.content.includes('(사진1)'))).toBe(false);
  });

  test('**소제목** 라인을 section_title 블록으로 파싱한다', () => {
    const content = `TITLE: 구조 테스트

도입 문단입니다.

**주차정보**

주차는 지하를 이용했습니다.

[사진1]

**비용정보**

비용은 2만원대였습니다.`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    const sectionTitles = result.blocks.filter((b) => b.type === 'section_title');
    expect(sectionTitles).toHaveLength(2);
    expect(sectionTitles[0]).toMatchObject({ type: 'section_title', content: '주차정보' });
    expect(sectionTitles[1]).toMatchObject({ type: 'section_title', content: '비용정보' });
    expect(result.blocks.some((b) => b.type === 'text' && b.content.includes('**주차정보**'))).toBe(false);
  });

  test('문장 내부의 **강조**는 section_title로 승격하지 않고 본문에 유지한다', () => {
    const content = `TITLE: 강조 테스트

오늘은 **첫 방문기** 느낌으로 적어본다.

본문이 이어진다.`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    const sectionTitles = result.blocks.filter((b) => b.type === 'section_title');
    expect(sectionTitles).toHaveLength(0);
    expect(result.blocks.some((b) => b.type === 'text' && b.content.includes('**첫 방문기**'))).toBe(true);
  });

  test('**첫 방문기**와 trailing space는 section_title로 인식한다', () => {
    const content = `TITLE: 소제목 공백 테스트

**첫 방문기** 

입구는 대기 줄이 짧았습니다.`;
    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');
    const result = parseBlogResult(filePath);
    const sectionTitles = result.blocks.filter((b) => b.type === 'section_title');
    expect(sectionTitles).toHaveLength(1);
    expect(sectionTitles[0]).toMatchObject({ type: 'section_title', content: '첫 방문기' });
  });

  test('멀티라인 깨진 강조는 heading으로 오인하지 않는다', () => {
    const content = `TITLE: 깨진 강조 테스트

**첫 방문기
본문**

입구는 빠르게 안내받았습니다.`;
    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');
    const result = parseBlogResult(filePath);
    const sectionTitles = result.blocks.filter((b) => b.type === 'section_title');
    expect(sectionTitles).toHaveLength(0);
  });

  test('짧은 첫 줄 → 제목으로 사용', () => {
    const content = `강남 맛집 추천!

오늘 강남에서 맛있는 파스타를 먹었습니다.
크림소스가 정말 부드러웠어요.`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    expect(result.title).toBe('강남 맛집 추천!');
    expect(result.body).not.toContain('강남 맛집 추천!');
  });

  test('첫 non-empty 라인이 길어도 제목으로 사용', () => {
    const content = `이 문장은 매우 길어서 제목으로 사용하기에는 적절하지 않은 매우 긴 첫 번째 줄입니다 그래서 기본 제목이 사용될 것입니다.`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    expect(result.title).toBe('이 문장은 매우 길어서 제목으로 사용하기에는 적절하지 않은 매우 긴 첫 번째 줄입니다 그래서 기본 제목이 사용될 것입니다.');
  });

  test('제목은 정확히 첫 non-empty 한 줄이며 줄바꿈이 포함되지 않는다', () => {
    const content = `

   첫 줄 제목   
둘째 줄 본문 시작
셋째 줄 본문`;

    const filePath = path.join(tmpDir, 'blog_result.md');
    fs.writeFileSync(filePath, content, 'utf-8');

    const result = parseBlogResult(filePath);
    expect(result.title).toBe('첫 줄 제목');
    expect(result.title.includes('\n')).toBe(false);
    expect(result.body.startsWith('둘째 줄 본문 시작')).toBe(true);
  });
});

describe('loadMetadata', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = createTempDir();
  });
  afterEach(() => {
    cleanup(tmpDir);
  });

  test('metadata.json 정상 로드', () => {
    const meta = {
      user_input: {
        category: '맛집',
        visit_date: '2026-02-12',
        rating: 5,
        companion: '가족',
        personal_review: '맛있었다',
        hashtags: ['#테스트'],
      },
      images: ['img1.jpg', 'img2.jpg'],
    };
    fs.writeFileSync(path.join(tmpDir, 'metadata.json'), JSON.stringify(meta), 'utf-8');

    const result = loadMetadata(tmpDir);
    expect(result).not.toBeNull();
    expect(result!.category).toBe('맛집');
    expect(result!.rating).toBe(5);
    expect(result!.images).toEqual(['img1.jpg', 'img2.jpg']);
  });

  test('metadata.json 없으면 null', () => {
    const result = loadMetadata(tmpDir);
    expect(result).toBeNull();
  });
});

describe('loadPostDirectory image ordering', () => {
  let tmpDir: string;
  beforeEach(() => {
    tmpDir = createTempDir();
  });
  afterEach(() => {
    cleanup(tmpDir);
  });

  test('metadata 이미지 basename은 images/ 실제 파일로 정규화되고 중복되지 않는다', () => {
    const postDir = path.join(tmpDir, 'post');
    const imagesDir = path.join(postDir, 'images');
    fs.mkdirSync(imagesDir, { recursive: true });
    fs.writeFileSync(path.join(postDir, 'blog_result.md'), 'TITLE: t\n\n본문\n\n[사진1]\n[사진2]\n', 'utf-8');
    fs.writeFileSync(path.join(imagesDir, 'a.jpg'), '1');
    fs.writeFileSync(path.join(imagesDir, 'b.jpg'), '1');
    fs.writeFileSync(path.join(postDir, 'metadata.json'), JSON.stringify({
      images: ['a.jpg', 'b.jpg'],
      user_input: {},
    }), 'utf-8');

    const loaded = loadPostDirectory(postDir);
    expect(loaded.imagePaths).toHaveLength(2);
    expect(loaded.imagePaths[0]).toBe(path.join(imagesDir, 'a.jpg'));
    expect(loaded.imagePaths[1]).toBe(path.join(imagesDir, 'b.jpg'));
  });
});

describe('loadPostDirectory', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = createTempDir();
  });
  afterEach(() => {
    cleanup(tmpDir);
  });

  test('blog_result.md 없으면 에러', () => {
    expect(() => loadPostDirectory(tmpDir)).toThrow('blog_result.md가 없습니다');
  });

  test('정상 디렉토리 로드', () => {
    // blog_result.md 생성
    fs.writeFileSync(
      path.join(tmpDir, 'blog_result.md'),
      '# 테스트 제목\n\n본문 내용입니다.',
      'utf-8'
    );

    // images 디렉토리 생성
    const imgDir = path.join(tmpDir, 'images');
    fs.mkdirSync(imgDir);

    const result = loadPostDirectory(tmpDir);
    expect(result.parsed.title).toBe('테스트 제목');
    expect(result.imagePaths).toHaveLength(0);
  });
});
