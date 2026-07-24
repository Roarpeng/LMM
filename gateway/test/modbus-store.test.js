'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const map = require('../../config/modbus-map.json');
const {
  decodeCommandImage,
  encodeStatusImage,
} = require('../lib/modbus-codec');
const {
  createModbusStore,
  FAIL_SAFE_COMMAND_VALUES,
} = require('../lib/modbus-store');

function readRegister(vector, address) {
  return new Promise((resolve, reject) => {
    vector.getHoldingRegister(address, 1, (error, value) => {
      if (error) reject(error);
      else resolve(value);
    });
  });
}

function writeRegister(vector, address, value) {
  return new Promise((resolve, reject) => {
    vector.setRegister(address, value, 1, (error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

function writeRegisterArray(vector, address, values) {
  return new Promise((resolve, reject) => {
    vector.setRegisterArray(address, values, 1, (error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

async function readCommandImage(vector) {
  const words = [];
  for (let offset = 0; offset < map.protocol.imageWords; offset += 1) {
    words.push(await readRegister(vector, map.command.baseAddress + offset));
  }
  return Uint16Array.from(words);
}

test('rejects holding-register addresses outside the two mapped images', async () => {
  const { vector } = createModbusStore();

  await assert.rejects(readRegister(vector, map.command.baseAddress - 1), /address/i);
  await assert.rejects(
    writeRegisterArray(
      vector,
      map.status.baseAddress + map.protocol.imageWords,
      Array(map.protocol.imageWords).fill(0),
    ),
    /address/i,
  );
});

test('FC03 reads a valid 64-word command image from address 1000', async () => {
  const { vector } = createModbusStore();

  const decoded = decodeCommandImage(await readCommandImage(vector));

  assert.equal(decoded.valid, true);
  assert.equal(decoded.diagnostics.sequence, 0);
  assert.equal(decoded.diagnostics.heartbeat, 0);
});

test('publishes status from one complete FC16 transaction at 1100', async () => {
  const published = [];
  const { vector } = createModbusStore({
    onStatus: (status) => published.push(status),
  });
  const words = encodeStatusImage(
    { HMI_eDevState: 1, HMI_xDevRun: true, AxisFb_rPosZ: -0.456 },
    7,
    3,
    12,
  );

  await writeRegisterArray(vector, map.status.baseAddress, Array.from(words));

  assert.equal(published.length, 1);
  assert.equal(published[0].t, 's');
  assert.equal(published[0].HMI_eDevState, 1);
  assert.equal(published[0].HMI_xDevRun, true);
  assert.equal(published[0].AxisFb_rPosZ, -0.456);
});

test('partial or shifted FC16 transactions never publish or accumulate', async () => {
  const published = [];
  const { vector } = createModbusStore({
    onStatus: (status) => published.push(status),
  });
  const words = Array.from(encodeStatusImage({ HMI_xDevRun: true }, 3, 2, 1));

  await assert.rejects(
    writeRegisterArray(vector, map.status.baseAddress, words.slice(0, 32)),
    /complete.*64/i,
  );
  await assert.rejects(
    writeRegisterArray(vector, map.status.baseAddress + 32, words.slice(32)),
    /complete.*64/i,
  );

  assert.equal(published.length, 0);
});

test('FC06 writes are rejected without changing or publishing status', async () => {
  const published = [];
  const { vector } = createModbusStore({
    onStatus: (status) => published.push(status),
  });

  await assert.rejects(writeRegister(vector, map.status.baseAddress, map.protocol.magic));
  assert.equal(published.length, 0);
});

test('valid browser writes update mapped command fields and heartbeat', async () => {
  const { vector, applyWebWrite } = createModbusStore();

  applyWebWrite({
    t: 'w',
    seq: 999,
    HMI_xJogXPos: true,
    HMI_rJogVelX: 1.25,
  });
  const decoded = decodeCommandImage(await readCommandImage(vector));

  assert.equal(decoded.valid, true);
  assert.equal(decoded.diagnostics.sequence, 1);
  assert.equal(decoded.diagnostics.heartbeat, 1);
  assert.equal(decoded.values.HMI_xJogXPos, true);
  assert.equal(decoded.values.HMI_rJogVelX, 1.25);
});

test('production command image starts fail-safe', async () => {
  const { vector } = createModbusStore();
  const decoded = decodeCommandImage(await readCommandImage(vector));

  assert.equal(decoded.values.HMI_xStop, true);
  assert.equal(decoded.values.HMI_xEnable, false);
  assert.equal(decoded.values.HMI_xStart, false);
  assert.equal(decoded.values.HMI_xJogXPos, false);
  assert.equal(decoded.values.HMI_xHomeExec, false);
  assert.equal(decoded.values.HMI_xAutoStart, false);
  assert.equal(decoded.values.HMI_xForceTare, false);
  assert.equal(decoded.values.HMI_xForceSimEnable, false);
});

test('invalid web values reject atomically and preserve the command image', async () => {
  const { vector, applyWebWrite } = createModbusStore();
  const before = await readCommandImage(vector);
  const invalidWrites = [
    { HMI_xEnable: 1 },
    { HMI_iAutoPasses: -1 },
    { HMI_iAutoPasses: 65536 },
    { HMI_iAutoPasses: 1.5 },
    { HMI_rJogVelX: Number.NaN },
    { HMI_rJogVelX: Number.POSITIVE_INFINITY },
    { HMI_rJogVelX: 2147484 },
    { HMI_eDevState: 1 },
    { unknown: true },
  ];

  for (const message of invalidWrites) {
    assert.throws(() => applyWebWrite({ t: 'w', HMI_xStop: false, ...message }), /write/i);
    assert.deepEqual(await readCommandImage(vector), before);
  }
});

test('safe command transition atomically disables every boolean action', async () => {
  const { vector, applyWebWrite, safeguardCommands } = createModbusStore();
  applyWebWrite({
    t: 'w',
    HMI_xStop: false,
    HMI_xEnable: true,
    HMI_xStart: true,
    HMI_xJogXPos: true,
    HMI_xHomeExec: true,
    HMI_xAutoStart: true,
    HMI_xForceTare: true,
    HMI_xForceSimEnable: true,
  });

  safeguardCommands();
  const decoded = decodeCommandImage(await readCommandImage(vector));

  for (const [key, expected] of Object.entries(FAIL_SAFE_COMMAND_VALUES)) {
    assert.equal(decoded.values[key], expected, key);
  }
});
