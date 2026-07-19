#!/usr/bin/env node
/**
 * LMM WebHMI gateway
 * Browser ←WS:8080→ this ←TCP:9100→ PLC (or embedded mock)
 *
 * Env:
 *   PLC_HOST=127.0.0.1
 *   PLC_PORT=9100
 *   WS_PORT=8080
 *   HTTP_PORT=8080  (same server serves / and WS)
 *   MOCK_PLC=1      (default if PLC connect fails, or force mock)
 */
const net = require('net');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const PLC_HOST = process.env.PLC_HOST || '127.0.0.1';
const PLC_PORT = Number(process.env.PLC_PORT || 9100);
const PORT = Number(process.env.HTTP_PORT || process.env.WS_PORT || 8080);
const FORCE_MOCK = process.env.MOCK_PLC === '1';
const ROOT = path.join(__dirname, '..', 'web', 'live');

const WRITE_KEYS = new Set([
  'HMI_xEStop', 'HMI_xStop', 'HMI_xStopHold3s', 'HMI_xStart', 'HMI_xEnable',
  'HMI_xAutoMode',
  'HMI_xJogXPos', 'HMI_xJogXNeg', 'HMI_xSpinLeft', 'HMI_xSpinRight',
  'HMI_xJogYPos', 'HMI_xJogYNeg', 'HMI_xJogZPos', 'HMI_xJogZNeg',
  'HMI_xJogRPos', 'HMI_xJogRNeg',
  'HMI_rJogVelX', 'HMI_rSpinVel', 'HMI_rJogVelY', 'HMI_rJogVelZ', 'HMI_rJogVelR',
  'HMI_xAutoStart', 'HMI_xAutoAbort',
  'HMI_rAutoDistX', 'HMI_rAutoVelX', 'HMI_rAutoVelY', 'HMI_rAutoVelZ',
  'HMI_rWheelBase', 'HMI_rForceSet', 'HMI_xForceSimEnable', 'HMI_rForceSim',
]);

function mime(p) {
  if (p.endsWith('.html')) return 'text/html; charset=utf-8';
  if (p.endsWith('.js')) return 'application/javascript';
  if (p.endsWith('.css')) return 'text/css';
  if (p.endsWith('.json')) return 'application/json';
  return 'application/octet-stream';
}

/* ---------- mock PLC state (also used when MOCK) ---------- */
const mock = {
  req: {
    HMI_xEStop: true,
    HMI_xStop: false,
    HMI_xStopHold3s: false,
    HMI_xStart: false,
    HMI_xEnable: false,
    HMI_xAutoMode: false,
    HMI_xJogXPos: false,
    HMI_xJogXNeg: false,
    HMI_xSpinLeft: false,
    HMI_xSpinRight: false,
    HMI_xJogYPos: false,
    HMI_xJogYNeg: false,
    HMI_xJogZPos: false,
    HMI_xJogZNeg: false,
    HMI_xJogRPos: false,
    HMI_xJogRNeg: false,
    HMI_rJogVelX: 0.4,
    HMI_rSpinVel: 0.3,
    HMI_rJogVelY: 0.3,
    HMI_rJogVelZ: 0.2,
    HMI_rJogVelR: 0.2,
    HMI_xAutoStart: false,
    HMI_xAutoAbort: false,
    HMI_rAutoDistX: 1.0,
    HMI_rAutoVelX: 0.4,
    HMI_rAutoVelY: 0.3,
    HMI_rAutoVelZ: 0.15,
    HMI_rWheelBase: 5.0,
    HMI_rForceSet: 100,
    HMI_xForceSimEnable: true,
    HMI_rForceSim: 0,
  },
  eDevState: 0,
  eOpMode: 0,
  iAutoStep: 0,
  autoBusy: false,
  autoDone: false,
  forceShow: 0,
  alarm: 0,
  estopLatch: false,
  startPrev: false,
  autoStartPrev: false,
  posY: 0,
  posZ: 0,
};

