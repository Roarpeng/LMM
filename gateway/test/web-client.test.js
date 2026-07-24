'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const html = fs.readFileSync(
  path.join(__dirname, '..', '..', 'web', 'live', 'index.html'),
  'utf8',
);

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
  const bindRange = section('function bindRange(', "bindRange('p-velx'");

  assert.match(bindRange, /sync\(false\)/);
  assert.match(bindRange, /addEventListener\(['"]input['"][^]*sync\(true\)/);
});

test('force simulation starts false and its checkbox is not selected', () => {
  const checkbox = html.match(/<input[^>]+id="force-sim"[^>]*>/)?.[0];

  assert.ok(checkbox, 'force simulation checkbox missing');
  assert.doesNotMatch(checkbox, /\bchecked\b/);
  assert.match(html, /HMI_xForceSimEnable:\s*false/);
});
