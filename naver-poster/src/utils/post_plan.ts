import * as crypto from 'crypto';
import type { PostBlock } from './parser';

export type PostPlanBlockType = 'text' | 'section_title' | 'image';

export interface PostPlanBlock {
  blockId: string;
  type: PostPlanBlockType;
  text?: string;
  imagePath?: string;
  imageIndex?: number;
  sourceIndex: number;
}

export interface PostPlan {
  blocks: PostPlanBlock[];
}

export interface PostPlanState {
  insertedBlockIds: Set<string>;
  insertedImageIds: Set<string>;
}

function stableHash(input: string): string {
  return crypto.createHash('sha1').update(input).digest('hex').slice(0, 12);
}

function toImageId(imagePath: string, imageIndex: number): string {
  return `image:${imageIndex}:${stableHash(imagePath)}`;
}

export function createPostPlanState(): PostPlanState {
  return {
    insertedBlockIds: new Set<string>(),
    insertedImageIds: new Set<string>(),
  };
}

export function buildPostPlan(blocks: PostBlock[], imagePaths: string[]): PostPlan {
  const planBlocks: PostPlanBlock[] = blocks.map((block, sourceIndex) => {
    if (block.type === 'text' || block.type === 'section_title') {
      const text = block.content;
      const blockId = `${block.type}:${sourceIndex}:${stableHash(text)}`;
      return {
        blockId,
        type: block.type,
        text,
        sourceIndex,
      };
    }

    const imageIndex = block.index;
    const imagePath = imagePaths[imageIndex - 1] ?? '';
    const imageId = toImageId(imagePath || `missing:${imageIndex}`, imageIndex);
    const blockId = `image:${sourceIndex}:${stableHash(imageId)}`;
    return {
      blockId,
      type: 'image',
      imagePath,
      imageIndex,
      sourceIndex,
    };
  });

  return { blocks: planBlocks };
}

export function getImageId(imagePath: string, imageIndex: number): string {
  return toImageId(imagePath, imageIndex);
}

export async function executePostPlanExactlyOnce(
  plan: PostPlan,
  state: PostPlanState,
  runner: (block: PostPlanBlock) => Promise<void>,
): Promise<void> {
  for (const block of plan.blocks) {
    if (state.insertedBlockIds.has(block.blockId)) continue;
    await runner(block);
    state.insertedBlockIds.add(block.blockId);
    if (block.type === 'image' && block.imagePath && block.imageIndex) {
      state.insertedImageIds.add(toImageId(block.imagePath, block.imageIndex));
    }
  }
}
