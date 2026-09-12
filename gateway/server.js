#!/usr/bin/env node
'use strict';

/**
 * LMM WebHMI gateway
 * Browser <-WebSocket/JSON-> Gateway (Modbus master) -> PLC slave
 * 目标默认 PLC_HOST=192.168.1.88 PLC_PORT=502；启动日志与 GET /health 可核对。
 */
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { WebSocketServer, WebSocket } = require('ws');

const map = require('../config/modbus-map.json');
const { createMockPlc } = require('./lib/mock-plc');
const { createModbusStore } = require('./lib/modbus-store');

const ROOT = path.join(__dirname, '..', 'web', 'live');
const statusFieldList = [
  ...map.status.fields,
  ...((map.directx && map.directx.status && map.directx.status.fields) || []),
];
const statusDefaults = Object.freeze(Object.fromEntries(
  statusFieldList.map((field) => [field.name, field.type === 'BOOL' ? false : 0]),
));

function resolveGatewayMode(env = process.env) {
  return env.MOCK_PLC === '1' ? 'mock' : 'modbus-master';
}

function createOfflineStatus(previous = {}, mode = 'modbus-master') {
  return {
    t: 's',
    ...statusDefaults,
    ...previous,
    Tcp_iCommStatus: 0,
    HMI_eDevState: 0,
    HMI_xDevStop: true,
    HMI_xDevRun: false,
    HMI_xLampEnableOk: false,
    HMI_xAutoBusy: false,
    HMI_xAutoDone: false,
    HMI_xHomeBusyY: false,
    HMI_xHomeBusyZ: false,
    HMI_xHomeBusyR: false,
    Tcp_xConnected: false,
    Tcp_xTimeout: true,
    AxisFb_xReady: false,
    _gateway: mode,
  };
}

function mime(filePath) {
  if (filePath.endsWith('.html')) return 'text/html; charset=utf-8';
  if (filePath.endsWith('.js')) return 'application/javascript';
  if (filePath.endsWith('.css')) return 'text/css';
  if (filePath.endsWith('.json')) return 'application/json';
  return 'application/octet-stream';
}

function createHttpServer(root = ROOT, options = {}) {
  const onVision = options.onVision;
  const onHealth = options.onHealth;
  return http.createServer((request, response) => {
    let url = request.url.split('?')[0];
    if (url === '/health') {
      response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify(onHealth ? onHealth() : { ok: true }));
      return;
    }
    if (request.method === 'POST' && url === '/vision' && onVision) {
      let body = '';
      request.on('data', (chunk) => {
        body += chunk;
        if (body.length > 4096) request.destroy();
      });
      request.on('end', () => {
        try {
          onVision(JSON.parse(body || '{}'));
          response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
          response.end(JSON.stringify({ ok: true }));
        } catch (error) {
          response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          response.end(JSON.stringify({ ok: false, error: error.message }));
        }
      });
      return;
    }
    if (url === '/map') {
      response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify(map));
      return;
    }
    if (url === '/') url = '/index.html';
    const filePath = path.normalize(path.join(root, url));
    if (!filePath.startsWith(root)) {
      response.writeHead(403);
      response.end('forbidden');
      return;
    }
    fs.readFile(filePath, (error, data) => {
      if (error) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      response.writeHead(200, { 'Content-Type': mime(filePath) });
      response.end(data);
    });
  });
}

