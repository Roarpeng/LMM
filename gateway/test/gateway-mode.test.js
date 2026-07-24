'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const gatewayPath = path.join(__dirname, '..', 'server.js');

function resolveMode(env) {
  const script = [
    `const { resolveGatewayMode } = require(${JSON.stringify(gatewayPath)});`,
    `process.stdout.write(resolveGatewayMode(${JSON.stringify(env)}));`,
  ].join('');
  return spawnSync(process.execPath, ['-e', script], {
    encoding: 'utf8',
    timeout: 2000,
  });
}

test('production mode never falls back to mock', () => {
  const explicitProduction = resolveMode({ MOCK_PLC: '0' });
  const defaultProduction = resolveMode({});

  assert.equal(explicitProduction.status, 0, explicitProduction.stderr);
  assert.equal(explicitProduction.stdout, 'modbus-server');
  assert.equal(defaultProduction.status, 0, defaultProduction.stderr);
  assert.equal(defaultProduction.stdout, 'modbus-server');
});

test('mock mode is enabled only by MOCK_PLC=1', () => {
  const result = resolveMode({ MOCK_PLC: '1' });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, 'mock');
});

test('gateway no longer contains the legacy PLC TCP client or port 9100', () => {
  const source = fs.readFileSync(gatewayPath, 'utf8');

  assert.doesNotMatch(source, /\bnet\.connect\b/);
  assert.doesNotMatch(source, /\b9100\b/);
});
