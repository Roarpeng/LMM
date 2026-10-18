'use strict';
/**
 * smoke-step.js — 0.80 外部工步验收：扮演上位机（RK3588），经网关 WebSocket 跑一道完整作业。
 *
 *   node scripts/smoke-step.js                     # 起进程内 mock 网关(:18081)，跑一道，打印每步结果
 *   node scripts/smoke-step.js --hold              # 跑完不退出：浏览器开 http://127.0.0.1:18081/ → 直控页看「外部工步」卡
 *   node scripts/smoke-step.js --fault heartbeat   # X 走距中停发心跳 → 期望 ERR_HEARTBEAT(12)
 *   node scripts/smoke-step.js --fault stop        # X 走距中发停止 → 期望 ERR_SAFETY(11)
 *   node scripts/smoke-step.js --fault busy        # X 走距中插入新命令 → 期望 ERR_BUSY(4)
 *   node scripts/smoke-step.js --fault nocontact   # 地面在行程外 → 压力步期望 ERR_NO_CONTACT(20)
 *   node scripts/smoke-step.js --fault limit       # Y 恒力行程越软限位 → 期望 ERR_LIMIT(3)
 *   node scripts/smoke-step.js --url ws://192.168.1.88:8080 --allow-motion
 *                                                  # 台架：连真网关(→真 PLC 0.80)。会真动轴！先确认急停可用
 *
 * 退出码 0 = 结果符合预期（正常流程全部完成，或注入故障得到期望错误码）。
 */
const WebSocket = require('ws');
const { startGateway } = require('../server.js');

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : dflt;
};
const flag = (name) => args.includes(name);
const fault = opt('--fault', 'none');
const url = opt('--url', null);
const port = Number(opt('--port', 18081));
const EXPECT = { none: 0, heartbeat: 12, stop: 11, busy: 4, nocontact: 20, limit: 3 };
if (!(fault in EXPECT)) {
  console.error(`未知 --fault ${fault}，可选：${Object.keys(EXPECT).join(' / ')}`);
  process.exit(2);
}
if (url && !flag('--allow-motion')) {
  console.error('连接外部网关会真实驱动 PLC 轴运动；确认急停可用后加 --allow-motion');
  process.exit(2);
}

const CMD = ['0 中止', '1 X走距', '2 Z压到力', '3 Y恒力行程', '4 点位'];
const STATE = ['空闲', '执行', '完成', '失败'];
const ERR = { 0: '', 1: '模式', 2: '参数', 3: '越限', 4: '忙', 10: '超时', 11: '安全', 12: '心跳', 20: '未接触' };
const FORCE = { HMI_rStepForce: 80, HMI_rStepKpForce: 0.002, HMI_rStepVelZMax: 0.05 };
const travel = { HMI_wStepFlags: 7, HMI_rStepPosY: 1.9, HMI_rStepPosZ: -0.05, HMI_rStepPosR: 0,
  HMI_rStepVel: 0.2, HMI_rStepVelR: 10 };
const PLAN = [
  ['行进姿态（水槽上方）', 4, travel],
  ['X 走距 0.60+0.02 补偿', 1, { HMI_rStepDist: 0.62, HMI_rStepVel: 0.2 }],
  ['起刷点（R 工作角 5°）', 4, { ...travel, HMI_rStepPosY: 0.2, HMI_rStepPosZ: -0.25, HMI_rStepPosR: 5 }],
  ['Z 压到 80N（去皮）', 2, { ...FORCE, HMI_wStepFlags: 8 }],
  ['Y 恒力拉毛 1.5m', 3, { ...FORCE, HMI_rStepDist: fault === 'limit' ? 9 : 1.5, HMI_rStepVel: 0.3 }],
  ['Z 抬起', 4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.05, HMI_rStepVel: 0.1 }],
  ['清洗：移到水槽', 4, { HMI_wStepFlags: 1, HMI_rStepPosY: 1.95, HMI_rStepVel: 0.3 }],
  ['清洗：下到水里', 4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.2, HMI_rStepVel: 0.1 }],
  ['清洗：提起沥干', 4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.05, HMI_rStepVel: 0.1 }],
  ['回行进姿态', 4, travel],
];
const BLANK = {
  HMI_wStepFlags: 0, HMI_rStepDist: 0, HMI_rStepVel: 0, HMI_rStepVelR: 0, HMI_rStepPosY: 0, HMI_rStepPosZ: 0,
  HMI_rStepPosR: 0, HMI_rStepForce: 0, HMI_rStepKpForce: 0, HMI_rStepVelZMax: 0, HMI_rStepTimeout: 0,
};

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const f = (v, n = 3) => (typeof v === 'number' ? v.toFixed(n) : '—');

