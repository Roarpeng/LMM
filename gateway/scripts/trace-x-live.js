'use strict';
/**
 * trace-x-live.js — X 轴双驱方向性调试记录器（只读 FC03，绝不写命令）
 *
 * 目的：区分「X− 顿挫后停死」的三类根因
 *   A 命令丢失：按住 X− 时命令镜像 word4 bit7 掉了
 *   B 逻辑/轴故障：命令位仍在，vAct 掉 0 且 xFaultM1/M2 置位
 *   C 机械/驱动不对称：命令位在，vActM2 << vActM1（M2 拖后腿）或 syncErr 爆掉
 *
 * 同时读命令镜像(4096,96W)与状态镜像(4352,96W)，每周期追加一行 CSV（每行 flush）。
 *
 * 用法:
 *   node gateway/scripts/trace-x-live.js [host] [secs] [ms] [outfile]
 *   默认: 192.168.1.88 240s 100ms gateway/x-trace-live.csv
 */
const ModbusRTU = require('modbus-serial');
const fs = require('fs');
const path = require('path');

const host = process.argv[2] || '192.168.1.88';
const secs = Number(process.argv[3] || 240);
const ms = Number(process.argv[4] || 100);
const out = process.argv[5] || path.join(__dirname, '..', 'x-trace-live.csv');
const CMD = 4096, ST = 4352, WORDS = 96;

function s32(w, o) {
  let v = ((w[o] & 0xffff) << 16) | (w[o + 1] & 0xffff);
  if (v >= 0x80000000) v -= 0x100000000;
  return v;
}
const f = (w, o) => s32(w, o) / 1000;
const bit = (w, o, b) => (w[o] >> b) & 1;

const HEAD = [
  't_ms', 'cmdSeq', 'cmdSeqTail', 'cmdValid', 'hb', 'cmdW4hex',
  'jogXP', 'jogXN', 'spinL', 'spinR', 'en', 'auto', 'stop', 'estop',
  'stSeq', 'devState', 'alarm', 'posM1', 'posM2', 'dPos',
  'vCmdM1', 'vCmdM2', 'vActM1', 'vActM2', 'syncErr',
  'faultM1', 'faultM2', 'w36hex', 'dirXActive', 'dirOnline', 'tcpConn', 'tcpTimeout',
].join(',');

(async () => {
  const c = new ModbusRTU();
  c.setTimeout(1500);
  await c.connectTCP(host, { port: 502 });
  c.setID(1);
  const fd = fs.openSync(out, 'w');
  fs.writeSync(fd, HEAD + '\n');
  const t0 = Date.now();
  console.log('[trace-x-live] -> ' + out + ' (' + secs + 's @' + ms + 'ms) host=' + host);
  while (Date.now() - t0 < secs * 1000) {
    const t = Date.now() - t0;
    try {
      const rc = await c.readHoldingRegisters(CMD, WORDS);
      const rs = await c.readHoldingRegisters(ST, WORDS);
      const cw = Array.from(rc.data), sw = Array.from(rs.data);
      const magicOk = (cw[0] === 0x4c4d || cw[0] === 19533) && cw[2] === cw[95];
      const row = [
        t, cw[2], cw[95], magicOk ? 1 : 0, cw[3], '0x' + cw[4].toString(16).padStart(4, '0'),
        bit(cw, 4, 6), bit(cw, 4, 7), bit(cw, 4, 8), bit(cw, 4, 9), bit(cw, 4, 4), bit(cw, 4, 5), bit(cw, 4, 1), bit(cw, 4, 0),
        sw[2], sw[6], sw[8], f(sw, 14), f(sw, 16), (f(sw, 14) - f(sw, 16)),
        f(sw, 24), f(sw, 26), f(sw, 32), f(sw, 34), f(sw, 37),
        bit(sw, 11, 8), bit(sw, 11, 9), '0x' + sw[36].toString(16).padStart(4, '0'),
        bit(sw, 42, 0), bit(sw, 42, 4), bit(sw, 10, 14), bit(sw, 10, 15),
      ];
      fs.writeSync(fd, row.join(',') + '\n');
    } catch (e) {
      fs.writeSync(fd, t + ',,,,,,,,,,,,,,,,,,,,,,,,,,,,,,ERR:' + e.message.replace(/,/g, ' ') + '\n');
    }
    await new Promise((r) => setTimeout(r, ms));
  }
  fs.closeSync(fd);
  c.close(() => { console.log('[trace-x-live] done'); process.exit(0); });
})().catch((e) => { console.error('trace-x-live failed:', e.message); process.exit(1); });
