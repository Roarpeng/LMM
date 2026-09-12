'use strict';

const map = require('../../config/modbus-map.json');
const {
  createCommandImage,
  decodeStatusImage,
} = require('./modbus-codec');

const { imageWords } = map.protocol;
const visionFieldList = (map.directx && map.directx.vision && map.directx.vision.fields) || [];
const commandFieldList = [
  ...map.command.fields,
  ...((map.directx && map.directx.command && map.directx.command.fields) || []),
];
const commandFields = new Map(commandFieldList.map((field) => [field.name, field]));

// 通信失效时的命令镜像：置「停止」并保持急停为正常（HMI_xEStop=TRUE）。
// 不主动置 HMI_xEStop=FALSE，避免 PLC 侧 xEStopLatched 锁存后必须手动复位；
// 物理急停仍是独立且更严的安全回路。
const FAIL_SAFE_COMMAND_VALUES = Object.freeze(Object.fromEntries(
  [...commandFieldList, ...visionFieldList].map((field) => [
    field.name,
    field.type === 'BOOL' ? (field.name === 'HMI_xStop' || field.name === 'HMI_xEStop') : 0,
  ]),
));

class WebWriteError extends TypeError {
  constructor(message) {
    super(message);
    this.code = 'INVALID_WRITE';
  }
}

function modbusError(message, modbusErrorCode) {
  const error = new RangeError(message);
  error.modbusErrorCode = modbusErrorCode;
  return error;
}

function illegalAddress(address) {
  return modbusError(`Illegal Modbus holding-register address: ${address}`, 0x02);
}

function validateFieldValue(field, value) {
  if (field.type === 'BOOL') {
    if (typeof value !== 'boolean') {
      throw new WebWriteError(`Invalid web write for ${field.name}: expected boolean`);
    }
    return;
  }
  if (field.type === 'UINT') {
    if (!Number.isInteger(value) || value < 0 || value > 0xffff) {
      throw new WebWriteError(`Invalid web write for ${field.name}: expected UINT`);
    }
    return;
  }
  if (field.type === 'SCALED_DINT') {
    const scaled = Math.round(value * field.scale);
    if (
      typeof value !== 'number'
      || !Number.isFinite(value)
      || !Number.isSafeInteger(scaled)
      || scaled < -0x80000000
      || scaled > 0x7fffffff
    ) {
      throw new WebWriteError(`Invalid web write for ${field.name}: outside scaled DINT`);
    }
    return;
  }
  if (field.type === 'SCALED_INT') {
    const scaled = Math.round(value * field.scale);
    if (
      typeof value !== 'number'
      || !Number.isFinite(value)
      || !Number.isSafeInteger(scaled)
      || scaled < -0x8000
      || scaled > 0x7fff
    ) {
      throw new WebWriteError(`Invalid web write for ${field.name}: outside scaled INT`);
    }
    return;
  }
  throw new WebWriteError(`Invalid web write type for ${field.name}`);
}