function applyWrite(obj) {
  for (const [k, v] of Object.entries(obj)) {
    if (k === 't' || k === 'seq') continue;
    if (!WRITE_KEYS.has(k)) continue;
    mock.req[k] = v;
  }
}

function tickMock(dt) {
  const r = mock.req;
  if (!r.HMI_xEStop) mock.estopLatch = true;
  if (r.HMI_xStopHold3s) {
    mock.estopLatch = false;
    mock.eDevState = 0;
    mock.iAutoStep = 0;
    mock.autoBusy = false;
  }
  const startEdge = (r.HMI_xStart || r.HMI_xEnable) && !mock.startPrev;
  mock.startPrev = !!(r.HMI_xStart || r.HMI_xEnable);
  if (mock.estopLatch || !r.HMI_xEStop) mock.eDevState = 2;
  else if (r.HMI_xStop) mock.eDevState = 0;
  else if (startEdge && mock.eDevState === 0) mock.eDevState = 1;

  mock.eOpMode = r.HMI_xAutoMode ? 1 : 0;
  mock.forceShow = r.HMI_xForceSimEnable ? r.HMI_rForceSim : mock.forceShow;

  const jog =
    r.HMI_xJogXPos || r.HMI_xJogXNeg || r.HMI_xSpinLeft || r.HMI_xSpinRight ||
    r.HMI_xJogYPos || r.HMI_xJogYNeg || r.HMI_xJogZPos || r.HMI_xJogZNeg ||
    r.HMI_xJogRPos || r.HMI_xJogRNeg;
  if (mock.eDevState === 1 && mock.eOpMode === 0 && jog) {
    if (r.HMI_xJogYPos) mock.posY += r.HMI_rJogVelY * dt;
    if (r.HMI_xJogYNeg) mock.posY -= r.HMI_rJogVelY * dt;
    if (r.HMI_xJogZPos) mock.posZ += r.HMI_rJogVelZ * dt;
    if (r.HMI_xJogZNeg) mock.posZ -= r.HMI_rJogVelZ * dt;
  }

  const autoEdge = r.HMI_xAutoStart && !mock.autoStartPrev;
  mock.autoStartPrev = !!r.HMI_xAutoStart;
  if (r.HMI_xAutoAbort || mock.eDevState !== 1) {
    mock.autoBusy = false;
    mock.iAutoStep = 0;
  } else if (autoEdge && mock.eOpMode === 1 && mock.eDevState === 1) {
    mock.iAutoStep = 1;
    mock.autoBusy = true;
    mock.autoDone = false;
  } else if (mock.autoBusy) {
    mock.iAutoStep += dt > 0 ? 0.4 * dt : 0; // advance ~2.5s/step
    if (mock.iAutoStep >= 5) {
      mock.iAutoStep = 5;
      mock.autoBusy = false;
      mock.autoDone = true;
      mock.iAutoStep = 0;
    }
  }
}

function statusMsg() {
  const step = Math.floor(mock.iAutoStep);
  return {
    t: 's',
    HMI_eDevState: mock.eDevState,
    HMI_eOpMode: mock.eOpMode,
    HMI_xDevStop: mock.eDevState === 0,
    HMI_xDevRun: mock.eDevState === 1,
    HMI_xDevError: mock.eDevState === 2,
    HMI_xLampEStop: mock.estopLatch || !mock.req.HMI_xEStop,
    HMI_xLampEnableOk: mock.eDevState === 1,
    HMI_xLampFault: mock.eDevState === 2,
    HMI_iAlarmShow: mock.eDevState === 2 ? 1001 : mock.alarm,
    HMI_iAutoStepShow: step,
    HMI_xAutoBusy: mock.autoBusy,
    HMI_xAutoDone: mock.autoDone,
    HMI_rForceShow: mock.forceShow,
    Tcp_xConnected: true,
    Tcp_xTimeout: false,
    AxisFb_rPosY: mock.posY,
    AxisFb_rPosZ: mock.posZ,
    AxisFb_xReady: true,
  };
}

/* ---------- TCP to real PLC ---------- */
let plcSocket = null;
let plcBuf = '';
let useMock = FORCE_MOCK;
let lastPlcRx = Date.now();

