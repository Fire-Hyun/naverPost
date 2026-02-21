const fs = require('fs');
const path = require('path');

function writeFixture(baseDir, name, payload) {
  const dir = path.join(baseDir, name);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'debug_fixture.json'), JSON.stringify(payload, null, 2), 'utf-8');
  console.log(`[fixture] ${path.join(dir, 'debug_fixture.json')}`);
}

function buildCases() {
  const shortText = '짧은 텍스트 케이스 '.repeat(12).slice(0, 200);
  const productionText = Array.from(
    { length: 8 },
    (_, i) => `문단 ${i + 1}: 제주 식당 후기 상세 설명입니다. `.repeat(18),
  ).join('\n\n');
  const specialText = '"따옴표" + 😀 이모지 + 줄바꿈\n다음 줄 [사진1] 마커\n탭\t문자 포함';

  return [
    {
      name: 'case1_short_200',
      title: '재현 케이스 1',
      blocks: [{ type: 'text', content: shortText }],
    },
    {
      name: 'case2_production_1200',
      title: '재현 케이스 2',
      blocks: [{ type: 'text', content: productionText }],
    },
    {
      name: 'case3_special_chars',
      title: '재현 케이스 3',
      blocks: [
        { type: 'text', content: specialText },
        { type: 'image', index: 1, marker: '[사진1]' },
      ],
    },
  ];
}

function main() {
  const output = process.argv[2] || '/tmp/naver_editor_debug/fixtures';
  fs.mkdirSync(output, { recursive: true });
  for (const fixture of buildCases()) {
    writeFixture(output, fixture.name, fixture);
  }
}

main();
