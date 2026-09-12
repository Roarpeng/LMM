'use strict';
/**
 * trace-x.js — X 轴双驱现场抓波工具（只读 FC03，不写命令镜像）
 *
 * PLC 状态镜像（MB_StatusOut 96 WORD）每周期无条件刷新：
 *   w0=19533(magic) w1=256 w2=序列号(每周期+1) w95=同序列
 *   w14..15  rPosM1    (×1000, m)
 *   w16..17  rPosM2    (×1000, m)
 *   w24..25  rVelCmdM1 (×1000, m/s)
 *   w26..27  rVelCmdM2 (×1000, m/s)
 *   w10 状态位: bit0=DevStop bit1=DevRun bit2=DevError
 *   w11 状态位: 256=xFaultM1  512=xFaultM2  64=xMoveDoneX  32=xReady
 *
 * 用法:
 *   node gateway/scripts/trace-x.js --scan            # 找镜像真实基址/单元号
 *   node gateway/scripts/trace-x.js [host] [secs] [ms]# 抓波（默认基址 1100 单元 1）
 *   node gateway/scripts/trace-x.js --base 4100 --unit 255 [host] [secs] [ms]
 *
 * 现场用法: 抓波启动后按住 X− 点动约 5s（摇摆+爬行录进去），松手停稳，
 * 再按住 X+ 约 3s 对照。输出 CSV 到 stdout 并写 trace-x.csv。
 */
const ModbusRTU = require('modbus-serial');
const fs = require('fs');
const map = require('../../config/modbus-map.json');

const IMAGE_WORDS = map.protocol.imageWords;
const MAGIC = 19533;
const MAGIC_SWAP = 0x4d4c; // 19788，字节交换后的 magic

function s32(hi, lo) {
  let v = ((hi & 0xffff) << 16) | (lo & 0xffff);
  if (v >= 0x80000000) v -= 0x100000000;
  return v;
}

async function readBlock(client, base) {
  const r = await client.readHoldingRegisters(base, IMAGE_WORDS);
  return Array.from(r.data);
}

async function scan(client) {
  // 全地址域单字扫描：找 magic 19533（或字节交换 19788）出现的所有地址。
  // 命令镜像在 1000，状态镜像地址未知时用本模式定位。
  const hits = [];
  for (const fn of ['readHoldingRegisters', 'readInputRegisters']) {
    const method = client[fn].bind(client);
    for (let addr = 0; addr <= 65535; addr += 1) {
      try {
        const r = await method(addr, 1);
        const v = r.data[0];
        if (v === MAGIC || v === MAGIC_SWAP) {
          hits.push(`${fn}@${addr}=${v}`);
          console.error(`${fn}@${addr} = ${v} ${v === MAGIC ? '*** HIT ***' : '(swap)'}`);
          if (hits.length >= 16) break;
        }
      } catch (e) {
        // 未映射/不支持的区域会异常；连续大量异常后跳过该区段
        if (e.modbusErrorCode === 2 || /Illegal/i.test(String(e.message))) {
          continue;
        }
      }
    }
    if (hits.length >= 16) break;
  }
  if (hits.length === 0) {
    console.error('no magic found in 0..65535 (FC03/FC04)');
  }
}

async function main() {
  const args = process.argv.slice(2);
  const flag = (name, dflt) => {
    const i = args.indexOf(`--${name}`);
    return i >= 0 && args[i + 1] !== undefined ? Number(args[i + 1]) : dflt;
  };
  const host = args.find((a) => !a.startsWith('-')) || '192.168.1.88';
  const secs = flag('secs', 10);
  const ms = flag('ms', 100);
  const base = flag('base', 1100);
  const unit = flag('unit', 1);

  const client = new ModbusRTU();
  client.setTimeout(1500);
  await client.connectTCP(host, { port: 502 });
  console.error(`connected ${host}:502`);

  if (args.includes('--scan')) {
    await scan(client);
    try { client.close(() => {}); } catch { /* ignore */ }
    return;
  }

  client.setID(unit);
  // 首帧校验 magic，失败给出提示
  let first = await readBlock(client, base);
  if (first[0] !== MAGIC && first[0] !== MAGIC_SWAP) {
    console.error(
      `base=${base} unit=${unit} 无 magic（w0=${first[0]}，期望 ${MAGIC}）。` +
      `先跑 node gateway/scripts/trace-x.js --scan 找真实基址/单元号，` +
      `再用 --base <N> --unit <N> 抓波。`);
    try { client.close(() => {}); } catch { /* ignore */ }
    process.exit(2);
  }
  const swapped = first[0] === MAGIC_SWAP;
  console.error(`base=${base} unit=${unit} magic OK${swapped ? ' (字节交换)' : ''}, ${secs}s @ ${ms}ms`);

  const rows = [];
  const t0 = Date.now();
  const deadline = t0 + secs * 1000;

  function decode(w) {
    return {
      t: Date.now() - t0,
      seq: w[2],
      posM1: s32(w[14], w[15]) / 1000.0,
      posM2: s32(w[16], w[17]) / 1000.0,
      vcmdM1: s32(w[24], w[25]) / 1000.0,
      vcmdM2: s32(w[26], w[27]) / 1000.0,
      devStop: (w[10] & 1) !== 0 ? 1 : 0,
      devRun: (w[10] & 2) !== 0 ? 1 : 0,
      devError: (w[10] & 4) !== 0 ? 1 : 0,
      faultM1: (w[11] & 256) !== 0 ? 1 : 0,
      faultM2: (w[11] & 512) !== 0 ? 1 : 0,
      moveDone: (w[11] & 64) !== 0 ? 1 : 0,
      ready: (w[11] & 32) !== 0 ? 1 : 0,
    };
  }

  while (Date.now() < deadline) {
    const w = await readBlock(client, base);
    if (w[0] !== MAGIC && w[0] !== MAGIC_SWAP) {
      console.error(`magic lost at t=${Date.now() - t0}ms, w0=${w[0]}`);
      break;
    }
    rows.push(decode(w));
    const next = Date.now() - t0 + ms;
    if (next > 0) await new Promise((res) => setTimeout(res, Math.min(next, ms)));
  }
  try { client.close(() => {}); } catch { /* ignore */ }

  const hdr = 't_ms,posM1_m,posM2_m,dPos_mm,vCmdM1,vCmdM2,devStop,devRun,devError,faultM1,faultM2,moveDone,ready,seq';
  const lines = rows.map((r) =>
    `${r.t},${r.posM1.toFixed(4)},${r.posM2.toFixed(4)},` +
    `${((r.posM1 - r.posM2) * 1000).toFixed(1)},${r.vcmdM1.toFixed(4)},` +
    `${r.vcmdM2.toFixed(4)},${r.devStop},${r.devRun},${r.devError},` +
    `${r.faultM1},${r.faultM2},${r.moveDone},${r.ready},${r.seq}`);
  const csv = hdr + '\n' + lines.join('\n') + '\n';

  fs.writeFileSync('trace-x.csv', csv);
  console.log(csv);
  console.error(`frames=${rows.length} -> trace-x.csv`);
}

main().catch((e) => {
  console.error('trace-x failed:', e.message);
  process.exit(1);
});
