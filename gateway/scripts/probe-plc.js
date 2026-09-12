'use strict';
/**
 * probe-plc.js — 只读探测 PLC 从站寄存器，定位 LMM 协议镜像位置/映射问题。
 * 基址取自 config/modbus-map.json（可用 PLC_CMD_BASE / PLC_STATUS_BASE 覆盖）。
 * 用法: node scripts/probe-plc.js [host] [port] [unitId]
 */
const ModbusRTU = require('modbus-serial');
const map = require('../../config/modbus-map.json');
const host = process.argv[2] || process.env.PLC_HOST || '192.168.1.88';
const port = Number(process.argv[3] || process.env.PLC_PORT || 502);
const unit = Number(process.argv[4] || process.env.PLC_UNIT_ID || 1);
const CMD = Number(process.env.PLC_CMD_BASE || map.command.baseAddress);
const ST = Number(process.env.PLC_STATUS_BASE || map.status.baseAddress);

function hex(w) { return '0x' + w.toString(16).padStart(4, '0'); }
function block(words, base) {
  const magicAt = words.findIndex((w) => w === 0x4c4d);
  console.log('  words[0..7] = ' + words.slice(0, 8).map(hex).join(' '));
  console.log('  0x4C4D(magic) at index ' + magicAt + (magicAt >= 0 ? ' (Holding ' + (base + magicAt) + ')' : ''));
}

(async () => {
  const client = new ModbusRTU();
  client.setTimeout(800);
  await client.connectTCP(host, { port });
  client.setID(unit);
  console.log('connected ' + host + ':' + port + ' unit=' + unit + '  cmd@' + CMD + ' status@' + ST);

  const ranges = [...new Set([0, 64, CMD, CMD + 64, ST, ST + 64])].filter((b) => b >= 0).sort((a, b) => a - b);
  for (const base of ranges) {
    try {
      const r = await client.readHoldingRegisters(base, 64);
      console.log('Holding ' + base + '..' + (base + 63) + ':');
      block(r.data, base);
    } catch (e) {
      console.log('Holding ' + base + ' ERROR: ' + e.message);
    }
  }

  const limit = Math.max(1300, ST + 128);
  console.log('scan 0..' + limit + ' for 0x4C4D ...');
  const hits = [];
  for (let base = 0; base < limit; base += 64) {
    try {
      const r = await client.readHoldingRegisters(base, Math.min(64, limit - base));
      r.data.forEach((w, i) => { if (w === 0x4c4d) hits.push(base + i); });
    } catch (e) { /* skip */ }
  }
  console.log('magic hits at Holding: ' + (hits.length ? hits.join(', ') : '(none)'));
  console.log('');
  if (hits.includes(ST)) {
    console.log('[probe] 状态区 OK：Holding ' + ST + ' = 0x4C4D，LMM 状态镜像已发布。');
  } else {
    console.log('[probe] 状态区缺失：Holding ' + ST + '..' + (ST + 63) + ' 没有 0x4C4D。');
    console.log('        修：确认 PLC 在线时 MB_StatusOut[0]=19533，且从站映射的十六进制起始地址 = 0x' + ST.toString(16));
    console.log('            （InoProShop 该字段为十六进制：十进制 4096 要填 1000，4352 要填 1100）。');
  }
  if (hits.includes(CMD)) console.log('[probe] 命令区 OK：Holding ' + CMD + ' = 0x4C4D（Gateway 写入已到达 PLC）。');
  else console.log('[probe] 命令区未见写入：Holding ' + CMD + ' 无 0x4C4D（网关未写或基址不符）。');
  client.close(() => process.exit(0));
})().catch((e) => { console.error('probe failed:', e.message); process.exit(1); });
