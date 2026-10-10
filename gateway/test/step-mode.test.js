'use strict';

// 0.80 外部工步：mock-plc 语义测试（与 plc/g/PRG_Logic.st 工步段同语义）+ 经网关 WebSocket 的契约测试。
const assert = require('node:assert/strict');
const test = require('node:test');
const WebSocket = require('ws');

const { createMockPlc, STEP_ERR } = require('../lib/mock-plc');
const { startGateway } = require('../server');

const DT = 0.02;

// 上位机行为：每个周期心跳 +1，工步块与命令号同一条写入
function createDriver(options) {
  const plc = createMockPlc({}, options);
  let seq = 0;
  let id = 0;
  let heartbeat = true;
  const base = { HMI_xEStop: true, HMI_xStop: false, HMI_xStepMode: true };

  function tick(seconds = DT) {
    const n = Math.max(1, Math.round(seconds / DT));
    for (let i = 0; i < n; i += 1) {
      if (heartbeat) {
        seq = (seq + 1) & 0xffff;
        plc.applyWrite({ ...base, HMI_wDirectSeq: seq });
      }
      plc.tick(DT);
    }
    return plc.statusMessage();
  }

  function send(cmd, params = {}) {
    id = (id + 1) & 0xffff;
    plc.applyWrite({
      HMI_iStepCmd: cmd,
      HMI_wStepFlags: 0,
      HMI_rStepDist: 0,
      HMI_rStepVel: 0,
      HMI_rStepVelR: 0,
      HMI_rStepPosY: 0,
      HMI_rStepPosZ: 0,
      HMI_rStepPosR: 0,
      HMI_rStepForce: 0,
      HMI_rStepKpForce: 0,
      HMI_rStepVelZMax: 0,
      HMI_rStepTimeout: 0,
      ...params,
      HMI_wStepId: id,
    });
    return id;
  }

  // 下发并等到本命令号完成/失败
  function run(cmd, params = {}, limitS = 120) {
    const myId = send(cmd, params);
    let st = plc.statusMessage();
    for (let t = 0; t < limitS; t += DT) {
      st = tick();
      if (st.Step_wIdEcho === myId && (st.Step_iState === 2 || st.Step_iState === 3)) return st;
    }
    throw new Error(`step ${cmd} id=${myId} 未在 ${limitS}s 内结束: ${JSON.stringify(st)}`);
  }

  return {
    plc,
    tick,
    send,
    run,
    write: (fields) => plc.applyWrite(fields),
    setBase: (fields) => Object.assign(base, fields),
    stopHeartbeat: () => { heartbeat = false; },
  };
}

const FORCE = { HMI_rStepForce: 80, HMI_rStepKpForce: 0.002, HMI_rStepVelZMax: 0.05 };
const PTP_YZR = 1 | 2 | 4;

test('进入工步模式：eOpMode=2，吞掉进入前已存在的命令号', () => {
  const d = createDriver();
  d.write({ HMI_xStepMode: false, HMI_iStepCmd: 1, HMI_wStepId: 7, HMI_rStepDist: 1, HMI_rStepVel: 0.2 });
  d.tick();
  const st = d.tick(0.2);
  assert.equal(st.HMI_eOpMode, 2);
  assert.equal(st.Step_xModeActive, true);
  assert.equal(st.Step_wIdEcho, 7);
  assert.equal(st.Step_iState, 0, '旧命令不执行');
  assert.equal(st.AxisFb_rPosM1, 0);
});

test('自动模式优先：HMI_xAutoMode=true 时不进入工步', () => {
  const d = createDriver();
  d.setBase({ HMI_xAutoMode: true });
  const st = d.tick(0.1);
  assert.equal(st.HMI_eOpMode, 1);
  assert.equal(st.Step_xModeActive, false);
});

