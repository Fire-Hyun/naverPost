import { spawn } from 'child_process';
import * as path from 'path';

function parseArgList(name: string): string[] {
  const idx = process.argv.indexOf(name);
  if (idx < 0 || !process.argv[idx + 1]) return [];
  return process.argv[idx + 1].split(',').map((v) => v.trim()).filter(Boolean);
}

function parseReport(output: string): any {
  const marker = 'NAVER_POST_RESULT_JSON:';
  const line = output.split('\n').find((l) => l.includes(marker));
  if (!line) throw new Error('NAVER_POST_RESULT_JSON marker not found');
  return JSON.parse(line.slice(line.indexOf(marker) + marker.length).trim());
}

async function runOne(projectRoot: string, dir: string): Promise<any> {
  const child = spawn('npx', ['tsx', 'src/cli/post_to_naver.ts', '--dir', dir], {
    cwd: projectRoot,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

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

  const code = await new Promise<number>((resolve) => child.on('close', (c) => resolve(c ?? 1)));
  if (code !== 0) {
    throw new Error(`CLI failed for ${dir} (exit=${code})`);
  }
  return parseReport(output);
}

async function main(): Promise<void> {
  const projectRoot = path.resolve(__dirname, '../..');
  const workspaceRoot = path.resolve(projectRoot, '..');
  const dirs = parseArgList('--dirs');
  if (dirs.length < 1) {
    console.error('Usage: npx tsx test_scripts/integration/test_temp_save_samples.ts --dirs "<dir1>,<dir2>,<dir3>"');
    process.exit(1);
  }

  for (const dir of dirs) {
    const resolvedDir = path.isAbsolute(dir) ? dir : path.resolve(workspaceRoot, dir);
    const report = await runOne(projectRoot, resolvedDir);
    if (!report?.draft_summary?.success) {
      throw new Error(`draft failed for ${resolvedDir}: ${report?.draft_summary?.failure_reason || 'unknown'}`);
    }
    if (report?.steps?.F?.status !== 'success') {
      throw new Error(`step F failed for ${resolvedDir}: ${JSON.stringify(report?.steps?.F)}`);
    }
    console.log(`[INTEGRATION] PASS dir=${resolvedDir} overall=${report.overall_status} image=${report.image_summary?.status}`);
  }
}

main().catch((error) => {
  console.error(`[INTEGRATION][FAIL] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
