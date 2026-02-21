import type { PostBlock } from './parser';

export type RenderChunk = {
  chunkId: string;
  sectionIndex: number;
  sectionTitle: string;
  content: string;
};

export type ChunkAnchorPlacement = {
  imageIndex: number;
  chunkId: string | null;
};

export function buildRenderPlanItems(
  chunks: RenderChunk[],
  placements: ChunkAnchorPlacement[],
): PostBlock[] {
  const imagesByChunk = new Map<string, number[]>();
  const tailImages: number[] = [];
  for (const placement of placements) {
    if (!placement.chunkId) {
      tailImages.push(placement.imageIndex);
      continue;
    }
    const list = imagesByChunk.get(placement.chunkId) ?? [];
    list.push(placement.imageIndex);
    imagesByChunk.set(placement.chunkId, list);
  }

  const blocks: PostBlock[] = [];
  const sectionStarted = new Set<number>();
  for (const chunk of chunks) {
    if (!sectionStarted.has(chunk.sectionIndex)) {
      blocks.push({ type: 'section_title', content: chunk.sectionTitle });
      sectionStarted.add(chunk.sectionIndex);
    }
    const chunkImages = imagesByChunk.get(chunk.chunkId) ?? [];
    for (const imageIndex of chunkImages) {
      blocks.push({ type: 'image', index: imageIndex, marker: `ANCHOR:${chunk.chunkId}` });
    }
    blocks.push({ type: 'text', content: chunk.content });
  }

  for (const imageIndex of tailImages) {
    blocks.push({ type: 'image', index: imageIndex, marker: 'FALLBACK_TAIL' });
  }
  return blocks;
}
