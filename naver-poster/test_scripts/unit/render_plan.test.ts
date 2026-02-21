import { buildRenderPlanItems, type ChunkAnchorPlacement, type RenderChunk } from '../../src/utils/render_plan';

describe('render plan ordering', () => {
  test('I1->C2, I2->C3이면 각 이미지가 해당 chunk 텍스트 바로 위에 배치된다', () => {
    const chunks: RenderChunk[] = [
      { chunkId: 'C001', sectionIndex: 0, sectionTitle: '첫 방문기', content: '도입 텍스트' },
      { chunkId: 'C002', sectionIndex: 0, sectionTitle: '첫 방문기', content: '입구는 줄이 짧았습니다.' },
      { chunkId: 'C003', sectionIndex: 0, sectionTitle: '첫 방문기', content: '주문은 키오스크로 했습니다.' },
    ];
    const placements: ChunkAnchorPlacement[] = [
      { imageIndex: 1, chunkId: 'C002' },
      { imageIndex: 2, chunkId: 'C003' },
    ];

    const items = buildRenderPlanItems(chunks, placements);
    const image1Idx = items.findIndex((item) => item.type === 'image' && item.index === 1);
    const image2Idx = items.findIndex((item) => item.type === 'image' && item.index === 2);
    const chunk2TextIdx = items.findIndex(
      (item) => item.type === 'text' && item.content.includes('입구는 줄이 짧았습니다.'),
    );
    const chunk3TextIdx = items.findIndex(
      (item) => item.type === 'text' && item.content.includes('주문은 키오스크로 했습니다.'),
    );

    expect(image1Idx).toBe(chunk2TextIdx - 1);
    expect(image2Idx).toBe(chunk3TextIdx - 1);
  });
});
