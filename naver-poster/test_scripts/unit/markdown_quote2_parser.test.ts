import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { parseBlogResult } from '../../src/utils/parser';

describe('markdown quote2 parser', () => {
  test('단독 **소제목**은 section_title로, 문장 중간 **강조**는 유지된다', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'quote2-parser-'));
    const file = path.join(dir, 'blog_result.md');
    fs.writeFileSync(file, [
      '# 테스트 제목',
      '',
      '**첫 방문기**',
      '문장 중간 **포인트** 는 일반 본문으로 남아야 함',
      '',
    ].join('\n'), 'utf-8');

    const parsed = parseBlogResult(file, null);
    const sectionTitles = parsed.blocks.filter((b) => b.type === 'section_title');
    expect(sectionTitles).toHaveLength(1);
    expect(sectionTitles[0]).toMatchObject({ type: 'section_title', content: '첫 방문기' });
    const texts = parsed.blocks.filter((b) => b.type === 'text').map((b: any) => b.content).join('\n');
    expect(texts).toContain('**포인트**');
  });
});