(async () => {
  let gateway = null;
  let wsUrl = url;
  if (!wsUrl) {
    const env = { MOCK_PLC: '1', HTTP_PORT: String(port) };
    if (fault === 'nocontact') env.MOCK_GROUND_Z = '-5';
    gateway = startGateway(env);
    await new Promise((resolve) => (gateway.httpServer.listening
      ? resolve() : gateway.httpServer.once('listening', resolve)));
    wsUrl = `ws://127.0.0.1:${gateway.httpServer.address().port}`;
    console.log(`[step] mock 网关 ${wsUrl}  WebHMI: http://127.0.0.1:${gateway.httpServer.address().port}/ (直控页 → 外部工步)`);
  }
  const ws = new WebSocket(wsUrl);
  let S = {};
  const errs = [];
  ws.on('message', (raw) => {
    const m = JSON.parse(String(raw));
    if (m.t === 's') S = m;
    if (m.t === 'err') errs.push(m.code);
  });
  await new Promise((resolve, reject) => { ws.once('open', resolve); ws.once('error', reject); });

  // 上位机周期帧：30ms，心跳 +1，视觉航向 0.005rad/Kp 1，工步块与命令号同帧
  let seq = 0;
  let id = 0;
  let heartbeat = true;
  let block = { HMI_iStepCmd: 0, ...BLANK, HMI_wStepId: 0 };
  const extra = { HMI_xStop: false };
  const frame = () => ({
    t: 'w', HMI_xEStop: true, ...extra, HMI_xStepMode: true,
    HMI_rHeadingErr: 0.005, HMI_rKpTrack: 1, ...block, HMI_wDirectSeq: seq,
  });
  const timer = setInterval(() => {
    if (!heartbeat) return;
    seq = (seq + 1) & 0xffff;
    ws.send(JSON.stringify(frame()));
  }, 30);

  await delay(500);
  if (S.HMI_eOpMode !== 2) {
    console.log(`[step] 未进入外部工步：HMI_eOpMode=${S.HMI_eOpMode}（自动模式开着？急停/停止？）`);
  }
  // 起始命令号接在 PLC 现有回显之后，避免与模式切入时吞掉的号冲突
  id = Number(S.Step_wIdEcho) || 0;

  async function run(name, cmd, params) {
    id = (id + 1) & 0xffff;
    block = { HMI_iStepCmd: cmd, ...BLANK, ...params, HMI_wStepId: id };
    const t0 = Date.now();
    let injected = false;
    for (;;) {
      await delay(20);
      if (cmd === 1 && !injected && Date.now() - t0 > 800) {
        injected = true;
        if (fault === 'heartbeat') heartbeat = false;
        if (fault === 'stop') extra.HMI_xStop = true;
        if (fault === 'busy') {
          id = (id + 1) & 0xffff;
          block = { ...block, HMI_iStepCmd: 4, HMI_wStepFlags: 1, HMI_rStepPosY: 1, HMI_rStepVel: 0.1, HMI_wStepId: id };
        }
      }
      if (S.Step_wIdEcho === id && (S.Step_iState === 2 || S.Step_iState === 3)) break;
      if (Date.now() - t0 > 120000) throw new Error(`${name}: 120s 未结束`);
    }
    await delay(150);
    const x = (Number(S.AxisFb_rPosM1) + Number(S.AxisFb_rPosM2)) / 2;
    console.log(`  #${String(id).padStart(3)} ${CMD[cmd].padEnd(7)} ${name.padEnd(16)} → ${STATE[S.Step_iState]}`
      + `${S.Step_iErr ? ` ERR ${S.Step_iErr}(${ERR[S.Step_iErr] || '?'})` : ''}`
      + `  用时 ${f(S.Step_rElapsed, 1)}s  X ${f(x)} Y ${f(S.AxisFb_rPosY)} Z ${f(S.AxisFb_rPosZ)} R ${f(S.AxisFb_rPosR, 1)}`
      + `  力 ${f(S.HMI_rForceShow, 1)}N  M1−M2 ${f(S.AxisFb_rSyncErr, 4)}`);
    return S;
  }

  console.log(`[step] 一道作业${fault !== 'none' ? `（注入故障：${fault}，期望 ERR ${EXPECT[fault]}）` : ''}`);
  let failErr = 0;
  for (const [name, cmd, params] of PLAN) {
    const st = await run(name, cmd, params);
    if (st.Step_iState === 3) {
      failErr = st.Step_iErr;
      break;
    }
  }
  clearInterval(timer);
  const ok = failErr === EXPECT[fault] && errs.length === 0;
  if (errs.length) console.log(`[step] 网关拒写：${errs.join(', ')}`);
  console.log(ok ? '[step] PASS' : `[step] FAIL（得到 ERR ${failErr}，期望 ${EXPECT[fault]}）`);

  if (flag('--hold')) {
    heartbeat = true;
    block = { ...block, HMI_iStepCmd: 0 };
    setInterval(() => { seq = (seq + 1) & 0xffff; ws.send(JSON.stringify(frame())); }, 30);
    console.log('[step] --hold：保持连接与心跳，Ctrl-C 退出');
    return;
  }
  ws.close();
  if (gateway) gateway.close(() => process.exit(ok ? 0 : 1));
  else process.exit(ok ? 0 : 1);
})().catch((error) => { console.error(error); process.exit(1); });