test('工步1 X 走距：到距完成，航向误差产生 M1/M2 差速', () => {
  const d = createDriver();
  d.tick();
  d.setBase({ HMI_rHeadingErr: 0.01, HMI_rKpTrack: 1 });
  const id = d.send(1, { HMI_rStepDist: 0.6, HMI_rStepVel: 0.2 });
  const mid = d.tick(1);
  assert.equal(mid.Step_iState, 1);
  assert.ok(mid.AxisFb_rVelCmdM1 > mid.AxisFb_rVelCmdM2, '车头偏左为正 → M1 快');
  assert.ok(Math.abs(mid.AxisFb_rVelCmdM1 - mid.AxisFb_rVelCmdM2 - 0.014) < 1e-9, 'trim=(0.01−0.003)×1，双侧 ±');
  let st = mid;
  while (st.Step_iState === 1) st = d.tick();
  assert.equal(st.Step_wIdEcho, id);
  assert.equal(st.Step_iState, 2);
  assert.ok(st.Step_rProgress >= 0.6 && st.Step_rProgress < 0.61);
});

test('工步2 Z 压到力：去皮后下压，力≥F 完成并保持力跟随', () => {
  const d = createDriver({ groundZ: -0.3 });
  d.tick();
  const st = d.run(2, { ...FORCE, HMI_wStepFlags: 8 });
  assert.equal(st.Step_iState, 2, JSON.stringify(st));
  assert.equal(st.Step_xForceReached, true);
  assert.ok(st.HMI_rForceShow >= 79.5, '死区内即判到力');
  assert.ok(st.AxisFb_rPosZ < -0.3);
  const later = d.tick(0.5);
  assert.equal(later.Step_xForceFollow, true, '完成后力跟随保持到下一条命令');
  assert.ok(Math.abs(later.HMI_rForceShow - 80) < 2);
  assert.equal(later.HMI_rForceSetEcho, 80, '回显实际下发的 F');
  assert.equal(later.Step_rKpForceEcho, 0.002);
});

test('工步3 Y 恒力行程：力跟随中横移到位', () => {
  const d = createDriver({ groundZ: -0.3 });
  d.tick();
  d.run(4, { HMI_wStepFlags: 1, HMI_rStepPosY: 0.2, HMI_rStepVel: 0.3 });
  d.run(2, FORCE);
  const st = d.run(3, { ...FORCE, HMI_rStepDist: 1.5, HMI_rStepVel: 0.3 });
  assert.equal(st.Step_iState, 2);
  assert.ok(Math.abs(st.AxisFb_rPosY - 1.7) < 1e-6);
  assert.equal(st.Step_xForceFollow, true);
  assert.equal(st.Step_xForceLow, false);
});

test('工步4 点位：Y/Z/R 同时到位，R 保持目标随之更新', () => {
  const d = createDriver();
  d.tick();
  const st = d.run(4, {
    HMI_wStepFlags: PTP_YZR, HMI_rStepPosY: 0.5, HMI_rStepPosZ: -0.1, HMI_rStepPosR: 12,
    HMI_rStepVel: 0.2, HMI_rStepVelR: 10,
  });
  assert.equal(st.Step_iState, 2);
  assert.ok(Math.abs(st.AxisFb_rPosY - 0.5) < 0.001);
  assert.ok(Math.abs(st.AxisFb_rPosZ + 0.1) < 0.001);
  assert.ok(Math.abs(st.AxisFb_rPosR - 12) < 0.1);
  assert.equal(st.Step_rRHoldPos, 12);
  const x = d.run(1, { HMI_rStepDist: 0.2, HMI_rStepVel: 0.2 });
  assert.equal(x.Step_xRHold, true);
  assert.equal(x.AxisFb_rPosR, 12, 'X 走距期间 R 保持工作角');
});

test('参数非法 → ERR_PARAM；越软限位 → ERR_LIMIT（拒绝，不钳位）', () => {
  const d = createDriver();
  d.tick();
  assert.equal(d.run(1, { HMI_rStepDist: 0.6, HMI_rStepVel: 0 }).Step_iErr, STEP_ERR.PARAM);
  assert.equal(d.run(1, { HMI_rStepDist: 0.6, HMI_rStepVel: 0.9 }).Step_iErr, STEP_ERR.PARAM);
  assert.equal(d.run(2, { ...FORCE, HMI_rStepKpForce: 0 }).Step_iErr, STEP_ERR.PARAM);
  assert.equal(d.run(4, { HMI_wStepFlags: 0, HMI_rStepVel: 0.1 }).Step_iErr, STEP_ERR.PARAM);
  assert.equal(d.run(9).Step_iErr, STEP_ERR.PARAM);
  assert.equal(d.run(4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.8, HMI_rStepVel: 0.1 }).Step_iErr, STEP_ERR.LIMIT);
  assert.equal(d.run(3, { ...FORCE, HMI_rStepDist: 7, HMI_rStepVel: 0.3 }).Step_iErr, STEP_ERR.LIMIT);
  const st = d.tick();
  assert.equal(st.AxisFb_rPosZ, 0, '被拒命令不产生运动');
});

