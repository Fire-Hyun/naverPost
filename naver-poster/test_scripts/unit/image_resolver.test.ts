import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { loadPostDirectory } from '../../src/utils/parser';
import { uploadImages } from '../../src/naver/editor';

function fakeCtx(): any {
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

describe('image resolver', () => {
  test('상대경로 이미지를 절대경로로 변환한다', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'image-resolver-'));
    fs.mkdirSync(path.join(base, 'images'), { recursive: true });
    fs.writeFileSync(path.join(base, 'images', 'x.jpg'), 'x', 'utf-8');
    fs.writeFileSync(path.join(base, 'blog_result.md'), '# t\n\n![i](images/x.jpg)\n', 'utf-8');
    const loaded = loadPostDirectory(base);
    expect(loaded.imagePaths.length).toBe(1);
    expect(path.isAbsolute(loaded.imagePaths[0])).toBe(true);
  });

  test('파일 미존재면 IMAGE_FILE_NOT_FOUND', async () => {
    const p = path.join(os.tmpdir(), `missing-${Date.now()}.jpg`);
    const result = await uploadImages(fakeCtx(), [p], './artifacts');
    expect(result.success).toBe(false);
    expect(result.reason_code).toBe('IMAGE_FILE_NOT_FOUND');
  });
});
