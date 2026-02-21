import * as fs from 'fs';
import * as path from 'path';

type TelegramUpdate = {
  update_id: number;
  message?: {
    message_id: number;
    chat: { id: number | string };
    text?: string;
    caption?: string;
    photo?: Array<{ file_id: string; file_unique_id: string; width: number; height: number; file_size?: number }>;
  };
};

type TelegramResponse<T> = {
  ok: boolean;
  result: T;
  description?: string;
};

export class TelegramClient {
  private readonly token: string;
  private readonly apiBase: string;
  private readonly fileBase: string;

  constructor(token: string) {
    this.token = token;
    this.apiBase = `https://api.telegram.org/bot${token}`;
    this.fileBase = `https://api.telegram.org/file/bot${token}`;
  }

  private async request<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
    const res = await fetch(`${this.apiBase}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload ? JSON.stringify(payload) : '{}',
    });
    if (!res.ok) {
      throw new Error(`telegram_api_http_error method=${method} status=${res.status}`);
    }
    const parsed = (await res.json()) as TelegramResponse<T>;
    if (!parsed.ok) {
      throw new Error(`telegram_api_error method=${method} description=${parsed.description ?? 'unknown'}`);
    }
    return parsed.result;
  }

  async pollUpdates(offset: number, timeoutSec: number): Promise<TelegramUpdate[]> {
    return await this.request<TelegramUpdate[]>('getUpdates', {
      offset,
      timeout: timeoutSec,
      allowed_updates: ['message'],
    });
  }

  async sendMessage(chatId: string | number, text: string): Promise<void> {
    await this.request('sendMessage', { chat_id: chatId, text });
  }

  async getFilePath(fileId: string): Promise<string> {
    const file = await this.request<{ file_path: string }>('getFile', { file_id: fileId });
    return file.file_path;
  }

  async downloadFile(filePath: string, outputPath: string): Promise<void> {
    const res = await fetch(`${this.fileBase}/${filePath}`);
    if (!res.ok) {
      throw new Error(`telegram_file_download_failed status=${res.status} path=${filePath}`);
    }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, buf);
  }
}

export type ParsedTelegramRequest = {
  title: string;
  body: string;
  mode: 'draft' | 'publish';
  storeName?: string;
};

export function parseTelegramRequest(textOrCaption: string | undefined): ParsedTelegramRequest {
  const text = (textOrCaption ?? '').trim();
  if (!text) {
    return {
      title: '텔레그램 업로드 요청',
      body: '이미지와 함께 업로드 요청이 수신되었습니다.',
      mode: 'draft',
    };
  }

  const lines = text.split('\n').map((line) => line.trim());
  const kv = new Map<string, string>();
  for (const line of lines) {
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim().toLowerCase();
    const value = line.slice(idx + 1).trim();
    if (value) kv.set(key, value);
  }

  const modeRaw = (kv.get('mode') ?? '').toLowerCase();
  const mode: 'draft' | 'publish' =
    modeRaw === 'publish' || /#publish|\/publish/.test(text.toLowerCase())
      ? 'publish'
      : 'draft';
  const title = kv.get('title') ?? lines.find((line) => line.length > 0) ?? '텔레그램 업로드 요청';

  const explicitBody = kv.get('body');
  const body = explicitBody
    ?? lines.filter((line) => line && !/^title\s*:/i.test(line) && !/^mode\s*:/i.test(line)).slice(1).join('\n')
    ?? '본문 없음';

  return {
    title,
    body: body || '본문 없음',
    mode,
    storeName: kv.get('store_name') ?? kv.get('place') ?? undefined,
  };
}

export function buildBlogResultMarkdown(input: ParsedTelegramRequest, imageCount: number): string {
  const placeholders = Array.from({ length: imageCount }, (_, i) => `[사진${i + 1}]`).join('\n');
  const body = placeholders ? `${input.body}\n\n${placeholders}` : input.body;
  return `# ${input.title}\n\n${body}\n`;
}

