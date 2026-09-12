'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const ModbusRTU = require('modbus-serial');

const map = require('../../config/modbus-map.json');
const { encodeStatusImage, decodeCommandImage } = require('../lib/modbus-codec');
const { createModbusMaster } = require('../lib/modbus-master');
const { createModbusStore } = require('../lib/modbus-store');

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test('modbus master writes command and reads status from a local slave', {
  timeout: 5000,
}, async () => {
  const port = 21000 + (process.pid % 1000);
  const commandWords = new Uint16Array(map.protocol.imageWords);
  let statusWords = Array.from(encodeStatusImage({
    HMI_xDevRun: true,
    HMI_xDevStop: false,
    AxisFb_xReady: true,
  }, 1, 1, 1));

  const vector = {
    getHoldingRegister(address, _unitID, callback) {
      try {
        if (address >= map.status.baseAddress
          && address < map.status.baseAddress + map.protocol.imageWords) {
          callback(null, statusWords[address - map.status.baseAddress]);
          return;
        }
        if (address >= map.command.baseAddress
          && address < map.command.baseAddress + map.protocol.imageWords) {
          callback(null, commandWords[address - map.command.baseAddress]);
          return;
        }
        const error = new RangeError('illegal');
        error.modbusErrorCode = 0x02;
        callback(error);
      } catch (error) {
        callback(error);
      }
    },
    setRegister(_address, _value, _unitID, callback) {
      const error = new Error('FC06 unsupported');
      error.modbusErrorCode = 0x01;
      callback(error);
    },
    setRegisterArray(address, values, _unitID, callback) {
      try {
        const base = map.command.baseAddress;
        const tailAddress = base + map.command.header.tailSequence;
        const okBase = address === base && values.length <= map.protocol.imageWords;
        const okTail = address === tailAddress && values.length === 1;
        if (!okBase && !okTail) {
          const error = new RangeError('illegal FC16');
          error.modbusErrorCode = 0x02;
          callback(error);
          return;
        }
        for (let i = 0; i < values.length; i += 1) commandWords[address - base + i] = values[i];
        callback(null);
      } catch (error) {
        callback(error);
      }
    },
  };

  const slave = new ModbusRTU.ServerTCP(vector, {
    host: '127.0.0.1',
    port,
    unitID: 1,
  });
  await new Promise((resolve) => slave.once('initialized', resolve));

  let sawStatus = false;
  const store = createModbusStore({
    onStatus(status) {
      if (status.HMI_xDevRun === true) sawStatus = true;
    },
  });
  store.applyWebWrite({ t: 'w', HMI_xStop: false, HMI_xEnable: true });

  const master = createModbusMaster({
    host: '127.0.0.1',
    port,
    unitID: 1,
    store,
    pollMs: 50,
  });
  master.start();

  try {
    await delay(300);
    assert.equal(sawStatus, true);
    const decoded = decodeCommandImage(commandWords);
    assert.equal(decoded.values.HMI_xEnable, true);
    assert.equal(decoded.values.HMI_xStop, false);
  } finally {
    await master.close();
    await new Promise((resolve) => slave.close(resolve));
  }
});