function startGateway(env = process.env) {
  const mode = resolveGatewayMode(env);
  // 现场对齐：从站 Internal I/O 映射若不在 1000/1100，可用环境变量临时改基址（不改文件）。
  if (env.PLC_CMD_BASE) map.command.baseAddress = Number(env.PLC_CMD_BASE);
  if (env.PLC_STATUS_BASE) map.status.baseAddress = Number(env.PLC_STATUS_BASE);
  const httpPort = Number(env.HTTP_PORT || env.WS_PORT || 8080);
  // PLC slave target (master mode). Prefer PLC_*; fall back to MODBUS_* aliases.
  const plcHost = env.PLC_HOST || env.MODBUS_HOST || '192.168.1.88';
  const plcPort = Number(env.PLC_PORT || env.MODBUS_PORT || 502);
  const unitID = Number(env.PLC_UNIT_ID || env.MODBUS_UNIT_ID || 1);
  const pollMs = Number(env.PLC_POLL_MS || 50);
  const writerLeaseMs = Number(env.WRITER_LEASE_MS || 1000);
  const statusTimeoutMs = Number(env.STATUS_TIMEOUT_MS || 1000);
  const statusCheckMs = Number(env.STATUS_CHECK_MS || 100);
  const visionTimeoutMs = Number(env.VISION_TIMEOUT_MS || 200);
  let handleVision = () => {};
  const httpServer = createHttpServer(ROOT, {
    onVision: (message) => handleVision(message),
    onHealth: () => buildHealth(),
  });
  const wss = new WebSocketServer({ server: httpServer });
  let latestStatus = createOfflineStatus({}, mode);
  let lastValidStatusAt = 0;
  let statusIsOffline = true;
  let leaseOwner = null;
  let leaseTimer = null;
  let closing = false;
  let clientSeq = 0;
  const startedAt = Date.now();

  function broadcast(message) {
    const payload = JSON.stringify(message);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(payload);
    }
  }

  const store = createModbusStore({
    onStatus(status) {
      lastValidStatusAt = Date.now();
      statusIsOffline = false;
      latestStatus = {
        ...status,
        Tcp_iCommStatus: 2,
        Tcp_xConnected: true,
        Tcp_xTimeout: false,
        _gateway: mode,
      };
      broadcast(latestStatus);
    },
    onProtocolError(diagnostics) {
      console.warn('[gateway] rejected invalid status image:', diagnostics.errors.join(','));
    },
  });

  let visionLastAt = 0;
  let visionTimer = setInterval(() => {
    if (visionLastAt && Date.now() - visionLastAt > visionTimeoutMs) {
      store.releaseVision();
      visionLastAt = 0;
    }
  }, 100);
  handleVision = (message) => {
    store.applyVisionWrite(message);
    visionLastAt = Date.now();
  };

  let modbusMaster = null;
  let mockPlc = null;
  let mockTimer = null;
  let statusTimer = null;

  function safeguardAndRelease(owner = leaseOwner) {
    if (!leaseOwner || owner !== leaseOwner) return;
    clearTimeout(leaseTimer);
    leaseTimer = null;
    leaseOwner = null;
    store.safeguardCommands();
    if (mockPlc) mockPlc.applyWrite(store.getCommandValues());
    broadcast({ t: 'lease', owner: null });
  }

  function renewWriterLease(ws) {
    leaseOwner = ws;
    clearTimeout(leaseTimer);
    leaseTimer = setTimeout(() => safeguardAndRelease(ws), writerLeaseMs);
    broadcast({ t: 'lease', owner: ws._clientId ?? null });
  }

  if (mode === 'mock') {
    mockPlc = createMockPlc();
    latestStatus = { ...statusDefaults, ...mockPlc.statusMessage(), _gateway: mode };
    let lastTick = Date.now();
    mockTimer = setInterval(() => {
      const now = Date.now();
      mockPlc.tick((now - lastTick) / 1000);
      lastTick = now;
      latestStatus = { ...statusDefaults, ...mockPlc.statusMessage(), _gateway: mode };
      statusIsOffline = false;
      lastValidStatusAt = now;
      broadcast(latestStatus);
    }, 100);
    console.log('[gateway] MOCK_PLC=1 — in-process mock');
  } else {
    const { createModbusMaster } = require('./lib/modbus-master');
    modbusMaster = createModbusMaster({
      host: plcHost,
      port: plcPort,
      unitID,
      store,
      pollMs,
      onError(error) {
        console.warn('[gateway] Modbus master:', error.message || error);
      },
      onConnected() {
        console.log(`[gateway] Modbus master connected ${plcHost}:${plcPort} unit=${unitID}`);
      },
      onDisconnected() {
        console.warn('[gateway] Modbus master disconnected');
      },
    });
    modbusMaster.start();
    statusTimer = setInterval(() => {
      if (
        !statusIsOffline
        && lastValidStatusAt > 0
        && Date.now() - lastValidStatusAt > statusTimeoutMs
      ) {
        statusIsOffline = true;
        latestStatus = createOfflineStatus(latestStatus, mode);
        broadcast(latestStatus);
      }
    }, statusCheckMs);
    console.log(`[gateway] Modbus master → PLC slave ${plcHost}:${plcPort} unit=${unitID}`);
    console.log(`[gateway] cmd@${map.command.baseAddress} status@${map.status.baseAddress} (len ${map.protocol.imageWords})`);
  }

  function buildHealth() {
    const now = Date.now();
    return {
      ok: true,
      mode,
      clients: wss.clients.size,
      leaseOwner: leaseOwner ? leaseOwner._clientId ?? null : null,
      statusIsOffline,
      lastValidStatusAgeMs: lastValidStatusAt ? now - lastValidStatusAt : null,
      mock: Boolean(mockPlc),
      master: modbusMaster ? modbusMaster.getDiagnostics() : null,
      visionLastAgeMs: visionLastAt ? now - visionLastAt : null,
      version: require('./package.json').version,
      startedAt,
      uptimeMs: now - startedAt,
    };
  }

  wss.on('connection', (ws) => {
    ws._clientId = ++clientSeq;
    ws.send(JSON.stringify(latestStatus));
    ws.send(JSON.stringify({ t: 'hello', clientId: ws._clientId, mode }));
    ws.on('close', () => safeguardAndRelease(ws));
    ws.on('message', (raw) => {
      let message;
      try {
        message = JSON.parse(String(raw));
      } catch {
        ws.send(JSON.stringify({ t: 'err', code: 'PARSE_ERROR', msg: 'parse' }));
        return;
      }

      if (message.t === 'ping') {
        if (leaseOwner === ws) renewWriterLease(ws);
        ws.send(JSON.stringify({ t: 'pong', lease: leaseOwner === ws }));
        return;
      }
      if (message.t !== 'w') return;
      if (leaseOwner && leaseOwner !== ws) {
        ws.send(JSON.stringify({
          t: 'err',
          code: 'WRITE_LEASED',
          msg: 'another browser owns the write lease',
        }));
        return;
      }
      try {
        store.applyWebWrite(message);
        if (mockPlc) mockPlc.applyWrite(message);
        renewWriterLease(ws);
        // 写入确认：让页面能区分「点了但没到网关」与「网关已收下」
        ws.send(JSON.stringify({ t: 'wack', seq: message.seq ?? null, at: Date.now() }));
      } catch (error) {
        ws.send(JSON.stringify({
          t: 'err',
          code: error.code || 'INVALID_WRITE',
          msg: error.message,
        }));
      }
    });
  });

  httpServer.listen(httpPort, () => {
    const address = httpServer.address();
    console.log(`[gateway] http+ws http://127.0.0.1:${address.port}/  (web/live)`);
    console.log(`[gateway] mode=${mode}`);
  });

  let closePromise = null;

  function closeComponent(closeAction) {
    return new Promise((resolve, reject) => {
      let completed = false;
      const done = (error) => {
        if (completed) return;
        completed = true;
        if (error && error.code !== 'ERR_SERVER_NOT_RUNNING') reject(error);
        else resolve();
      };
      try {
        closeAction(done);
      } catch (error) {
        done(error);
      }
    });
  }

  function close(callback) {
    if (!closePromise) {
      closing = true;
      if (leaseOwner) safeguardAndRelease(leaseOwner);
      clearTimeout(leaseTimer);
      clearInterval(mockTimer);
      clearInterval(statusTimer);
      clearInterval(visionTimer);
      for (const client of wss.clients) client.terminate();

      const closes = [
        closeComponent((done) => wss.close(done)),
        closeComponent((done) => httpServer.close(done)),
      ];
      if (modbusMaster) {
        closes.push(Promise.resolve(modbusMaster.close()));
      }
      if (typeof httpServer.closeAllConnections === 'function') {
        httpServer.closeAllConnections();
      }
      closePromise = Promise.all(closes).then(() => undefined);
    }

    if (typeof callback === 'function') {
      let called = false;
      const doneOnce = (error) => {
        if (called) return;
        called = true;
        callback(error);
      };
      closePromise.then(() => doneOnce(), doneOnce);
    }
    return closePromise;
  }

  return {
    close,
    httpServer,
    mode,
    modbusMaster,
    store,
    wss,
    get closing() {
      return closing;
    },
  };
}

if (require.main === module) startGateway();

module.exports = {
  createHttpServer,
  createOfflineStatus,
  resolveGatewayMode,
  startGateway,
};
