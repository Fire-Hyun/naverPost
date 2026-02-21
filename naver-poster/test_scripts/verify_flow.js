#!/usr/bin/env node
/* eslint-disable no-console */
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function runCommand(title, cmd, args, opts = {}) {
  console.log(`\n[verify-flow] ${title}`);
  const result = spawnSync(cmd, args, {
    cwd: opts.cwd || process.cwd(),
    stdio: 'inherit',
    env: { ...process.env, ...(opts.env || {}) },
  });
  if ((result.status ?? 1) !== 0) {
    throw new Error(`${title} failed (exit=${result.status ?? 1})`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function normalizeText(text) {
  return String(text || '').replace(/\r\n/g, '\n');
}

function runMarkdownQuoteRuleCheck() {
  const sample = [
    '# 제목',
    '',
    '**소제목 단독라인**',
    '일반 문장 **중간강조** 유지',
    '',
  ].join('\n');
  const lines = normalizeText(sample).split('\n');
  const standaloneMatches = lines.filter((line) => /^\s*\*\*[^*\n]+\*\*\s*$/.test(line));
  const inlineMatches = lines.filter((line) => /\S+\s+\*\*[^*\n]+\*\*/.test(line));
  assert(standaloneMatches.length === 1, '단독 **소제목** 라인 감지 실패');
  assert(inlineMatches.length === 1, '문장 중간 **강조** 감지 실패');
}

async function runOpenAiCheck() {
  if (!process.env.OPENAI_API_KEY) {
    console.log('[verify-flow] OPENAI_API_KEY 미설정: OpenAI 실호출 체크는 건너뜀');
    return;
  }
  console.log('\n[verify-flow] OpenAI API 실호출 확인');
  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: process.env.OPENAI_VERIFY_MODEL || 'gpt-4o-mini',
      messages: [{ role: 'user', content: 'ping' }],
      max_tokens: 8,
    }),
  });
  if (response.status !== 200) {
    const body = await response.text().catch(() => '');
    throw new Error(`OpenAI API failed status=${response.status} body=${body.slice(0, 200)}`);
  }
  const json = await response.json();
  assert(Array.isArray(json.choices) && json.choices.length > 0, 'OpenAI JSON 응답 형식 오류');
}

function runOnlineChecks(projectRoot) {
  const online = String(process.env.VERIFY_FLOW_ONLINE || 'false').toLowerCase() === 'true';
  if (!online) {
    console.log('[verify-flow] VERIFY_FLOW_ONLINE=false: 로그인/실업로드 체크는 건너뜀');
    return;
  }

  runCommand(
    '1) 로그인 확인(healthcheck)',
    process.execPath,
    [path.join(projectRoot, 'dist/cli/post_to_naver.js'), '--healthcheck', '--headless'],
    { cwd: projectRoot },
  );

  const targetDir = process.env.VERIFY_FLOW_DIR || '';
  assert(targetDir.trim().length > 0, 'VERIFY_FLOW_ONLINE=true 인 경우 VERIFY_FLOW_DIR가 필요합니다');
  runCommand(
    '2) 임시저장 + draft 실재 검증',
    process.execPath,
    [path.join(projectRoot, 'dist/cli/post_to_naver.js'), `--dir=${targetDir}`, '--draft', '--headless'],
    { cwd: projectRoot },
  );
}

function runJestTests(projectRoot, title, testPaths) {
  runCommand(
    title,
    'npx',
    ['--no-install', 'jest', '--config', 'jest.config.js', '--runInBand', ...testPaths],
    { cwd: projectRoot },
  );
}

async function main() {
  const projectRoot = path.resolve(process.cwd());
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-flow-'));
  fs.writeFileSync(path.join(tmp, 'README.txt'), 'verify-flow temp', 'utf-8');

  runOnlineChecks(projectRoot);

  console.log('\n[verify-flow] 3) markdown quote2 파싱 규칙 체크');
  runMarkdownQuoteRuleCheck();

  runJestTests(projectRoot, '4) 인용구2 삽입 스모크 테스트', ['test_scripts/unit/editor_quote2_smoke.test.ts']);
  runJestTests(projectRoot, '5) 이미지 업로드 파이프라인 검증', ['test_scripts/integration/image_upload_pipeline.test.ts']);

  await runOpenAiCheck();

  runJestTests(projectRoot, '7) 텔레그램 세션/큐 흐름 테스트', [
    'test_scripts/integration/worker/queue_persistence.spec.ts',
    'test_scripts/integration/worker/worker_blocked_login.spec.ts',
  ]);

  runJestTests(projectRoot, '8) 핵심 단위 테스트 세트', [
    'test_scripts/unit/block_writer.test.ts',
    'test_scripts/unit/image_resolver.test.ts',
    'test_scripts/unit/session_lock.test.ts',
    'test_scripts/unit/markdown_quote2_parser.test.ts',
  ]);

  console.log('\n[verify-flow] PASS');
}

main().catch((error) => {
  console.error(`[verify-flow] FAIL: ${String(error?.message || error)}`);
  process.exit(1);
});
