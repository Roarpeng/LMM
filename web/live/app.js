/* LMM WebHMI v3 - app (HMI store + WebSocket mirror + 9-page render) */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const STEP_NAME = ['Idle', 'MoveX', 'Y->0', 'PressZ', 'MoveY+F', 'Multi', 'Done'];
  const ALARMS = {
    0: { name: '无报警', fix: '设备正常。' },
    1001: { name: '急停', fix: '松开物理急停按钮，然后按「复位设备」解除锁存。' },
    1002: { name: '电机故障', fix: '检查驱动器报警，排除后按「复位」。' },
    1003: { name: '限位', fix: '反向点动退出限位。' },
    1005: { name: '力通讯超时', fix: '检查力传感器 485 接线/供电与从站使能。' },
    1006: { name: '力从站使能失败', fix: '检查站号/波特率/供电，复位后重试。' },
    1007: { name: '使能未就绪', fix: '检查各轴驱动器就绪与使能。' },
    1008: { name: '同步跳闸(已废)', fix: 'X 双驱已取消同步跳闸。' },
  };
  const CMD_LABELS = {
    HMI_xEStop: '急停请求', HMI_xStop: '停止', HMI_xStopHold3s: '复位', HMI_xStart: '启动', HMI_xEnable: '启动别名',
    HMI_xAutoMode: '自动模式', HMI_xJogXPos: 'X+', HMI_xJogXNeg: 'X-', HMI_xSpinLeft: '左旋', HMI_xSpinRight: '右旋',
    HMI_xJogYPos: 'Y+', HMI_xJogYNeg: 'Y-', HMI_xJogZPos: 'Z+', HMI_xJogZNeg: 'Z-', HMI_xJogRPos: 'R+', HMI_xJogRNeg: 'R-',
    HMI_xHomeY: 'Y回零', HMI_xHomeZ: 'Z回零', HMI_xHomeR: 'R回零', HMI_xHomeExec: '回零执行',
    HMI_xAutoStart: '自动启动', HMI_xAutoAbort: '自动中止',
    HMI_xForceSimEnable: '力模拟', HMI_xForceTare: '去皮', HMI_xForceUntare: '取消去皮', HMI_xForceGuide: '力引导',
    HMI_iHomeAxis: '回零轴', HMI_iAutoPasses: '道数',
    HMI_rJogVelX: 'X直行速度', HMI_rSpinVel: '旋转速度', HMI_rJogVelY: 'Y点动速度', HMI_rJogVelZ: 'Z点动速度', HMI_rJogVelR: 'R点动速度',
    HMI_rAutoDistX: '自动X走距', HMI_rAutoVelX: '自动X速度', HMI_rAutoVelY: '自动Y速度', HMI_rAutoVelZ: '自动Z速度',
    HMI_rWheelBase: '跨距', HMI_rForceSet: '恒力设定', HMI_rForceSim: '力模拟值', HMI_rHeadingErr: '航向误差',
    HMI_rKpTrack: '纠偏Kp', HMI_rKpForce: '力Kp',
    HMI_rAccX: 'X加速度', HMI_rDecX: 'X减速度', HMI_rAccY: 'Y加速度', HMI_rDecY: 'Y减速度',
    HMI_rAccZ: 'Z加速度', HMI_rDecZ: 'Z减速度', HMI_rAccR: 'R加速度', HMI_rDecR: 'R减速度',
    HMI_xDirectEnable: '直控使能', HMI_rVelM1Set: '直控M1给定', HMI_rVelM2Set: '直控M2给定',
    HMI_wDirectSeq: '直控心跳序号', HMI_iDirectModeX: '直控X模式', HMI_rDirectPosX: '直控X整机目标',
    HMI_iDirectModeY: '直控Y模式', HMI_rDirectVelY: '直控Y速度', HMI_rDirectPosY: '直控Y目标',
    HMI_iDirectModeZ: '直控Z模式', HMI_rDirectVelZ: '直控Z速度', HMI_rDirectPosZ: '直控Z目标',
    HMI_iDirectModeR: '直控R模式', HMI_rDirectVelR: '直控R速度', HMI_rDirectPosR: '直控R目标',
  };
  const STATUS_LABELS = {
    Tcp_iCommStatus: '通讯诊断', HMI_eDevState: '设备态', HMI_eOpMode: '运行方式', HMI_iAlarmShow: '报警号',
    HMI_iAutoStepShow: '自动步号', HMI_xDevStop: '停止灯', HMI_xDevRun: '运行灯', HMI_xDevError: '故障灯',
    HMI_xLampEStop: '急停灯', HMI_xLampEnableOk: '就绪灯', HMI_xLampFault: '故障指示',
    HMI_xAutoBusy: '自动忙', HMI_xAutoDone: '自动完成',
    HMI_xHomedY: 'Y已回零', HMI_xHomedZ: 'Z已回零', HMI_xHomedR: 'R已回零',
    HMI_xHomeBusyY: 'Y回零中', HMI_xHomeBusyZ: 'Z回零中', HMI_xHomeBusyR: 'R回零中',
    Tcp_xConnected: '远程连接', Tcp_xTimeout: '远程超时',
    Force_xCommOk: '力通讯', Force_xTimeout: '力超时', Force_xSlaveFail: '力从站失败', Force_xTareBusy: '去皮中', Force_xTareDone: '去皮完成',
    AxisFb_xReady: '全轴就绪', AxisFb_xMoveDoneX: 'X走距完成', AxisFb_xMoveDoneY: 'Y完成',
    AxisFb_xFaultM1: 'M1故障', AxisFb_xFaultM2: 'M2故障', AxisFb_xFaultY: 'Y故障', AxisFb_xFaultZ: 'Z故障', AxisFb_xFaultR: 'R故障',
    AxisFb_xHomedY: 'Y回零(轴)', AxisFb_xHomedZ: 'Z回零(轴)', AxisFb_xHomedR: 'R回零(轴)', HMI_rForceShow: '力显示',
    AxisFb_rPosM1: 'M1位置', AxisFb_rPosM2: 'M2位置', AxisFb_rPosY: 'Y位置', AxisFb_rPosZ: 'Z位置', AxisFb_rPosR: 'R位置',
    AxisFb_rVelCmdM1: 'M1速度指令', AxisFb_rVelCmdM2: 'M2速度指令', AxisFb_rVelActM1: 'M1实际速度', AxisFb_rVelActM2: 'M2实际速度',
    AxisFb_xMovingM1: 'M1运动中', AxisFb_xMovingM2: 'M2运动中', AxisFb_xPoweredM1: 'M1使能', AxisFb_xPoweredM2: 'M2使能',
    AxisFb_xSyncWarn: 'X同步预警', AxisFb_xSyncFault: 'X同步故障', AxisFb_rSyncErr: 'X同步误差',
    Direct_xActive: '直控在役', Direct_xOnline: '视觉在线', Direct_xEnable: '直控使能', Direct_rVelM1Act: '直控M1实际速度', Direct_rVelM2Act: '直控M2实际速度', Direct_wSeqEcho: '视觉序号回显',
    AxisFb_rVelActY: 'Y实际速度', AxisFb_rVelActZ: 'Z实际速度', AxisFb_rVelActR: 'R实际速度',
    Direct2_xActiveX: '直控X在役', Direct2_xActiveY: '直控Y在役', Direct2_xActiveZ: '直控Z在役', Direct2_xActiveR: '直控R在役',
    Direct2_xOnline: '直控心跳在线', Direct2_xSafe: '直控安全允许', Direct2_wSeqEcho: '直控心跳回显', HMI_rForceSetEcho: '力设定回显',
    Vis_xEnable: '视觉使能', Vis_wSeq: '视觉序号', Vis_rVelM1Set: '视觉M1给定', Vis_rVelM2Set: '视觉M2给定',
  };
  const W = {
    HMI_xEStop: true, HMI_xStop: false, HMI_xStopHold3s: false, HMI_xStart: false, HMI_xEnable: false, HMI_xAutoMode: false,
    HMI_xJogXPos: false, HMI_xJogXNeg: false, HMI_xSpinLeft: false, HMI_xSpinRight: false,
    HMI_xJogYPos: false, HMI_xJogYNeg: false, HMI_xJogZPos: false, HMI_xJogZNeg: false, HMI_xJogRPos: false, HMI_xJogRNeg: false,
    HMI_xHomeY: false, HMI_xHomeZ: false, HMI_xHomeR: false, HMI_xHomeExec: false, HMI_xAutoStart: false, HMI_xAutoAbort: false,
    HMI_xForceSimEnable: false, HMI_xForceTare: false, HMI_xForceUntare: false, HMI_xForceGuide: false,
    HMI_iHomeAxis: 1, HMI_iAutoPasses: 1,
    HMI_rJogVelX: 0.4, HMI_rSpinVel: 0.3, HMI_rJogVelY: 0.3, HMI_rJogVelZ: 0.2, HMI_rJogVelR: 0.2,
    HMI_rAutoDistX: 1.0, HMI_rAutoVelX: 0.4, HMI_rAutoVelY: 0.3, HMI_rAutoVelZ: 0.15,
    HMI_rWheelBase: 5.0, HMI_rForceSet: 100, HMI_rForceSim: 0, HMI_rHeadingErr: 0.0, HMI_rKpTrack: 0.0, HMI_rKpForce: 1.0,
    HMI_rAccX: 100, HMI_rDecX: 100, HMI_rAccY: 100, HMI_rDecY: 100, HMI_rAccZ: 100, HMI_rDecZ: 100, HMI_rAccR: 100, HMI_rDecR: 100,
    HMI_xDirectEnable: false, HMI_rVelM1Set: 0, HMI_rVelM2Set: 0,
    HMI_wDirectSeq: 0, HMI_iDirectModeX: 0, HMI_rDirectPosX: 0, HMI_iDirectModeY: 0, HMI_rDirectVelY: 0, HMI_rDirectPosY: 0,
    HMI_iDirectModeZ: 0, HMI_rDirectVelZ: 0, HMI_rDirectPosZ: 0, HMI_iDirectModeR: 0, HMI_rDirectVelR: 0, HMI_rDirectPosR: 0,
  };
  const S = {};
  const ACT = { 'x+': 'HMI_xJogXPos', 'x-': 'HMI_xJogXNeg', spinL: 'HMI_xSpinLeft', spinR: 'HMI_xSpinRight',
    'y+': 'HMI_xJogYPos', 'y-': 'HMI_xJogYNeg', 'z+': 'HMI_xJogZPos', 'z-': 'HMI_xJogZNeg', 'r+': 'HMI_xJogRPos', 'r-': 'HMI_xJogRNeg' };
  const KEYMAP = { KeyW: 'x+', KeyS: 'x-', KeyA: 'y-', KeyD: 'y+', KeyQ: 'z+', KeyE: 'z-', KeyZ: 'r+', KeyC: 'r-', KeyX: 'spinL', KeyV: 'spinR' };
  let ws = null, seq = 0, dirty = false, lastSend = 0, activePage = 'overview';
  let controlClaimed = false;
  let clientId = null, leaseOwner = null, lastAckAt = 0, lastWriteLog = 0, lastPingAt = 0, rtt = null;
  let gwHealth = null, healthAt = 0, MAP = null, rafPending = false, lastTrend = 0, lastAutoSnap = 0, lastHistAt = 0;
  const regCells = {}; const logs = []; const SC = {};
  const HIST = { t: [], vel1: [], vel2: [], act1: [], act2: [], p1: [], p2: [], force: [] };
  const HIST_MAX = 3000; let winSamples = 300;
  const alarmHist = []; let lastAlarm = 0; let overlayHidden = false;
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const fmt = (v, d) => { if (typeof v === 'boolean') return v ? 'T' : 'F'; const n = Number(v); return Number.isFinite(n) ? n.toFixed(d == null ? 3 : d) : '—'; };
  const setText = (id, v) => { const el = $(id); if (!el) return; const s = String(v); if (el.textContent !== s) el.textContent = s; };
  function setChip(id, cls, text) { const el = $(id); if (!el) return; el.className = 'chip ' + (cls || ''); const b = el.querySelector('b'); if (b && text != null) b.textContent = text; else if (text != null && !b) { /* keep */ } }
  function scaleUpd(k, v) { const s = SC[k] || (SC[k] = { lo: v, hi: v }); if (v < s.lo) s.lo = v; if (v > s.hi) s.hi = v; if (s.hi - s.lo < 1e-4) s.hi = s.lo + 1e-4; }
  function scaleN(k, v) { const s = SC[k]; if (!s) return 0.5; return Math.max(0, Math.min(1, (v - s.lo) / (s.hi - s.lo))); }

  function log(msg, kind) {
    logs.push({ at: Date.now(), kind: kind || 'info', msg });
    const el = $('log');
    if (el) { const d = document.createElement('div'); d.textContent = new Date().toLocaleTimeString() + '  ' + msg; if (kind === 'err') d.style.color = 'var(--alarm)'; if (kind === 'warn') d.style.color = 'var(--warn)'; el.prepend(d); while (el.children.length > 400) el.removeChild(el.lastChild); }
    if (kind === 'err') { const box = $('toast'); if (box) { const d = document.createElement('div'); d.textContent = msg; box.appendChild(d); setTimeout(() => { if (d.parentNode) d.parentNode.removeChild(d); }, 4000); } }
  }

  function flush(force) {
    const now = Date.now();
    if (!controlClaimed || !dirty) return;
    if (!force && now - lastSend < 50) return;
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify(Object.assign({ t: 'w', seq: ++seq }, W)));
    lastSend = now; dirty = false;
    if (now - lastWriteLog > 1000) { lastWriteLog = now; log('-> 写入网关 seq=' + seq); }
  }
  function patch(partial, userInitiated) {
    Object.assign(W, partial);
    if (userInitiated !== false) controlClaimed = true;
    if (!controlClaimed) return;
    dirty = true; flush(true);
  }
  function pulse(partial, ms) { patch(partial); setTimeout(() => patch(partial, false), ms || 130); }
  const HMI = {
    state: S, cmd: W,
    patch: (o) => patch(o),
    pulse: (o, ms) => pulse(o, ms),
    jog: (act, on) => { const k = ACT[act]; if (k) { const o = {}; o[k] = on; patch(o); } },
    setParam: (k, v) => { const o = {}; o[k] = v; patch(o); },
  };
  window.HMI = HMI;

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(proto + '://' + location.host);
    ws.onopen = () => { setConn(true); log('WS open'); ws.send(JSON.stringify({ t: 'ping' })); };
    ws.onclose = () => {
      controlClaimed = false; dirty = false; leaseOwner = null; setConn(false); log('WS closed - retry 2s', 'warn');
      Object.keys(ACT).forEach((k) => { W[ACT[k]] = false; });
      W.HMI_xStart = false; W.HMI_xEnable = false; W.HMI_xAutoStart = false; W.HMI_xStop = false; W.HMI_xEStop = true; W.HMI_xForceGuide = false; W.HMI_xDirectEnable = false;
      setTimeout(connect, 2000);
    };
    ws.onerror = () => log('WS error', 'err');
    ws.onmessage = (ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.t === 'pong') { applyPong(msg); return; }
      if (msg.t === 'hello') { clientId = msg.clientId; if (msg.mode) S._gateway = msg.mode; return; }
      if (msg.t === 'lease') { leaseOwner = msg.owner; return; }
      if (msg.t === 'wack') { lastAckAt = Date.now(); return; }
      if (msg.t === 'err') { log('err ' + (msg.msg || msg.code), 'err'); return; }
      if (msg.t === 's' || msg.HMI_eDevState !== undefined) ingestStatus(msg);
    };
  }
  function applyPong(msg) { rtt = typeof msg.rtt === 'number' ? msg.rtt : (lastPingAt ? Date.now() - lastPingAt : rtt); }
  function bindParam(rangeId, numId, key, digits, onUser) {
    const r = $(rangeId), n = $(numId);
    if (!r || !n) return;
    const apply = (v, user) => {
      const x = Number(v); if (!Number.isFinite(x)) return;
      W[key] = x; r.value = String(x); n.value = digits === 0 ? String(Math.round(x)) : x.toFixed(digits);
      if (user) { controlClaimed = true; dirty = true; flush(false); }
      if (onUser) onUser(x);
    };
    r.addEventListener('input', () => apply(r.value, true));
    n.addEventListener('change', () => apply(n.value, true));
    apply(r.value, false);
  }
  function setCheckbox(id, key) { const el = $(id); if (!el) return; el.addEventListener('change', () => { const o = {}; o[key] = el.checked; patch(o); }); }
  function on(id, ev, fn) { const el = $(id); if (el) el.addEventListener(ev, fn); }
  function switchPage(name) {
    activePage = name;
    document.querySelectorAll('#nav button').forEach((b) => b.classList.toggle('active', b.dataset.page === name));
    document.querySelectorAll('.page').forEach((p) => p.classList.toggle('active', p.id === 'page-' + name));
  }
  document.querySelectorAll('#nav button').forEach((b) => b.addEventListener('click', () => { switchPage(b.dataset.page); if (b.dataset.page === 'system' || b.dataset.page === 'debug') pollHealth(); }));
  document.querySelectorAll('input[name=opmode]').forEach((r) => r.addEventListener('change', () => patch({ HMI_xAutoMode: r.value === '1' })));
  document.querySelectorAll('input[name=home-axis]').forEach((r) => r.addEventListener('change', () => patch({ HMI_iHomeAxis: Number(r.value) })));
  function hold(btn, key, onv) { btn.classList.toggle('active', onv); const o = {}; o[key] = onv; patch(o); }
  function bindHold(btn) { const act = btn.dataset.act, key = ACT[act]; if (!key) return;
    const down = (e) => { e.preventDefault(); if (btn.disabled) return; hold(btn, key, true); };
    const up = (e) => { e.preventDefault(); hold(btn, key, false); };
    btn.addEventListener('pointerdown', down); btn.addEventListener('pointerup', up); btn.addEventListener('pointerleave', up); btn.addEventListener('pointercancel', up); }
  function typing(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT'); }
  window.addEventListener('keydown', (e) => { if (typing(e) || e.repeat) return;
    if (e.code === 'Space') { e.preventDefault(); patch({ HMI_xStop: true }); return; }
    const act = KEYMAP[e.code]; if (!act) return; e.preventDefault(); const b = document.querySelector('.hold[data-act="' + act + '"]'); if (b && !b.disabled) hold(b, ACT[act], true); });
  window.addEventListener('keyup', (e) => { if (typing(e)) return;
    if (e.code === 'Space') { patch({ HMI_xStop: false }, false); return; }
    const act = KEYMAP[e.code]; if (!act) return; const b = document.querySelector('.hold[data-act="' + act + '"]'); if (b) hold(b, ACT[act], false); });

  function setConn(ok) {
    S.connected = ok;
    setChip('dev-status', ok ? 'off' : 'alarm', ok ? undefined : 'OFFLINE');
    document.querySelectorAll('.hold, #btn-auto-start').forEach((el) => { el.disabled = !ok; });
  }
  function ingestStatus(msg) {
    if (msg._gateway) S._gateway = msg._gateway;
    for (const k in msg) { if (k !== 't' && k !== '_gateway') S[k] = msg[k]; }
    S.HMI_xDevStop = !!msg.HMI_xDevStop; S.HMI_xDevRun = !!msg.HMI_xDevRun; S.HMI_xDevError = !!msg.HMI_xDevError;
    S.__rxWall = Date.now();
    const avg = (num(S.AxisFb_rPosM1) + num(S.AxisFb_rPosM2)) * 0.5;
    scaleUpd('x', avg); scaleUpd('y', num(S.AxisFb_rPosY)); scaleUpd('z', num(S.AxisFb_rPosZ)); scaleUpd('r', num(S.AxisFb_rPosR));
    pushHistory(); schedule();
  }
  function pushHistory() {
    const now = performance.now();
    if (now - lastHistAt < 90) return; lastHistAt = now;
    HIST.t.push(now);
    HIST.vel1.push(num(S.AxisFb_rVelCmdM1)); HIST.vel2.push(num(S.AxisFb_rVelCmdM2));
    HIST.act1.push(num(S.AxisFb_rVelActM1)); HIST.act2.push(num(S.AxisFb_rVelActM2));
    HIST.p1.push(num(S.AxisFb_rPosM1)); HIST.p2.push(num(S.AxisFb_rPosM2));
    HIST.force.push(num(S.HMI_rForceShow));
    const keys = ['t', 'vel1', 'vel2', 'act1', 'act2', 'p1', 'p2', 'force'];
    if (HIST.t.length > HIST_MAX) keys.forEach((k) => HIST[k].shift());
    const as = $('auto-snap');
    if (as && as.checked) { const moving = W.HMI_xJogXPos || W.HMI_xJogXNeg || W.HMI_xSpinLeft || W.HMI_xSpinRight; if (moving && Date.now() - lastAutoSnap > 500) { lastAutoSnap = Date.now(); snapshot('AUTO'); } }
  }
  function schedule() { if (rafPending) return; rafPending = true; requestAnimationFrame(() => { rafPending = false; render(); }); }

  function statusSemantics() {
    const online = !!S.connected && (S.Tcp_iCommStatus === 2 || S.Tcp_iCommStatus === 1 || (!gwHealth && !S.Tcp_xTimeout));
    const estop = !!S.HMI_xLampEStop || num(S.HMI_iAlarmShow) === 1001;
    const alarm = num(S.HMI_iAlarmShow) !== 0;
    if (!S.connected) return { cls: 'off', text: 'OFFLINE' };
    if (!online) return { cls: 'alarm', text: 'OFFLINE' };
    if (estop) return { cls: 'alarm', text: 'ESTOP' };
    if (S.HMI_xDevError) return { cls: 'alarm', text: 'FAULT' };
    if (alarm) return { cls: 'warn', text: 'ALARM ' + num(S.HMI_iAlarmShow) };
    if (S.HMI_xDevRun) return { cls: 'run', text: 'RUNNING' };
    if (S.AxisFb_xReady) return { cls: 'ok', text: 'READY' };
    return { cls: 'warn', text: 'WAIT' };
  }

  function render() {
    const sem = statusSemantics();
    setChip('dev-status', sem.cls, sem.text);
    const master = gwHealth && gwHealth.master;
    const plcOk = master ? (master.connected && !gwHealth.statusIsOffline) : (S.Tcp_iCommStatus !== undefined && !S.Tcp_xTimeout);
    setChip('plc-chip', plcOk ? 'ok' : 'alarm', 'PLC');
    document.querySelectorAll('input[name=opmode]').forEach((r) => { r.checked = (r.value === '1') === !!S.HMI_eOpMode; });

    const avg = (num(S.AxisFb_rPosM1) + num(S.AxisFb_rPosM2)) * 0.5;
    const dpos = num(S.AxisFb_rSyncErr != null ? S.AxisFb_rSyncErr : (num(S.AxisFb_rPosM1) - num(S.AxisFb_rPosM2)));
    const dvel = num(S.AxisFb_rVelActM1) - num(S.AxisFb_rVelActM2);
    const step = num(S.HMI_iAutoStepShow);
    const alarm = num(S.HMI_iAlarmShow);

    // overview
    setText('ov-state', sem.text);
    const sub = sem.cls === 'run' ? '自动运行中' : sem.cls === 'alarm' ? ((ALARMS[alarm] || {}).name || '报警') : sem.cls === 'ok' ? '就绪，可操作' : '等待…';
    setText('ov-sub', sub);
    setText('ov-task', alarm ? ('报警 ' + alarm) : (S.HMI_xAutoBusy ? ('步 ' + step + ' · ' + (STEP_NAME[step] || '')) : '待机'));
    setText('ov-x', fmt(avg, 3) + ' m'); setText('ov-y', fmt(S.AxisFb_rPosY, 3) + ' m');
    setText('ov-z', fmt(S.AxisFb_rPosZ, 3) + ' m'); setText('ov-r', fmt(S.AxisFb_rPosR, 1) + ' °');
    setText('ov-alarm', alarm ? ('当前报警 ' + alarm) : '无报警');
    renderMachine(avg, num(S.AxisFb_rPosY), num(S.AxisFb_rPosZ), num(S.AxisFb_rPosR), dpos);

    // auto
    setChip('auto-chip', S.HMI_xAutoBusy ? 'run' : (S.HMI_xAutoDone ? 'ok' : ''), S.HMI_xAutoBusy ? '运行中' : (S.HMI_xAutoDone ? '完成' : '待机'));
    document.querySelectorAll('#steps .s').forEach((el) => { const n = Number(el.dataset.s); el.classList.toggle('on', n === step); el.classList.toggle('dn', n < step && step > 0); });
    setText('p-step', 'Step ' + step + ' ' + (STEP_NAME[step] || ''));
    const pbusy = $('p-busy'); if (pbusy) { pbusy.className = 'chip ' + (S.HMI_xAutoBusy ? 'run' : ''); }
    const pdone = $('p-done'); if (pdone) { pdone.className = 'chip ' + (S.HMI_xAutoDone ? 'ok' : ''); }
    const pr = $('auto-progress'); if (pr) pr.style.width = Math.max(0, Math.min(100, (step / 5) * 100)) + '%';
    setText('q-passes', W.HMI_iAutoPasses); setText('q-dx', fmt(W.HMI_rAutoDistX, 2) + ' m');
    setText('q-base', fmt(W.HMI_rWheelBase, 1) + ' m'); setText('q-fset', (num(W.HMI_rForceSet) || 0) + ' N');

    // manual
    setChip('manual-chip', S.HMI_eOpMode ? 'warn' : 'run', S.HMI_eOpMode ? '自动模式' : '手动模式');
    ['y', 'z', 'r'].forEach((a) => { const on = !!S['HMI_xHomed' + a.toUpperCase()]; const el = $('p-homed-' + a); if (el) el.className = 'chip ' + (on ? 'ok' : ''); });
    setText('out-ready', S.AxisFb_xReady ? 'T' : 'F');
    setText('out-done', 'X=' + (S.AxisFb_xMoveDoneX ? 'T' : 'F') + ' Y=' + (S.AxisFb_xMoveDoneY ? 'T' : 'F'));
    const faults = ['M1', 'M2', 'Y', 'Z', 'R'].filter((a) => S['AxisFb_xFault' + a]).join(' ') || '无';
    setText('faults', faults);

    // xdual
    setChip('xdual-chip', (S.AxisFb_xSyncFault ? 'alarm' : (S.AxisFb_xSyncWarn ? 'warn' : 'ok')), S.AxisFb_xSyncFault ? 'SYNC FAULT' : (S.AxisFb_xSyncWarn ? 'SYNC WARN' : 'SYNC OK'));
    setText('m1-act', fmt(S.AxisFb_rVelActM1, 3)); setText('m2-act', fmt(S.AxisFb_rVelActM2, 3));
    setText('m1-cmd', fmt(S.AxisFb_rVelCmdM1, 3)); setText('m2-cmd', fmt(S.AxisFb_rVelCmdM2, 3));
    setText('dvel2', fmt(dvel, 4)); setText('dpos2', fmt(dpos, 4));
    setText('m1-pos', fmt(S.AxisFb_rPosM1, 4)); setText('m2-pos', fmt(S.AxisFb_rPosM2, 4));
    const dm1 = $('dm1'); if (dm1) dm1.className = 'chip ' + (S.AxisFb_xMovingM1 ? 'run' : ''); const dm2 = $('dm2'); if (dm2) dm2.className = 'chip ' + (S.AxisFb_xMovingM2 ? 'run' : '');
    const sw = $('sync-warn'); if (sw) sw.className = 'chip ' + (S.AxisFb_xSyncWarn ? 'warn' : ''); const sf = $('sync-fault'); if (sf) sf.className = 'chip ' + (S.AxisFb_xSyncFault ? 'alarm' : '');
    const da = $('d-active'); if (da) da.className = 'chip ' + (S.Direct_xActive ? 'run' : ''); const doln = $('d-online'); if (doln) doln.className = 'chip ' + (S.Direct_xOnline ? 'ok' : '');
    setText('d-act-m1', 'M1 ' + fmt(S.Direct_rVelM1Act, 3)); setText('d-act-m2', 'M2 ' + fmt(S.Direct_rVelM2Act, 3));

    // force
    const fok = S.Force_xCommOk && !S.Force_xTimeout && !S.Force_xSlaveFail;
    setChip('force-chip', fok ? 'ok' : 'alarm', fok ? '通讯正常' : (S.Force_xSlaveFail ? '从站失败' : (S.Force_xTimeout ? '超时' : '—')));
    setText('out-force', fmt(S.HMI_rForceShow, 1) + ' N');
    const fg = $('fg-fill'); if (fg) fg.style.height = Math.max(0, Math.min(100, (num(S.HMI_rForceShow) / (num(W.HMI_rForceSet) || 1)) * 100)) + '%';
    const fs = $('fg-set'); if (fs) fs.style.bottom = 'calc(100% - 2px)';
    setText('p-force-diag', 'Comm=' + (S.Force_xCommOk ? 'OK' : '—') + (S.Force_xTimeout ? ' TO' : '') + (S.Force_xSlaveFail ? ' SlaveFail' : ''));
    setText('p-tare', S.Force_xTareBusy ? 'Busy' : (S.Force_xTareDone ? 'Done' : '—'));

    // alarm page
    renderAlarms(alarm);
    // debug diagnostics
    setText('sys-plc', plcOk ? 'TRUE' : 'FALSE');
    setText('sys-age', S.__rxWall ? (Date.now() - S.__rxWall) + ' ms' : '—');
    setText('sys-poll', master ? (master.pollMs + ' ms') : '—');
    setText('sys-rtt', rtt == null ? '—' : rtt + ' ms');
    setText('sys-err', master ? String(master.errorCount || 0) : '—');
    // system page
    setChip('sys-chip', plcOk ? 'ok' : 'off', plcOk ? 'OK' : 'OFFLINE');
    setText('sys-ws', S.connected ? 'CONNECTED' : 'DOWN');
    setText('sys-gw', master ? (master.connected ? 'CONNECTED' : 'DOWN') : '—');
    setText('sys-host', master ? (master.host + ':' + master.port) : '—');
    setText('sys-mode', (gwHealth && gwHealth.mode) || S._gateway || '—');
    setText('sys-lease', leaseOwner == null ? (controlClaimed ? '本页' : '空闲') : (leaseOwner === clientId ? '本页' : '其他 #' + leaseOwner));
    setText('sys-rtt2', rtt == null ? '—' : rtt + ' ms');
    setText('sys-hb', S.__rxWall ? (Date.now() - S.__rxWall) + ' ms' : '—');
    setText('sys-ack', lastAckAt ? new Date(lastAckAt).toLocaleTimeString() : '—');
    setText('sys-version', 'v3');

    renderDirect(); renderTrends(); refreshRegCells();
    if ($('health-age') && healthAt) setText('health-age', (Date.now() - healthAt) + 'ms');
  }
  function renderMachine(avg, y, z, r, dpos) {
    const nx = scaleN('x', avg), ny = scaleN('y', y), nz = scaleN('z', z);
    const beam = $('gm-beam'); if (beam) beam.setAttribute('transform', 'translate(' + (24 + nx * 420) + ',0)');
    const skew = Math.max(-1, Math.min(1, dpos / 0.02)) * 5;
    const b1 = $('gm-m1'), b2 = $('gm-m2'); if (b1) b1.setAttribute('y', String(28 + skew)); if (b2) b2.setAttribute('y', String(28 - skew));
    const yx = ny * 350;
    const gy = $('gm-y'); if (gy) gy.setAttribute('x', String(yx));
    const gz = $('gm-z'); if (gz) { gz.setAttribute('x', String(yx + 6)); gz.setAttribute('y', String(62 + (1 - nz) * 50)); gz.setAttribute('height', String(12 + nz * 40)); }
    const gr = $('gm-r'); if (gr) gr.setAttribute('transform', 'translate(' + (yx - 170) + ',0) rotate(' + r + ',183,47)');
  }
  function renderAlarms(code) {
    const info = ALARMS[code] || { name: '报警 ' + code, fix: '查看 PLC 报警表。' };
    const card = $('alarm-card'); if (card) { card.style.borderColor = code ? 'var(--alarm)' : 'var(--line)'; }
    setText('alarm-code', code); setText('alarm-name', info.name); setText('alarm-fix', info.fix);
    setChip('alarm-chip', code ? 'alarm' : 'off', code ? ('报警 ' + code) : '无报警');
    const set = (id, on, cls) => { const el = $(id); if (el) { el.textContent = on ? 'TRUE' : 'FALSE'; el.className = on ? (cls || 'run') : 'off'; } };
    set('lamp-estop', S.HMI_xLampEStop, 'alarm'); set('lamp-run2', S.HMI_xDevRun, 'run'); set('lamp-fault', S.HMI_xDevError || S.HMI_xLampFault, 'alarm');
    set('lamp-comm', S.Tcp_xConnected && !S.Tcp_xTimeout, 'ok'); set('lamp-ready2', S.AxisFb_xReady, 'ok');
    set('lamp-force', S.Force_xCommOk && !S.Force_xTimeout, 'ok');
    if (code !== lastAlarm) {
      if (code !== 0) alarmHist.unshift({ code, at: new Date(), recovered: false });
      if (code === 0 && lastAlarm !== 0) { const e = alarmHist.find((x) => x.code === lastAlarm && !x.recovered); if (e) e.recovered = true; }
      lastAlarm = code; renderAlarmList();
    }
    const ov = $('overlay');
    if (ov) {
      const estop = !!S.HMI_xLampEStop || code === 1001;
      if (estop && !overlayHidden) ov.classList.add('on'); else ov.classList.remove('on');
      if (!estop) overlayHidden = false;
      if (estop) { setText('ov-alarm-desc', '请释放物理急停按钮，然后执行复位。（报警 ' + code + '）'); }
    }
  }
  function renderDirect() {
    const online = !!S.Direct2_xOnline, safe = !!S.Direct2_xSafe;
    setChip('direct-chip', !S.connected ? 'off' : (!safe ? 'alarm' : (online ? 'run' : 'warn')),
      !S.connected ? 'OFFLINE' : (!safe ? 'UNSAFE' : (online ? 'ONLINE' : 'IDLE')));
    setText('d2-online', online ? 'TRUE' : 'FALSE');
    setText('d2-safe', safe ? 'TRUE' : 'FALSE');
    setText('d2-active', 'X=' + (S.Direct2_xActiveX ? 'T' : 'F') + ' Y=' + (S.Direct2_xActiveY ? 'T' : 'F') + ' Z=' + (S.Direct2_xActiveZ ? 'T' : 'F') + ' R=' + (S.Direct2_xActiveR ? 'T' : 'F'));
    setText('d2-seq', fmt(W.HMI_wDirectSeq, 0) + ' → ' + (S.Direct2_wSeqEcho == null ? '—' : fmt(S.Direct2_wSeqEcho, 0)));
    setText('d-ready', S.AxisFb_xReady ? 'TRUE' : 'FALSE');
    setText('d-alarm', fmt(S.HMI_iAlarmShow, 0));
    setText('d-m1-act', fmt(S.AxisFb_rVelActM1, 3)); setText('d-m2-act', fmt(S.AxisFb_rVelActM2, 3));
    setText('d-m1-pos', fmt(S.AxisFb_rPosM1, 4)); setText('d-m2-pos', fmt(S.AxisFb_rPosM2, 4));
    setText('d-sync', fmt(S.AxisFb_rSyncErr, 4));
    setText('d-y-pos', fmt(S.AxisFb_rPosY, 4)); setText('d-y-act', fmt(S.AxisFb_rVelActY, 3));
    setText('d-z-pos', fmt(S.AxisFb_rPosZ, 4)); setText('d-z-act', fmt(S.AxisFb_rVelActZ, 3));
    setText('d-r-pos', fmt(S.AxisFb_rPosR, 4)); setText('d-r-act', fmt(S.AxisFb_rVelActR, 3));
    setText('d-force-show', fmt(S.HMI_rForceShow, 1) + ' N');
    setText('d-force-echo', S.HMI_rForceSetEcho == null ? '—' : fmt(S.HMI_rForceSetEcho, 1) + ' N');
  }
  function renderAlarmList() {
    const el = $('alarm-list'); if (!el) return;
    if (!alarmHist.length) { el.innerHTML = '<span class="hint">尚无报警。</span>'; return; }
    el.innerHTML = '';
    alarmHist.slice(0, 20).forEach((a) => { const d = document.createElement('div'); d.className = 'alert'; const info = ALARMS[a.code] || { name: '报警 ' + a.code }; d.innerHTML = '<div class="code">' + a.code + '</div><div class="body"><b>' + info.name + '</b><span>' + (a.recovered ? '已恢复' : '活动') + '</span></div><div class="time">' + a.at.toLocaleTimeString() + '</div>'; el.appendChild(d); });
  }

  function drawSeries(ctx, w, h, arr, color, lo, hi, dash) {
    if (arr.length < 2 || hi - lo < 1e-9) return;
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath(); if (dash) ctx.setLineDash([5, 4]);
    const n = arr.length;
    for (let i = 0; i < n; i += 1) { const x = (i / Math.max(1, n - 1)) * (w - 4) + 2; const yy = h - ((arr[i] - lo) / (hi - lo)) * (h - 8) - 4; if (i === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy); }
    ctx.stroke(); if (dash) ctx.setLineDash([]);
  }
  function drawOne(id, series) {
    const c = $(id); if (!c || !c.getContext) return; const ctx = c.getContext('2d'); const w = c.width, h = c.height;
    ctx.clearRect(0, 0, w, h); ctx.strokeStyle = '#1a232e'; ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
    const sl = (arr) => arr.slice(Math.max(0, arr.length - winSamples));
    let lo = Infinity, hi = -Infinity;
    series.forEach((s) => sl(s.arr).forEach((v) => { if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
    if (!Number.isFinite(lo)) return; const pad = Math.max(1e-4, (hi - lo) * 0.1);
    series.forEach((s) => drawSeries(ctx, w, h, sl(s.arr), s.c, lo - pad, hi + pad, s.d));
  }
  function renderTrends() {
    const now = performance.now(); if (now - lastTrend < 100) return; lastTrend = now;
    drawOne('trend-xdual', [{ arr: HIST.act1, c: '#3fb950' }, { arr: HIST.act2, c: '#3b9dd6' }, { arr: HIST.vel1, c: '#8a97a6', d: 1 }, { arr: HIST.vel2, c: '#8a97a6', d: 1 }]);
    drawOne('trend-vel', [{ arr: HIST.act1, c: '#3fb950' }, { arr: HIST.act2, c: '#3b9dd6' }, { arr: HIST.vel1, c: '#8a97a6', d: 1 }, { arr: HIST.vel2, c: '#8a97a6', d: 1 }]);
    drawOne('trend-pos', [{ arr: HIST.p1, c: '#3fb950' }, { arr: HIST.p2, c: '#3b9dd6' }, { arr: HIST.p1.map((v, i) => v - num(HIST.p2[i])), c: '#e05555' }]);
    drawOne('trend-force', [{ arr: HIST.force, c: '#d29922' }]);
  }
  function snapshot(tag) {
    const line = [tag || 'SNAP', 'act=' + fmt(S.AxisFb_rVelActM1, 3) + '/' + fmt(S.AxisFb_rVelActM2, 3), 'pos=' + fmt(S.AxisFb_rPosM1, 4) + '/' + fmt(S.AxisFb_rPosM2, 4), 'alm=' + num(S.HMI_iAlarmShow)].join('  ');
    log(line);
    const el = $('snap-list'); if (el) { const d = document.createElement('div'); d.textContent = new Date().toLocaleTimeString() + '  ' + line; el.prepend(d); while (el.children.length > 100) el.removeChild(el.lastChild); }
  }
  function csvEscape(s) { const v = String(s); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function download(name, text) { const blob = new Blob([text], { type: 'text/csv;charset=utf-8' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0); }
  function exportHistory() { const rows = [['idx', 'velCmdM1', 'velCmdM2', 'velActM1', 'velActM2', 'posM1', 'posM2', 'force']]; for (let i = 0; i < HIST.t.length; i += 1) rows.push([i, HIST.vel1[i], HIST.vel2[i], HIST.act1[i], HIST.act2[i], HIST.p1[i], HIST.p2[i], HIST.force[i]]); download('lmm-trend-' + Date.now() + '.csv', rows.map((r) => r.map(csvEscape).join(',')).join('\n')); log('导出趋势 CSV ' + (rows.length - 1) + ' 行'); }
  function exportLog() { const rows = [['time', 'kind', 'msg']]; logs.forEach((l) => rows.push([new Date(l.at).toISOString(), l.kind, l.msg])); download('lmm-log-' + Date.now() + '.csv', rows.map((r) => r.map(csvEscape).join(',')).join('\n')); }

  function allMapFields() { if (!MAP) return []; const out = []; const push = (sec, fs) => (fs || []).forEach((f) => out.push(Object.assign({ section: sec }, f))); push('cmd', MAP.command && MAP.command.fields); push('cmd', MAP.directx && MAP.directx.command && MAP.directx.command.fields); push('st', MAP.status && MAP.status.fields); push('st', MAP.directx && MAP.directx.status && MAP.directx.status.fields); return out; }
  function buildRegTable() { const tb = document.querySelector('#regtable tbody'); if (!tb) return; tb.innerHTML = ''; allMapFields().forEach((f) => { const base = f.section === 'cmd' ? (MAP.command.baseAddress || 4096) : (MAP.status.baseAddress || 4352); const tr = document.createElement('tr'); const cells = [f.section === 'cmd' ? 'CMD' : 'ST', String(base + f.offset), f.name + (f.bit !== undefined ? '.' + f.bit : ''), f.type + (f.scale ? ' x' + f.scale : ''), '', f.zh || '']; cells.forEach((c, i) => { const td = document.createElement('td'); td.textContent = c; if (i === 1 || i === 2) td.className = 'mono'; tr.appendChild(td); }); tb.appendChild(tr); regCells[f.name] = tr.children[4]; }); }
  function refreshRegCells() { if (!MAP) return; for (const k in regCells) { const v = regCells[k]; const raw = (k in W) ? W[k] : S[k]; const s = typeof raw === 'boolean' ? (raw ? 'T' : 'F') : (raw === undefined ? '—' : String(raw)); if (v.textContent !== s) v.textContent = s; } }
  function sendJson() { const ta = $('cmd-json'); if (!ta) return; let obj; try { obj = JSON.parse(ta.value || '{}'); } catch (e) { log('JSON 解析失败: ' + e.message, 'err'); return; } const allowed = {}; for (const k in obj) { if (CMD_LABELS[k]) allowed[k] = obj[k]; else log('忽略非白名单字段 ' + k, 'warn'); } if (!Object.keys(allowed).length) { log('无可发送字段', 'warn'); return; } patch(allowed); log('console write ' + JSON.stringify(allowed)); }
  function pollHealth() { fetch('/health').then((r) => r.json()).then((h) => { healthAt = Date.now(); gwHealth = h; const el = $('health'); if (el) el.textContent = JSON.stringify(h, null, 2); render(); }).catch(() => { gwHealth = null; render(); }); }

  document.querySelectorAll('button[data-act]').forEach(bindHold);
  bindParam('p-velx', 'n-velx', 'HMI_rJogVelX', 2); bindParam('p-spin', 'n-spin', 'HMI_rSpinVel', 2);
  bindParam('p-vely', 'n-vely', 'HMI_rJogVelY', 2); bindParam('p-velz', 'n-velz', 'HMI_rJogVelZ', 2); bindParam('p-velr', 'n-velr', 'HMI_rJogVelR', 2);
  bindParam('p-accx', 'n-accx', 'HMI_rAccX', 0); bindParam('p-decx', 'n-decx', 'HMI_rDecX', 0);
  bindParam('p-accy', 'n-accy', 'HMI_rAccY', 0); bindParam('p-decy', 'n-decy', 'HMI_rDecY', 0);
  bindParam('p-accz', 'n-accz', 'HMI_rAccZ', 0); bindParam('p-decz', 'n-decz', 'HMI_rDecZ', 0);
  bindParam('p-accr', 'n-accr', 'HMI_rAccR', 0); bindParam('p-decr', 'n-decr', 'HMI_rDecR', 0);
  bindParam('p-dx', 'n-dx', 'HMI_rAutoDistX', 2); bindParam('p-avx', 'n-avx', 'HMI_rAutoVelX', 2);
  bindParam('p-avy', 'n-avy', 'HMI_rAutoVelY', 2); bindParam('p-avz', 'n-avz', 'HMI_rAutoVelZ', 2);
  bindParam('p-base', 'n-base', 'HMI_rWheelBase', 1); bindParam('p-npass', 'n-npass', 'HMI_iAutoPasses', 0);
  bindParam('p-fset', 'n-fset', 'HMI_rForceSet', 0); bindParam('p-kpf', 'n-kpf', 'HMI_rKpForce', 1);
  bindParam('p-kpt', 'n-kpt', 'HMI_rKpTrack', 2); bindParam('p-herr', 'n-herr', 'HMI_rHeadingErr', 2);
  bindParam('p-fsim', 'n-fsim', 'HMI_rForceSim', 0);
  bindParam('p-dvm1', 'n-dvm1', 'HMI_rVelM1Set', 3); bindParam('p-dvm2', 'n-dvm2', 'HMI_rVelM2Set', 3);
  setCheckbox('force-sim', 'HMI_xForceSimEnable'); setCheckbox('force-guide', 'HMI_xForceGuide'); setCheckbox('x-direct', 'HMI_xDirectEnable');
  // 「直控」页：每轴速度 / 位置 / 模式 + 力设定
  setCheckbox('direct-enable', 'HMI_xDirectEnable');
  bindParam('p-dm1', 'n-dm1', 'HMI_rVelM1Set', 3); bindParam('p-dm2', 'n-dm2', 'HMI_rVelM2Set', 3);
  bindParam('p-dpx', 'n-dpx', 'HMI_rDirectPosX', 3);
  bindParam('p-dvy', 'n-dvy', 'HMI_rDirectVelY', 3); bindParam('p-dpy', 'n-dpy', 'HMI_rDirectPosY', 3);
  bindParam('p-dvz', 'n-dvz', 'HMI_rDirectVelZ', 3); bindParam('p-dpz', 'n-dpz', 'HMI_rDirectPosZ', 3);
  bindParam('p-dvr', 'n-dvr', 'HMI_rDirectVelR', 3); bindParam('p-dpr', 'n-dpr', 'HMI_rDirectPosR', 3);
  bindParam('p-dfs', 'n-dfs', 'HMI_rForceSet', 0);
  [['dmx', 'HMI_iDirectModeX'], ['dmy', 'HMI_iDirectModeY'], ['dmz', 'HMI_iDirectModeZ'], ['dmr', 'HMI_iDirectModeR']]
    .forEach(([id, key]) => on(id, 'change', () => patch({ [key]: Number($(id).value) })));

  on('btn-estop', 'pointerdown', (e) => { e.preventDefault(); patch({ HMI_xEStop: false }); });
  const estopUp = (e) => { e.preventDefault(); patch({ HMI_xEStop: true }); };
  on('btn-estop', 'pointerup', estopUp); on('btn-estop', 'pointerleave', estopUp);
  on('btn-stop', 'pointerdown', (e) => { e.preventDefault(); patch({ HMI_xStop: true }); });
  on('btn-stop', 'pointerup', (e) => { e.preventDefault(); patch({ HMI_xStop: false }); });
  on('btn-stop', 'pointerleave', (e) => { e.preventDefault(); patch({ HMI_xStop: false }); });
  on('btn-reset', 'click', () => pulse({ HMI_xStopHold3s: true }, 150));
  on('btn-overlay-reset', 'click', () => { overlayHidden = true; pulse({ HMI_xStopHold3s: true, HMI_xEStop: true }, 150); });
  on('btn-overlay-dismiss', 'click', () => { overlayHidden = true; render(); });
  on('btn-auto-start', 'click', () => pulse({ HMI_xAutoStart: true, HMI_xAutoAbort: false }, 120));
  on('btn-auto-abort', 'click', () => pulse({ HMI_xAutoAbort: true }, 120));
  on('btn-tare', 'click', () => pulse({ HMI_xForceTare: true }, 120));
  on('btn-untare', 'click', () => pulse({ HMI_xForceUntare: true }, 120));
  function pulseHome(partial) { const sel = document.querySelector('input[name=home-axis]:checked'); const o = Object.assign({ HMI_xHomeY: false, HMI_xHomeZ: false, HMI_xHomeR: false, HMI_xHomeExec: false }, partial); if (o.HMI_xHomeExec) o.HMI_iHomeAxis = sel ? Number(sel.value) : 1; patch(o); setTimeout(() => patch({ HMI_xHomeY: false, HMI_xHomeZ: false, HMI_xHomeR: false, HMI_xHomeExec: false }, false), 220); }
  on('btn-home-exec', 'click', () => pulseHome({ HMI_xHomeExec: true }));
  on('btn-home-y', 'click', () => pulseHome({ HMI_xHomeY: true })); on('btn-home-z', 'click', () => pulseHome({ HMI_xHomeZ: true })); on('btn-home-r', 'click', () => pulseHome({ HMI_xHomeR: true }));
  on('btn-snap', 'click', () => snapshot('SNAP'));
  on('btn-trend-clear', 'click', () => { const keys = ['t', 'vel1', 'vel2', 'act1', 'act2', 'p1', 'p2', 'force']; keys.forEach((k) => { HIST[k].length = 0; }); log('趋势已清空'); });
  on('btn-clear-hist', 'click', () => { const keys = ['t', 'vel1', 'vel2', 'act1', 'act2', 'p1', 'p2', 'force']; keys.forEach((k) => { HIST[k].length = 0; }); const a = $('snap-list'); if (a) a.innerHTML = ''; const b = $('log'); if (b) b.innerHTML = ''; log('历史已清空'); });
  on('btn-export-csv', 'click', exportHistory);
  on('btn-log-clear', 'click', () => { logs.length = 0; const le = $('log'); if (le) le.innerHTML = ''; });
  on('btn-log-export', 'click', exportLog);
  on('btn-send-json', 'click', sendJson);
  on('btn-preset-safe', 'click', () => patch({ HMI_xEStop: false })); on('btn-preset-normal', 'click', () => patch({ HMI_xEStop: true }));
  on('btn-preset-auto', 'click', () => patch({ HMI_xAutoMode: true })); on('btn-preset-manual', 'click', () => patch({ HMI_xAutoMode: false }));
  on('btn-dvm-fwd', 'click', () => patch({ HMI_rVelM1Set: 0.3, HMI_rVelM2Set: 0.3, HMI_xDirectEnable: true }));
  on('btn-dvm-rev', 'click', () => patch({ HMI_rVelM1Set: -0.3, HMI_rVelM2Set: -0.3, HMI_xDirectEnable: true }));
  on('btn-dvm-stop', 'click', () => patch({ HMI_rVelM1Set: 0, HMI_rVelM2Set: 0 })); on('btn-dvm-off', 'click', () => patch({ HMI_xDirectEnable: false }));
  on('btn-health', 'click', pollHealth);
  document.querySelectorAll('[data-win]').forEach((b) => b.addEventListener('click', () => { winSamples = Number(b.dataset.win) * 10; }));

  fetch('/map').then((r) => r.json()).then((m) => { MAP = m; buildRegTable(); }).catch(() => {});
  setInterval(() => { const c = $('clock'); if (c) c.textContent = new Date().toLocaleTimeString(); }, 1000);
  setInterval(() => { if (ws && ws.readyState === 1) { ws.send(JSON.stringify({ t: 'ping' })); if (dirty) flush(false); } }, 200);
  setInterval(() => { if (ws && ws.readyState === 1) { lastPingAt = Date.now(); ws.send(JSON.stringify({ t: 'ping' })); } }, 1000);
  // 直控页开启时 HMI_wDirectSeq 每 ~100ms 自增并随命令镜像下发（未取得控制权时 flush 不发送）
  setInterval(() => {
    if (activePage !== 'direct' || !ws || ws.readyState !== 1) return;
    W.HMI_wDirectSeq = (Number(W.HMI_wDirectSeq) + 1) & 0xffff;
    dirty = true; flush(false);
  }, 100);

  setConn(false); render(); log('WebHMI v3 就绪 - 总览/自动/手动/X双驱/直控/力传感/趋势/报警/调试/系统');
  pollHealth(); setInterval(pollHealth, 2000); connect();
})();
