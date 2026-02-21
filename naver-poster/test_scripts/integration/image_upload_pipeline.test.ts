import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { loadPostDirectory } from '../../src/utils/parser';
import { uploadImages } from '../../src/naver/editor';

function createFakeCtx(): any {
  return {
    page: {
      screenshot: async () => undefined,
      content: async () => '<html></html>',
      url: () => 'https://blog.naver.com/PostWriteForm.naver',
      frames: () => [],
    },
    frame: {},
  };
}

describe('image upload pipeline', () => {
  test('markdown 상대경로 이미지를 절대경로로 resolve한다', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'image-pipeline-'));
    const postDir = path.join(base, 'post');
    const imagesDir = path.join(postDir, 'images');
    fs.mkdirSync(imagesDir, { recursive: true });
    fs.writeFileSync(path.join(imagesDir, 'a.jpg'), 'img', 'utf-8');
    fs.writeFileSync(
      path.join(postDir, 'blog_result.md'),
      '# 제목\n\n본문\n\n![사진1](images/a.jpg)\n',
      'utf-8',
    );

    const loaded = loadPostDirectory(postDir);
    expect(loaded.imagePaths.length).toBeGreaterThanOrEqual(1);
    expect(path.isAbsolute(loaded.imagePaths[0])).toBe(true);
    expect(loaded.imagePaths.some((p) => p.endsWith(path.join('images', 'a.jpg')))).toBe(true);
  });

  test('업로드 대상 이미지가 비면 IMAGE_LIST_EMPTY로 실패한다', async () => {
    const result = await uploadImages(createFakeCtx(), [], './artifacts');
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('IMAGE_LIST_EMPTY');
    expect(result.debug_path).toContain('/tmp/naver_editor_debug/');
  });

  test('파일이 없으면 IMAGE_FILE_NOT_FOUND로 실패한다', async () => {
    const missing = path.join(os.tmpdir(), `missing-${Date.now()}.jpg`);
    const result = await uploadImages(createFakeCtx(), [missing], './artifacts');
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('IMAGE_FILE_NOT_FOUND');
    expect(result.debug_path).toContain('/tmp/naver_editor_debug/');
  });
});
