#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

function pad(v) { return String(v).padStart(2, '0'); }
function dayKey(d = new Date()) {
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
}

const dir = path.resolve(process.cwd(), 'logs', dayKey());
const file = path.join(dir, 'app.log');

if (!fs.existsSync(file)) {
  console.error(`[logs:today] file not found: ${file}`);
  process.exit(1);
}

console.log(`[logs:today] tail -f ${file}`);
const child = spawn('tail', ['-f', file], { stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 0));
