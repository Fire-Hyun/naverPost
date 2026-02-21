import { spawn } from 'child_process';
import * as path from 'path';

function parseArg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx >= 0 && process.argv[idx + 1]) {
    return process.argv[idx + 1];
  }
  return undefined;
}

async function run(): Promise<void> {
  const projectRoot = path.resolve(__dirname, '../..');
  const targetDir = parseArg('--dir') || process.env.TEST_DRAFT_DIR;

  if (!targetDir) {
    console.error('[FAIL] --dir 또는 TEST_DRAFT_DIR가 필요합니다.');
    process.exit(1);
  }

  const cliArgs = ['tsx', 'src/cli/post_to_naver.ts', '--dir', targetDir];
  const child = spawn('npx', cliArgs, {
    cwd: projectRoot,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let combinedOutput = '';

  child.stdout.on('data', (chunk: Buffer) => {
    const text = chunk.toString();
    combinedOutput += text;
    process.stdout.write(text);
  });

  child.stderr.on('data', (chunk: Buffer) => {
    const text = chunk.toString();
    combinedOutput += text;
    process.stderr.write(text);
  });

  const exitCode = await new Promise<number>((resolve) => {
    child.on('close', (code) => resolve(code ?? 1));
  });

  if (exitCode !== 0) {
    console.error(`[FAIL] naver-post 실행 실패 (exit=${exitCode})`);
    process.exit(exitCode);
  }

  const marker = 'NAVER_POST_RESULT_JSON:';
  const line = combinedOutput
    .split('\n')
    .find((l) => l.includes(marker));

  if (!line) {
    console.error('[FAIL] 결과 JSON 마커를 찾지 못했습니다.');
    process.exit(1);
  }

  const reportRaw = line.slice(line.indexOf(marker) + marker.length).trim();
  const report = JSON.parse(reportRaw);

  if (!report.draft_summary?.success) {
    console.error(`[FAIL] draft 저장 실패로 보고됨: ${report.draft_summary?.failure_reason || 'unknown'}`);
    process.exit(1);
  }

  if (report.steps?.F?.status !== 'success') {
    console.error(`[FAIL] Step F 실패: ${JSON.stringify(report.steps?.F)}`);
    process.exit(1);
  }

  console.log(`[PASS] 임시저장 통합 검증 통과: overall=${report.overall_status}, image=${report.image_summary?.status}`);
}

run().catch((error) => {
  console.error(`[FAIL] 통합 테스트 실행 중 예외: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