test('执行中来非 0 新命令 → ERR_BUSY 并停当前；命令 0 随时中止', () => {
  const d = createDriver();
  d.tick();
  d.send(1, { HMI_rStepDist: 2, HMI_rStepVel: 0.2 });
  d.tick(0.5);
  const busyId = d.send(4, { HMI_wStepFlags: 1, HMI_rStepPosY: 1, HMI_rStepVel: 0.2 });
  let st = d.tick();
  assert.equal(st.Step_wIdEcho, busyId);
  assert.equal(st.Step_iState, 3);
  assert.equal(st.Step_iErr, STEP_ERR.BUSY);
  const x = st.AxisFb_rPosM1;
  st = d.tick(0.5);
  assert.equal(st.AxisFb_rPosM1, x, '当前 X 走距已停');

  d.send(1, { HMI_rStepDist: 2, HMI_rStepVel: 0.2 });
  d.tick(0.3);
  st = d.run(0);
  assert.equal(st.Step_iState, 2);
  assert.equal(st.Step_iErr, 0);
});

test('心跳 300ms 丢失 → ERR_HEARTBEAT，停止运动', () => {
  const d = createDriver();
  d.tick();
  d.send(1, { HMI_rStepDist: 2, HMI_rStepVel: 0.2 });
  d.tick(0.5);
  d.stopHeartbeat();
  let st = d.tick(0.2);
  assert.equal(st.Step_iState, 1, '300ms 内仍在执行');
  st = d.tick(0.2);
  assert.equal(st.Step_iState, 3);
  assert.equal(st.Step_iErr, STEP_ERR.HEARTBEAT);
  assert.equal(st.Direct2_xOnline, false);
});

test('停止 / 急停 → ERR_SAFETY；退出工步模式 → ERR_MODE', () => {
  const d = createDriver();
  d.tick();
  d.send(1, { HMI_rStepDist: 2, HMI_rStepVel: 0.2 });
  d.tick(0.3);
  d.setBase({ HMI_xStop: true });
  let st = d.tick();
  assert.equal(st.Step_iErr, STEP_ERR.SAFETY);

  d.setBase({ HMI_xStop: false });
  d.tick();
  d.send(1, { HMI_rStepDist: 2, HMI_rStepVel: 0.2 });
  d.tick(0.3);
  d.setBase({ HMI_xStepMode: false });
  st = d.tick();
  assert.equal(st.Step_iState, 3);
  assert.equal(st.Step_iErr, STEP_ERR.MODE);
  assert.equal(st.HMI_eOpMode, 0);
});

test('Z 到下限仍未达力 → ERR_NO_CONTACT；超时 → ERR_TIMEOUT', () => {
  const d = createDriver({ groundZ: -5 }); // 地面在行程外：永远接触不到
  d.tick();
  const st = d.run(2, { ...FORCE, HMI_rStepVelZMax: 0.2 });
  assert.equal(st.Step_iErr, STEP_ERR.NO_CONTACT);
  assert.equal(st.Step_xForceFollow, false);

  const t = d.run(1, { HMI_rStepDist: 2, HMI_rStepVel: 0.1, HMI_rStepTimeout: 1 });
  assert.equal(t.Step_iErr, STEP_ERR.TIMEOUT);
  assert.ok(t.Step_rElapsed > 1 && t.Step_rElapsed < 1.2);
});

