'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { findPython } = require('./bin/wedocodex.cjs');
const launcher = path.join(__dirname, 'bin', 'wedocodex.cjs');
const pythonPath = path.resolve('Python with spaces', 'python');

test('rejects old/missing Python before finding a compatible interpreter', () => {
  let attempts = 0;
  const found = findPython((command, args, options) => {
    assert.equal(options.shell, false);
    attempts++;
    return { status: 0, stdout: JSON.stringify({ version: [3, attempts === 1 ? 10 : 11], executable: pythonPath }) };
  }, 'darwin');
  assert.equal(found, pythonPath);
  assert.equal(attempts, 2);
  assert.throws(() => findPython(() => ({ status: null, error: new Error('missing') }), 'darwin'), /Python 3.11/);
});

test('malformed probes do not launch an inferred executable', () => {
  for (const stdout of ['garbage', '{}', '{"version":[3,11],"executable":"relative"}']) {
    assert.throws(() => findPython(() => ({ status: 0, stdout }), 'win32'), /Python 3.11/);
  }
});

test('real Node to Python forwarding preserves literal arguments and child exit status', () => {
  const prompt = 'quotes " hello & $(touch never) ; %PATH% !value!\nsecond line';
  const result = spawnSync(process.execPath, [launcher, 'show', 'saver', '--autopilot', '--prompt', prompt], { encoding: 'utf8', shell: false });
  assert.equal(result.status, 0, result.stderr);
  const data = JSON.parse(result.stdout);
  assert.ok(data.argv.at(-1).endsWith('\nTask: ' + prompt));
  const failed = spawnSync(process.execPath, [launcher, 'invalid-action'], { encoding: 'utf8', shell: false });
  assert.equal(failed.status, 2);
});

test('install dry-run does not create state; install, repeat, update and uninstall stay isolated', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'wedocodex-npx-'));
  const home = path.join(temp, 'home with spaces');
  const run = (...args) => {
    const result = spawnSync(process.execPath, [launcher, ...args, '--home', home], { encoding: 'utf8', shell: false });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
  };
  try {
    run('install', '--dry-run');
    assert.equal(fs.existsSync(path.join(home, 'wedocodex-install.json')), false);
    run('install');
    assert.ok(fs.existsSync(path.join(home, 'skills', 'wedocodex', 'SKILL.md')));
    assert.equal(run('install').changed_files, 0);
    run('update', '--dry-run');
    run('uninstall');
    assert.equal(fs.existsSync(path.join(home, 'skills', 'wedocodex', 'SKILL.md')), false);
  } finally { fs.rmSync(temp, { recursive: true }); }
});
