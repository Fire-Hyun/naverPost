import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { loadPostDirectory } from '../../../src/utils/parser';

describe('post/load_post_dir', () => {
  test('blog_result.md + images 구조를 로드한다', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'load-post-dir-'));
    const postDir = path.join(base, '20260214(하이디라오 제주도점)');
    const imagesDir = path.join(postDir, 'images');
    fs.mkdirSync(imagesDir, { recursive: true });
    fs.writeFileSync(path.join(postDir, 'blog_result.md'), '# 제목\n\n본문', 'utf-8');
    fs.writeFileSync(path.join(imagesDir, 'a.jpg'), 'x', 'utf-8');

    const loaded = loadPostDirectory(postDir);
    expect(loaded.parsed.title).toBe('제목');
    expect(loaded.imagePaths.length).toBe(1);
  });

  test('blog_result.md가 없으면 명확한 에러를 낸다', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'load-post-dir-missing-'));
    const postDir = path.join(base, 'invalid');
    fs.mkdirSync(postDir, { recursive: true });

    expect(() => loadPostDirectory(postDir)).toThrow(/blog_result\.md가 없습니다/);
  });
});
