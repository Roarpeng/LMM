'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const map = require('../../config/modbus-map.json');
const {
  createCommandImage,
  decodeCommandImage,
  decodeStatusImage,
  encodeStatusImage,
} = require('../lib/modbus-codec');

function assertValidMapping(candidate) {
  assert.equal(candidate.protocol.imageWords, 64);
  assert.equal(candidate.command.baseAddress, map.command.baseAddress);
  assert.equal(candidate.status.baseAddress, map.status.baseAddress);

  const names = new Set();
  for (const image of [candidate.command, candidate.status]) {
    const wholeWords = new Set();
    const bitWords = new Map();
    for (const field of image.fields) {
      assert.ok(!names.has(field.name), `duplicate variable ${field.name}`);
      names.add(field.name);
      assert.ok(field.offset >= 0 && field.offset < candidate.protocol.imageWords);

      if (field.type === 'BOOL') {
        assert.ok(Number.isInteger(field.bit) && field.bit >= 0 && field.bit < 16);
        assert.ok(!wholeWords.has(field.offset), `overlap at ${field.offset}`);
        const bits = bitWords.get(field.offset) || new Set();
        assert.ok(!bits.has(field.bit), `overlap at ${field.offset}.${field.bit}`);
        bits.add(field.bit);
        bitWords.set(field.offset, bits);
      } else {
        const width = field.type === 'SCALED_DINT' ? 2 : 1;
        for (let index = 0; index < width; index += 1) {
          const offset = field.offset + index;
          assert.ok(offset < 63, `${field.name} overlaps trailer`);
          assert.ok(!wholeWords.has(offset) && !bitWords.has(offset), `overlap at ${offset}`);
          wholeWords.add(offset);
        }
      }
    }
  }
}

function runPythonMapValidation(candidate) {
  return spawnSync(
    'python3',
    [
      '-c',
      [
        'import json, sys',
        'from tools.generate_modbus_map import validate',
        'try:',
        '    validate(json.load(sys.stdin))',
        'except Exception as exc:',
        '    print(exc, file=sys.stderr)',
        '    raise SystemExit(1)',
      ].join('\n'),
    ],
    {
      cwd: process.cwd(),
      encoding: 'utf8',
      input: JSON.stringify(candidate),
    },
  );
}

test('command image round-trips signed scaled values', () => {
  const words = createCommandImage(
    { HMI_xJogXPos: true, HMI_rJogVelX: -1.25, HMI_rForceSet: 123.45 },
    7,
    65535,
  );
  const decoded = decodeCommandImage(words, 6);

  assert.equal(words.length, 64);
  assert.equal(words[0], 0x4c4d);
  assert.equal(words[1], 0x0100);
  assert.equal(words[2], 7);
  assert.equal(words[63], 7);
  assert.equal(words[3], 65535);
  assert.equal(words[4] & (1 << 6), 1 << 6);
  assert.equal(decoded.valid, true);
  assert.equal(decoded.isNew, true);
  assert.equal(decoded.values.HMI_xJogXPos, true);
  assert.equal(decoded.values.HMI_rJogVelX, -1.25);
  assert.equal(decoded.values.HMI_rForceSet, 123.45);
});

test('command image stores signed scaled DINTs as raw high-word-first values', () => {
  const words = createCommandImage(
    { HMI_rJogVelX: -1.25, HMI_rForceSet: 123.45 },
    1,
    1,
  );

  assert.equal(words[8], 0xffff);
  assert.equal(words[9], 0xfb1e);
  assert.equal(words[28], 0x0000);
  assert.equal(words[29], 0x3039);
});

test('status image round-trips bool fields and signed scaled DINTs', () => {
  const words = encodeStatusImage(
    {
      Tcp_iCommStatus: 2,
      HMI_eDevState: 1,
      HMI_eOpMode: 1,
      HMI_iAlarmShow: 1006,
      HMI_iAutoStepShow: 3,
      HMI_xAutoBusy: true,
      AxisFb_xReady: true,
      HMI_rForceShow: 123.45,
      AxisFb_rPosZ: -0.456,
    },
    12,
    7,
    0,
  );
  const decoded = decodeStatusImage(words);

  assert.equal(words.length, 64);
  assert.equal(words[2], 12);
  assert.equal(words[3], 7);
  assert.equal(words[4], 0);
  assert.equal(words[63], 12);
  assert.equal(decoded.valid, true);
  assert.equal(decoded.values.HMI_xAutoBusy, true);
  assert.equal(decoded.values.AxisFb_xReady, true);
  assert.equal(decoded.values.HMI_rForceShow, 123.45);
  assert.equal(decoded.values.AxisFb_rPosZ, -0.456);
});

test('decoder rejects an incompatible protocol version', () => {
  const words = createCommandImage({}, 1, 1);
  words[1] = 0x0200;

  const decoded = decodeCommandImage(words, 0);

  assert.equal(decoded.valid, false);
  assert.ok(decoded.diagnostics.errors.includes('VERSION_MISMATCH'));
});

test('decoder rejects a mismatched trailing sequence', () => {
  const words = encodeStatusImage({}, 9, 4, 3);
  words[63] = 10;

  const decoded = decodeStatusImage(words);

  assert.equal(decoded.valid, false);
  assert.ok(decoded.diagnostics.errors.includes('SEQUENCE_MISMATCH'));
});

test('heartbeat preserves the unsigned 16-bit wraparound', () => {
  const beforeWrap = decodeCommandImage(createCommandImage({}, 20, 65535), 19);
  const afterWrap = decodeCommandImage(createCommandImage({}, 21, 0), 20);

  assert.equal(beforeWrap.valid, true);
  assert.equal(beforeWrap.diagnostics.heartbeat, 65535);
  assert.equal(afterWrap.valid, true);
  assert.equal(afterWrap.diagnostics.heartbeat, 0);
});

test('command decoder detects repeated and wrapped sequences', () => {
  const repeated = decodeCommandImage(createCommandImage({}, 65535, 10), 65535);
  const wrapped = decodeCommandImage(createCommandImage({}, 0, 11), 65535);

  assert.equal(repeated.valid, true);
  assert.equal(repeated.isNew, false);
  assert.equal(wrapped.valid, true);
  assert.equal(wrapped.isNew, true);
});

test('first valid command is new without a previous sequence', () => {
  const decoded = decodeCommandImage(createCommandImage({}, 0, 1));

  assert.equal(decoded.valid, true);
  assert.equal(decoded.isNew, true);
});

test('mapping has unique variables and non-overlapping in-range fields', () => {
  assertValidMapping(map);
});

test('JavaScript mapping validation rejects BOOL and whole-word overlap', () => {
  const invalid = structuredClone(map);
  invalid.command.fields.push({
    name: 'HMI_iOverlappingWord',
    type: 'UINT',
    offset: 4,
  });

  assert.throws(() => assertValidMapping(invalid), /overlap/);
});

test('Python mapping validation rejects changed command and status bases', () => {
  const invalid = structuredClone(map);
  invalid.command.baseAddress = 999;
  invalid.status.baseAddress = 1101;

  const result = runPythonMapValidation(invalid);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /baseAddress/);
});

test('Python mapping validation rejects fields that cover header words', () => {
  const invalid = structuredClone(map);
  invalid.command.fields.push({
    name: 'HMI_iHeaderCollision',
    type: 'UINT',
    offset: 0,
  });

  const result = runPythonMapValidation(invalid);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /overlaps/);
});
