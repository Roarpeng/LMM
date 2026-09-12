'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const liveDir = path.join(__dirname, '..', '..', 'web', 'live');
const html = ['index.html', 'styles.css', 'app.js']
  .map((file) => fs.readFileSync(path.join(liveDir, file), 'utf8'))
  .join('\n');

function section(start, end) {
  const startIndex = html.indexOf(start);
  const endIndex = html.indexOf(end, startIndex + start.length);
  assert.notEqual(startIndex, -1, `missing section start: ${start}`);
  assert.notEqual(endIndex, -1, `missing section end: ${end}`);
  return html.slice(startIndex, endIndex);
}

test('WebSocket onopen sends ping but never sends t:w or flushes commands', () => {
  const onOpen = section('ws.onopen = () => {', 'ws.onclose = () => {');

  assert.match(onOpen, /t:\s*['"]ping['"]/);
  assert.doesNotMatch(onOpen, /\bflush\s*\(/);
  assert.doesNotMatch(onOpen, /t:\s*['"]w['"]/);
});

test('web client requires explicit local control claim before command writes', () => {
  const flush = section('function flush(', 'function patch(');
  const patch = section('function patch(', 'function connect(');
  const onClose = section('ws.onclose = () => {', 'ws.onerror =');

  assert.match(html, /let controlClaimed\s*=\s*false/);
  assert.match(flush, /if\s*\(\s*!controlClaimed/);
  assert.match(patch, /controlClaimed\s*=\s*true/);
  assert.match(onClose, /controlClaimed\s*=\s*false/);
});

test('range initialization updates local display without claiming or writing', () => {
  const bindParam = section('function bindParam(', "bindParam('p-velx'");

  assert.match(bindParam, /apply\(r\.value,\s*false\)/);
  assert.match(bindParam, /addEventListener\(['"]input['"][^]*apply\(r\.value,\s*true\)/);
  assert.match(bindParam, /if\s*\(\s*user\)\s*\{\s*controlClaimed\s*=\s*true/);
});

test('force simulation starts false and its checkbox is not selected', () => {
  const checkbox = html.match(/<input[^>]+id="force-sim"[^>]*>/)?.[0];

  assert.ok(checkbox, 'force simulation checkbox missing');
  assert.doesNotMatch(checkbox, /\bchecked\b/);
  assert.match(html, /HMI_xForceSimEnable:\s*false/);
});

test('status pills bind HMI_xDevStop / HMI_xDevRun / HMI_xDevError by name', () => {
  assert.match(html, /HMI_xDevStop/);
  assert.match(html, /HMI_xDevRun/);
  assert.match(html, /HMI_xDevError/);
  assert.match(html, /msg\.HMI_xDevStop/);
  assert.match(html, /msg\.HMI_xDevRun/);
  assert.match(html, /msg\.HMI_xDevError/);
});

test('live page mentions every modbus-map command and status field name', () => {
  const map = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', '..', 'config', 'modbus-map.json'), 'utf8'),
  );
  const missing = [];
  for (const f of map.command.fields) {
    if (!html.includes(f.name)) missing.push('cmd:' + f.name);
  }
  for (const f of map.status.fields) {
    if (!html.includes(f.name)) missing.push('st:' + f.name);
  }
  assert.deepEqual(missing, [], 'missing map fields in web/live/index.html:\n' + missing.join('\n'));
});