function broadcast(obj) {
  const line = JSON.stringify(obj);
  for (const ws of wss.clients) {
    if (ws.readyState === 1) ws.send(line);
  }
}

function sendToPlc(obj) {
  const line = JSON.stringify(obj) + '\n';
  if (useMock || !plcSocket || plcSocket.destroyed) {
    applyWrite(obj);
    return;
  }
  try {
    plcSocket.write(line);
  } catch (e) {
    console.error('PLC write fail', e.message);
  }
}

function connectPlc() {
  if (FORCE_MOCK) {
    useMock = true;
    console.log('[gateway] MOCK_PLC=1 — in-process mock');
    return;
  }
  const s = net.connect({ host: PLC_HOST, port: PLC_PORT }, () => {
    plcSocket = s;
    useMock = false;
    plcBuf = '';
    lastPlcRx = Date.now();
    console.log(`[gateway] TCP connected ${PLC_HOST}:${PLC_PORT}`);
  });
  s.on('data', (chunk) => {
    lastPlcRx = Date.now();
    plcBuf += chunk.toString('utf8');
    let idx;
    while ((idx = plcBuf.indexOf('\n')) >= 0) {
      const line = plcBuf.slice(0, idx).trim();
      plcBuf = plcBuf.slice(idx + 1);
      if (!line) continue;
      try {
        const msg = JSON.parse(line);
        if (msg.t === 's' || msg.t === 'pong' || msg.t === 'err') broadcast(msg);
      } catch {
        /* ignore */
      }
    }
  });
  s.on('error', (e) => {
    console.warn('[gateway] PLC TCP error:', e.message, '— fallback MOCK');
    useMock = true;
    plcSocket = null;
  });
  s.on('close', () => {
    console.warn('[gateway] PLC TCP closed — fallback MOCK, retry 3s');
    plcSocket = null;
    useMock = true;
    setTimeout(connectPlc, 3000);
  });
}

const server = http.createServer((req, res) => {
  let url = req.url.split('?')[0];
  if (url === '/') url = '/index.html';
  const fp = path.normalize(path.join(ROOT, url));
  if (!fp.startsWith(ROOT)) {
    res.writeHead(403);
    res.end('forbidden');
    return;
  }
  fs.readFile(fp, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'Content-Type': mime(fp) });
    res.end(data);
  });
});

const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  ws.send(JSON.stringify({ t: 's', ...statusMsg(), _gateway: useMock ? 'mock' : 'plc' }));
  ws.on('message', (raw) => {
    let msg;
    try {
      msg = JSON.parse(String(raw));
    } catch {
      ws.send(JSON.stringify({ t: 'err', code: 1, msg: 'parse' }));
      return;
    }
    if (msg.t === 'ping') {
      ws.send(JSON.stringify({ t: 'pong' }));
      sendToPlc({ t: 'ping' });
      return;
    }
    if (msg.t === 'w') {
      const out = { t: 'w' };
      for (const [k, v] of Object.entries(msg)) {
        if (k === 't' || k === 'seq') {
          if (k === 'seq') out.seq = v;
          continue;
        }
        if (WRITE_KEYS.has(k)) out[k] = v;
      }
      sendToPlc(out);
    }
  });
});

let lastTick = Date.now();
setInterval(() => {
  const now = Date.now();
  const dt = (now - lastTick) / 1000;
  lastTick = now;
  if (useMock) {
    tickMock(dt);
    broadcast(statusMsg());
  } else {
    sendToPlc({ t: 'ping' });
    if (now - lastPlcRx > 2000) {
      console.warn('[gateway] PLC silent — stay connected but flag timeout in UI via last s');
    }
  }
}, 100);

server.listen(PORT, () => {
  console.log(`[gateway] http+ws http://127.0.0.1:${PORT}/  (web/live)`);
  console.log(`[gateway] PLC target ${PLC_HOST}:${PLC_PORT} mock=${FORCE_MOCK}`);
  connectPlc();
});