function createModbusStore(options = {}) {
  const onStatus = options.onStatus || (() => {});
  const onProtocolError = options.onProtocolError || (() => {});
  const commandValues = {
    ...FAIL_SAFE_COMMAND_VALUES,
    ...(options.initialCommands || {}),
  };
  let sequence = 0;
  let heartbeat = 0;
  let visionSeq = 0;
  let commandWords = createCommandImage(commandValues, sequence, heartbeat);

  function refreshCommandImage() {
    commandWords = createCommandImage(commandValues, sequence, heartbeat);
  }

  function advanceCommandImage() {
    sequence = (sequence + 1) & 0xffff;
    heartbeat = (heartbeat + 1) & 0xffff;
    refreshCommandImage();
  }

  // 主站每周期单独推进心跳，维持 PLC 侧 tonHb 远程在线看门狗；
  // 命令序号（sequence）只在真正写入命令快照时推进。
  function advanceHeartbeat() {
    heartbeat = (heartbeat + 1) & 0xffff;
    refreshCommandImage();
  }

  function commandOffset(address) {
    const offset = address - map.command.baseAddress;
    if (offset < 0 || offset >= imageWords) throw illegalAddress(address);
    return offset;
  }

  const vector = {
    getHoldingRegister(address, unitID, callback) {
      try {
        callback(null, commandWords[commandOffset(address)]);
      } catch (error) {
        callback(error);
      }
    },

    setRegister(address, value, unitID, callback) {
      callback(modbusError('FC06 is not supported; use one complete FC16 image', 0x01));
    },

    setRegisterArray(address, values, unitID, callback) {
      try {
        if (
          address !== map.status.baseAddress
          || !Array.isArray(values)
          || values.length !== imageWords
        ) {
          throw illegalAddress(
            `${address}; FC16 requires one complete ${imageWords}-word image at ${map.status.baseAddress}`,
          );
        }
        if (values.some((value) => !Number.isInteger(value) || value < 0 || value > 0xffff)) {
          throw modbusError('FC16 contains an invalid register value', 0x03);
        }

        const decoded = decodeStatusImage(Uint16Array.from(values));
        if (!decoded.valid) {
          onProtocolError(decoded.diagnostics);
          throw modbusError(`Invalid status image: ${decoded.diagnostics.errors.join(',')}`, 0x03);
        }
        onStatus({ t: 's', ...decoded.values });
        callback(null);
      } catch (error) {
        callback(error);
      }
    },
  };

  function applyWebWrite(message) {
    if (!message || typeof message !== 'object' || Array.isArray(message)) {
      throw new WebWriteError('Invalid web write message');
    }
    const updates = [];
    for (const [key, value] of Object.entries(message)) {
      if (key === 't' || key === 'seq') continue;
      const field = commandFields.get(key);
      if (!field) throw new WebWriteError(`Invalid web write field: ${key}`);
      validateFieldValue(field, value);
      updates.push([key, value]);
    }
    for (const [key, value] of updates) commandValues[key] = value;
    advanceCommandImage();
  }

  function applyVisionWrite(message) {
    const data = message || {};
    commandValues.Vis_xEnable = Boolean(data.enable);
    commandValues.Vis_rVelM1Set = Number(data.velM1) || 0;
    commandValues.Vis_rVelM2Set = Number(data.velM2) || 0;
    visionSeq = (visionSeq + 1) & 0xffff;
    commandValues.Vis_wSeq = visionSeq;
    refreshCommandImage();
  }

  function releaseVision() {
    commandValues.Vis_xEnable = false;
    commandValues.Vis_rVelM1Set = 0;
    commandValues.Vis_rVelM2Set = 0;
    refreshCommandImage();
  }

  function safeguardCommands() {
    Object.assign(commandValues, FAIL_SAFE_COMMAND_VALUES);
    advanceCommandImage();
  }

  function getCommandWords() {
    return Uint16Array.from(commandWords);
  }

  function ingestStatusWords(values) {
    if (
      !Array.isArray(values)
      && !(values instanceof Uint16Array)
    ) {
      throw illegalAddress(
        `status; FC03 requires one complete ${imageWords}-word image at ${map.status.baseAddress}`,
      );
    }
    const list = Array.from(values);
    if (list.length !== imageWords) {
      throw illegalAddress(
        `${map.status.baseAddress}; FC03 requires one complete ${imageWords}-word image at ${map.status.baseAddress}`,
      );
    }
    if (list.some((value) => !Number.isInteger(value) || value < 0 || value > 0xffff)) {
      throw modbusError('status image contains an invalid register value', 0x03);
    }

    const decoded = decodeStatusImage(Uint16Array.from(list));
    if (!decoded.valid) {
      onProtocolError(decoded.diagnostics);
      throw modbusError(`Invalid status image: ${decoded.diagnostics.errors.join(',')}`, 0x03);
    }
    onStatus({ t: 's', ...decoded.values });
  }

  return {
    vector,
    applyWebWrite,
    applyVisionWrite,
    releaseVision,
    safeguardCommands,
    advanceHeartbeat,
    getCommandValues: () => ({ ...commandValues }),
    getCommandWords,
    ingestStatusWords,
  };
}

module.exports = {
  DEFAULT_COMMAND_VALUES: FAIL_SAFE_COMMAND_VALUES,
  FAIL_SAFE_COMMAND_VALUES,
  WebWriteError,
  createModbusStore,
};
