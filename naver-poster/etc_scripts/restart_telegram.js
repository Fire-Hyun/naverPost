#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const localScript = path.resolve(process.cwd(), 'etc_scripts', 'restart_telegram.sh');
const fallbackScript = path.resolve(process.cwd(), '..', 'etc_scripts', 'restart_telegram.sh');
const script = fs.existsSync(localScript) ? localScript : fallbackScript;
const result = spawnSync('bash', [script], { stdio: 'inherit' });
process.exit(result.status ?? 1);
