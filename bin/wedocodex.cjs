#!/usr/bin/env node
'use strict';

const { spawnSync } = require('node:child_process');
const path = require('node:path');

function findPython(run = spawnSync, platform = process.platform) {
  const candidates = platform === 'win32'
    ? [['py', '-3'], ['python'], ['python3']]
    : [['python3'], ['python']];
  const probe = 'import json,sys; print(json.dumps({"version":list(sys.version_info[:2]),"executable":sys.executable}))';
  for (const [command, ...prefix] of candidates) {
    const result = run(command, [...prefix, '-c', probe], {
      encoding: 'utf8', timeout: 5000, windowsHide: true, shell: false,
    });
    if (result.error || result.status !== 0) continue;
    try {
      const info = JSON.parse(result.stdout.trim());
      const [major, minor] = info.version;
      if ((major > 3 || (major === 3 && minor >= 11)) &&
          typeof info.executable === 'string' && path.isAbsolute(info.executable)) {
        return info.executable;
      }
    } catch { /* Try the next installed interpreter. */ }
  }
  throw new Error('Python 3.11+ was not found. Install Python, reopen the terminal, then retry. No Python or model is downloaded automatically.');
}

function main(args = process.argv.slice(2)) {
  const python = findPython();
  const launcher = path.resolve(__dirname, '..', 'wedocodex.py');
  const result = spawnSync(python, [launcher, ...(args.length ? args : ['--help'])], {
    stdio: 'inherit', shell: false,
  });
  if (result.error) throw new Error('Could not start the Python launcher: ' + result.error.message);
  return result.status === null ? 1 : result.status;
}

module.exports = { findPython, main };
if (require.main === module) {
  try { process.exitCode = main(); }
  catch (error) { console.error('WEDOCODEX: ' + error.message); process.exitCode = 1; }
}