test('一道完整作业（行进姿态→走距→起刷→压力→拉毛→抬起→清洗→行进姿态）', () => {
  const d = createDriver({ groundZ: -0.3 });
  d.tick();
  d.setBase({ HMI_rHeadingErr: 0.005, HMI_rKpTrack: 1 });
  // Y·Z 同时点位共用 HMI_rStepVel，受 Y/Z 上限较小者（Z 0.2 m/s）约束
  const travel = { HMI_wStepFlags: PTP_YZR, HMI_rStepPosY: 1.9, HMI_rStepPosZ: -0.05, HMI_rStepPosR: 0,
    HMI_rStepVel: 0.2, HMI_rStepVelR: 10 };
  const plan = [
    [4, travel],
    [1, { HMI_rStepDist: 0.6 + 0.02, HMI_rStepVel: 0.2 }],
    [4, { ...travel, HMI_rStepPosY: 0.2, HMI_rStepPosZ: -0.25, HMI_rStepPosR: 5 }],
    [2, { ...FORCE, HMI_wStepFlags: 8 }],
    [3, { ...FORCE, HMI_rStepDist: 1.5, HMI_rStepVel: 0.3 }],
    [4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.05, HMI_rStepVel: 0.1 }],
    [4, { HMI_wStepFlags: 1, HMI_rStepPosY: 1.95, HMI_rStepVel: 0.3 }],
    [4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.2, HMI_rStepVel: 0.1 }],
    [4, { HMI_wStepFlags: 2, HMI_rStepPosZ: -0.05, HMI_rStepVel: 0.1 }],
    [4, travel],
  ];
  for (const [cmd, params] of plan) {
    const st = d.run(cmd, params);
    assert.equal(st.Step_iState, 2, `cmd ${cmd} 失败 err=${st.Step_iErr}`);
  }
  const st = d.tick();
  assert.ok(Math.abs((st.AxisFb_rPosM1 + st.AxisFb_rPosM2) / 2 - 0.62) < 0.01);
  assert.ok(st.AxisFb_rSyncErr > 0, '航向纠偏使 M1 多走');
  assert.equal(st.Step_xForceFollow, false, '抬起后力跟随结束');
});

// ---- 经网关：字段在契约内（无 INVALID_WRITE），断开即 fail-safe 退出工步 ----
function connect(port) {
  const ws = new WebSocket(`ws://127.0.0.1:${port}`);
  const messages = [];
  ws.on('message', (raw) => messages.push(JSON.parse(String(raw))));
  return new Promise((resolve, reject) => {
    ws.once('open', () => resolve({ ws, messages }));
    ws.once('error', reject);
  });
}
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('网关 mock：工步字段被接受并执行；写者断开 → fail-safe 退出工步', async () => {
  const gateway = startGateway({ MOCK_PLC: '1', HTTP_PORT: '0', MODBUS_PORT: '0' });
  try {
    await new Promise((resolve) => (gateway.httpServer.listening
      ? resolve() : gateway.httpServer.once('listening', resolve)));
    const { port } = gateway.httpServer.address();
    const { ws, messages } = await connect(port);
    let seq = 0;
    const timer = setInterval(() => {
      seq += 1;
      ws.send(JSON.stringify({ t: 'w', HMI_xEStop: true, HMI_xStop: false, HMI_xStepMode: true, HMI_wDirectSeq: seq }));
    }, 30);
    await delay(400);
    ws.send(JSON.stringify({
      t: 'w', HMI_xEStop: true, HMI_xStop: false, HMI_xStepMode: true, HMI_wDirectSeq: ++seq,
      HMI_iStepCmd: 1, HMI_wStepId: 1, HMI_rStepDist: 0.1, HMI_rStepVel: 0.2,
      HMI_rStepKpForce: 0.002, HMI_rStepTimeout: 30,
    }));
    const deadline = Date.now() + 5000;
    let done = null;
    while (!done && Date.now() < deadline) {
      done = messages.find((m) => m.t === 's' && m.Step_wIdEcho === 1 && m.Step_iState === 2);
      await delay(50);
    }
    clearInterval(timer);
    assert.deepEqual(messages.filter((m) => m.t === 'err'), []);
    assert.ok(done, '工步1 经网关完成');
    assert.equal(done.HMI_eOpMode, 2);

    ws.close();
    await delay(400);
    const last = [...messages].reverse().find((m) => m.t === 's');
    const { ws: viewer, messages: seen } = await connect(port);
    await delay(300);
    const now = [...seen].reverse().find((m) => m.t === 's');
    viewer.close();
    assert.ok(last);
    assert.equal(now.Step_xModeActive, false, '写者断开 → HMI_xStepMode 回 fail-safe=false');
  } finally {
    await new Promise((resolve) => gateway.close(resolve));
  }
});
