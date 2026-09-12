'use strict';

const map = require('../../config/modbus-map.json');

const { protocol } = map;
const versionWord = (protocol.versionMajor << 8) | protocol.versionMinor;

function toWord(value) {
  return Number(value) & 0xffff;
}

function writeScaledDint(words, field, value) {
  const scaled = Math.round(Number(value || 0) * field.scale);
  if (!Number.isSafeInteger(scaled) || scaled < -0x80000000 || scaled > 0x7fffffff) {
    throw new RangeError(`${field.name} is outside signed DINT range`);
  }
  const unsigned = scaled >>> 0;
  words[field.offset] = unsigned >>> 16;
  words[field.offset + 1] = unsigned & 0xffff;
}

function readScaledDint(words, field) {
  const signed = (words[field.offset] << 16) | words[field.offset + 1];
  return signed / field.scale;
}

function writeScaledInt(words, field, value) {
  const scaled = Math.round(Number(value || 0) * field.scale);
  if (!Number.isSafeInteger(scaled) || scaled < -0x8000 || scaled > 0x7fff) {
    throw new RangeError(`${field.name} is outside signed INT range`);
  }
  words[field.offset] = scaled & 0xffff;
}

function readScaledInt(words, field) {
  let v = words[field.offset] & 0xffff;
  if (v >= 0x8000) v -= 0x10000;
  return v / field.scale;
}

function encodeFields(words, fields, values) {
  for (const field of fields) {
    const value = values[field.name];
    if (field.type === 'BOOL') {
      if (value) words[field.offset] |= 1 << field.bit;
    } else if (field.type === 'UINT') {
      words[field.offset] = toWord(value || 0);
    } else if (field.type === 'SCALED_DINT') {
      writeScaledDint(words, field, value);
    } else if (field.type === 'SCALED_INT') {
      writeScaledInt(words, field, value);
    } else {
      throw new TypeError(`Unsupported Modbus type: ${field.type}`);
    }
  }
}

function decodeFields(words, fields) {
  const values = {};
  for (const field of fields) {
    if (field.type === 'BOOL') {
      values[field.name] = Boolean(words[field.offset] & (1 << field.bit));
    } else if (field.type === 'UINT') {
      values[field.name] = words[field.offset];
    } else if (field.type === 'SCALED_DINT') {
      values[field.name] = readScaledDint(words, field);
    } else if (field.type === 'SCALED_INT') {
      values[field.name] = readScaledInt(words, field);
    } else {
      throw new TypeError(`Unsupported Modbus type: ${field.type}`);
    }
  }
  return values;
}

function createImage(image, values, sequence, headerValues) {
  const words = new Uint16Array(protocol.imageWords);
  words[image.header.magic] = protocol.magic;
  words[image.header.version] = versionWord;
  words[image.header.sequence] = toWord(sequence);
  words[image.header.tailSequence] = toWord(sequence);
  for (const [name, value] of Object.entries(headerValues)) {
    words[image.header[name]] = toWord(value);
  }
  encodeFields(words, image.fields, values || {});
  return words;
}

function validateImage(words, image) {
  const errors = [];
  if (!words || words.length !== protocol.imageWords) {
    errors.push('INVALID_LENGTH');
    return errors;
  }
  if (words[image.header.magic] !== protocol.magic) errors.push('MAGIC_MISMATCH');
  if ((words[image.header.version] >>> 8) !== protocol.versionMajor) {
    errors.push('VERSION_MISMATCH');
  }
  const seq = words[image.header.sequence];
  const tail = words[image.header.tailSequence];
  // 兼容：从站输出通道只发布前 64 字时（0.68 设备树 Leg 未同步扩到 96），尾部序号字读回 0。
  // 此时退回 magic/version/sequence 判定，避免把正常状态误判为离线。
  if (tail !== 0 && seq !== tail) {
    errors.push('SEQUENCE_MISMATCH');
  }
  return errors;
}

function createCommandImage(values, sequence, heartbeat) {
  const words = createImage(map.command, values, sequence, { heartbeat });
  if (map.directx && map.directx.command && map.directx.command.fields) {
    encodeFields(words, map.directx.command.fields, values || {});
  }
  if (map.directx && map.directx.vision && map.directx.vision.fields) {
    encodeFields(words, map.directx.vision.fields, values || {});
  }
  return words;
}

function encodeStatusImage(values, sequence, ack, heartbeat) {
  return createImage(map.status, values, sequence, { ack, heartbeat });
}

function decodeCommandImage(words, previousSequence) {
  const errors = validateImage(words, map.command);
  const sequence = words && words.length > map.command.header.sequence
    ? words[map.command.header.sequence]
    : undefined;
  const heartbeat = words && words.length > map.command.header.heartbeat
    ? words[map.command.header.heartbeat]
    : undefined;

  return {
    valid: errors.length === 0,
    isNew: errors.length === 0
      && (previousSequence == null || sequence !== toWord(previousSequence)),
    values: errors.includes('INVALID_LENGTH') ? {} : Object.assign(
      decodeFields(words, map.command.fields),
      map.directx && map.directx.command ? decodeFields(words, map.directx.command.fields) : {},
      map.directx && map.directx.vision ? decodeFields(words, map.directx.vision.fields) : {},
    ),
    diagnostics: {
      errors,
      sequence,
      tailSequence: words && words.length === protocol.imageWords
        ? words[map.command.header.tailSequence]
        : undefined,
      heartbeat,
      version: words && words.length === protocol.imageWords
        ? words[map.command.header.version]
        : undefined,
    },
  };
}

function decodeStatusImage(words) {
  const errors = validateImage(words, map.status);
  let values = {};
  if (!errors.includes('INVALID_LENGTH')) {
    values = decodeFields(words, map.status.fields);
    if (map.directx && map.directx.status) {
      Object.assign(values, decodeFields(words, map.directx.status.fields));
    }
  }
  return {
    valid: errors.length === 0,
    values,
    diagnostics: {
      errors,
      sequence: words && words.length === protocol.imageWords
        ? words[map.status.header.sequence]
        : undefined,
      tailSequence: words && words.length === protocol.imageWords
        ? words[map.status.header.tailSequence]
        : undefined,
      ack: words && words.length === protocol.imageWords
        ? words[map.status.header.ack]
        : undefined,
      heartbeat: words && words.length === protocol.imageWords
        ? words[map.status.header.heartbeat]
        : undefined,
      version: words && words.length === protocol.imageWords
        ? words[map.status.header.version]
        : undefined,
    },
  };
}

module.exports = {
  createCommandImage,
  decodeCommandImage,
  decodeStatusImage,
  encodeStatusImage,
};
