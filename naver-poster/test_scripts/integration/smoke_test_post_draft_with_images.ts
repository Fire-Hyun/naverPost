import { spawn } from 'child_process';
import * as path from 'path';

type Scenario = {
  name: string;
  dir: string;
  expectedRequested: number;
  env?: NodeJS.ProcessEnv;
  expectDraftSuccess: boolean;
  expectImageStatus?: Array<'full' | 'partial' | 'none' | 'not_requested'>;
};

function parseArg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return undefined;
}

async function runCli(
  projectRoot: string,
  dir: string,
  extraEnv: NodeJS.ProcessEnv | undefined
): Promise<{ exitCode: number; output: string }> {
  const child = spawn(
    'npx',
    ['tsx', 'src/cli/post_to_naver.ts', '--dir', dir],
    {
      cwd: projectRoot,
      env: { ...process.env, ...(extraEnv || {}) },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );

  let output = '';
  child.stdout.on('data', (chunk: Buffer) => {
    const text = chunk.toString();
    output += text;
    process.stdout.write(text);
  });
  child.stderr.on('data', (chunk: Buffer) => {
    const text = chunk.toString();
    output += text;
    process.stderr.write(text);
  });

  const exitCode = await new Promise<number>((resolve) => {
    child.on('close', (code) => resolve(code ?? 1));
  });
  return { exitCode, output };
}

function extractReport(output: string): any {
  const marker = 'NAVER_POST_RESULT_JSON:';
  const line = output.split('\n').find((l) => l.includes(marker));
  if (!line) throw new Error('결과 JSON 마커를 찾지 못했습니다.');
  const payload = line.slice(line.indexOf(marker) + marker.length).trim();
  return JSON.parse(payload);
}

function assertScenario(scenario: Scenario, report: any): void {
  const requested = report?.image_summary?.requested_count ?? -1;
  if (requested !== scenario.expectedRequested) {
    throw new Error(`[${scenario.name}] requested_count mismatch: expected=${scenario.expectedRequested}, actual=${requested}`);
  }

  const draftSuccess = Boolean(report?.draft_summary?.success);
  if (draftSuccess !== scenario.expectDraftSuccess) {
    throw new Error(`[${scenario.name}] draft success mismatch: expected=${scenario.expectDraftSuccess}, actual=${draftSuccess}`);
  }

  if (scenario.expectImageStatus && scenario.expectImageStatus.length > 0) {
    const status = report?.image_summary?.status;
    if (!scenario.expectImageStatus.includes(status)) {
      throw new Error(`[${scenario.name}] image status mismatch: expected one of ${scenario.expectImageStatus.join(', ')}, actual=${status}`);
    }
  }

  if (!report?.steps?.F) {
    throw new Error(`[${scenario.name}] Step F 결과가 없습니다.`);
  }
}

async function main(): Promise<void> {
  const projectRoot = path.resolve(__dirname, '../..');
  const dirOne = parseArg('--dir1') || process.env.SMOKE_DIR_1;
  const dirFive = parseArg('--dir5') || process.env.SMOKE_DIR_5;

  if (!dirOne || !dirFive) {
    console.error('Usage: npx tsx test_scripts/integration/smoke_test_post_draft_with_images.ts --dir1 <1-image-dir> --dir5 <5-image-dir>');
    console.error('or set env: SMOKE_DIR_1, SMOKE_DIR_5');
    process.exit(1);
  }

  const scenarios: Scenario[] = [
    {
      name: 'single-image-draft',
      dir: dirOne,
      expectedRequested: 1,
      expectDraftSuccess: true,
      expectImageStatus: ['full', 'partial', 'none'],
    },
    {
      name: 'five-images-draft',
      dir: dirFive,
      expectedRequested: 5,
      expectDraftSuccess: true,
      expectImageStatus: ['full', 'partial', 'none'],
    },
    {
      name: 'simulated-upload-timeout',
      dir: dirOne,
      expectedRequested: 1,
      env: { SIMULATE_IMAGE_UPLOAD_FAILURE: 'timeout' },
      expectDraftSuccess: true,
      expectImageStatus: ['none'],
    },
    {
      name: 'parallel-multi-image-order',
      dir: dirFive,
      expectedRequested: 5,
      expectDraftSuccess: true,
      expectImageStatus: ['full', 'partial', 'none'],
    },
  ];

  for (const scenario of scenarios) {
    console.log(`\n[SMOKE] start: ${scenario.name}`);
    const run = await runCli(projectRoot, scenario.dir, scenario.env);
    if (run.exitCode !== 0) {
      throw new Error(`[${scenario.name}] CLI failed (exit=${run.exitCode})`);
    }
    const report = extractReport(run.output);
    assertScenario(scenario, report);
    console.log(`[SMOKE] pass: ${scenario.name} overall=${report.overall_status} image=${report.image_summary.status}`);
  }
}

main().catch((error) => {
  console.error(`[SMOKE][FAIL] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
