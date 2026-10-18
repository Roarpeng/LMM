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
  // 服务器模式（PLC_SERVER=1）：网关作为 Modbus TCP Server，等 PLC 主站来拉命令/推状态。
  const serverMode = env.PLC_SERVER === '1';
  const plcServerPort = Number(env.PLC_SERVER_PORT || 502);
  // 状态轮询地址覆盖：从站 ESV 侧窗读同一状态帧时与契约基址可能相差若干字。
  const statusPollAddress = env.PLC_STATUS_POLL_ADDR ? Number(env.PLC_STATUS_POLL_ADDR) : undefined;
  const writerLeaseMs = Number(env.WRITER_LEASE_MS || 1000);
  const statusTimeoutMs = Number(env.STATUS_TIMEOUT_MS || 1000);
  const statusCheckMs = Number(env.STATUS_CHECK_MS || 100);
  const visionTimeoutMs = Number(env.VISION_TIMEOUT_MS || 200);
  const cmdEchoMs = Number(env.CMD_ECHO_MS || 200);
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
  let cmdEchoTimer = null;
  let cmdEchoAt = 0;
  let closing = false;
  let clientSeq = 0;
  const startedAt = Date.now();

  function broadcast(message) {
    const payload = JSON.stringify(message);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(payload);
    }
  }

  // 命令镜像回显 {t:"c"}：网关实际收下、将写给 PLC 的命令（含其他写者，如视觉工控机），
  // 供所有页面只读显示。写入后按 CMD_ECHO_MS 节流（首帧立即、末帧补发），租约变化/安全值立即发。
  function commandEcho() {
    return {
      t: 'c',
      owner: leaseOwner ? leaseOwner._clientId ?? null : null,
      at: Date.now(),
      values: store.getCommandValues(),
    };
  }

  function broadcastCommandEcho() {
    clearTimeout(cmdEchoTimer);
    cmdEchoTimer = null;
    cmdEchoAt = Date.now();
    broadcast(commandEcho());
  }

  function scheduleCommandEcho() {
    if (cmdEchoTimer) return;
    const wait = cmdEchoMs - (Date.now() - cmdEchoAt);
    if (wait <= 0) broadcastCommandEcho();
    else cmdEchoTimer = setTimeout(broadcastCommandEcho, wait);
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
  let modbusServer = null;
  let heartbeatTimer = null;
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
    if (!closing) broadcastCommandEcho();
  }

  function renewWriterLease(ws) {
    const changed = leaseOwner !== ws;
    leaseOwner = ws;
    clearTimeout(leaseTimer);
    leaseTimer = setTimeout(() => safeguardAndRelease(ws), writerLeaseMs);
    // 只在易主时广播（续约每 30 ms 一次，逐次广播会刷屏）；新连接在 connection 时单独补发
    if (changed) broadcast({ t: 'lease', owner: ws._clientId ?? null });
  }

  if (mode === 'mock') {
    // MOCK_GROUND_Z：模拟地面高度（m，Z 向下为负；默认 -0.3），供外部工步压力/未接触场景
    mockPlc = createMockPlc({}, { groundZ: Number(env.MOCK_GROUND_Z) });
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
      writeCommands: !serverMode,
      statusPollAddress,
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
    if (serverMode) {
      // PLC 为主站的架构（0.80）：PLC 通过 Modbus 主站通道从网关拉命令（FC03 @4096）、
      // 推状态（FC16 @4352）。此处起 Modbus TCP Server 提供该接口；
      // 主站轮询退化为只读状态（见 writeCommands/statusPollAddress）。
      const { ServerTCP } = require('modbus-serial');
      // 不按 unitID 过滤：Wecon 主站可能以 SlaveAddr(如 255) 发请求，vector 不区分 unit。
      const serverVector = Object.assign({}, store.vector);
      if (!serverVector.getInputRegister && serverVector.getHoldingRegister) {
        serverVector.getInputRegister = serverVector.getHoldingRegister;
      }
      // 0.80 现场写通道挂接在 %QW42（比 MB_StatusOut 早 2 字）：FC16 推来的 96 字是
      // [前缀2][帧0..93]，帧头落在 +2。兼容重构为 [帧0..93, 0, 0]——word94 无字段、
      // word95 为尾序号回显，codec 对 tail=0 容忍，无数据丢失。
      const rawSetRegisterArray = store.vector.setRegisterArray;
      const isShiftedStatus = (list) => list[map.status.header.magic + 2] === map.protocol.magic
        && (list[map.status.header.version + 2] >>> 8) === map.protocol.versionMajor;
      serverVector.setRegisterArray = (address, values, unitID, callback) => {
        const list = Array.from(values);
        if (
          address === map.status.baseAddress
          && list.length === map.protocol.imageWords
          && isShiftedStatus(list)
        ) {
          return rawSetRegisterArray(address, [...list.slice(2), 0, 0], unitID, callback);
        }
        return rawSetRegisterArray(address, values, unitID, callback);
      };
      modbusServer = new ServerTCP(serverVector, {
        host: env.PLC_SERVER_HOST || '0.0.0.0',
        port: plcServerPort,
        debug: false,
      });
      modbusServer.on('initialized', () => {
        console.log(`[gateway] Modbus TCP server listening :${plcServerPort} (PLC master pulls cmd@${map.command.baseAddress}, pushes status@${map.status.baseAddress})`);
      });
      // 调试：记录 PLC 主站前若干个原始请求帧（MBAP+PDU hex），用于联调对齐。
      // 注意 ServerTCP 是 EventEmitter 包装，socket 连接事件挂在内部 _server 上。
      if (env.PLC_SERVER_TRACE === '1') {
        let fcReads = 0;
        let fcPushes = 0;
        const rawGet = serverVector.getHoldingRegister;
        serverVector.getHoldingRegister = (a, u, cb) => {
          fcReads += 1;
          return rawGet(a, u, cb);
        };
        const rawPush = serverVector.setRegisterArray;
        serverVector.setRegisterArray = (a, v, u, cb) => {
          fcPushes += 1;
          return rawPush(a, v, u, cb);
        };
        setInterval(() => {
          if (fcReads || fcPushes) console.log(`[modbus-server] served FC03 words=${fcReads} FC16 pushes=${fcPushes}`);
          fcReads = 0;
          fcPushes = 0;
        }, 10000).unref();
        const netServer = modbusServer._server;
        if (netServer && typeof netServer.on === 'function') {
          netServer.on('connection', (sock) => {
            const peer = `${sock.remoteAddress}:${sock.remotePort}`;
            let seen = 0;
            console.log(`[modbus-server] conn from ${peer}`);
            sock.on('data', (buf) => {
              if (seen >= 6) return;
              seen += 1;
              console.log(`[modbus-rx] ${peer} ${buf.toString('hex')}`);
            });
            sock.on('error', () => {});
          });
        }
      }
      // 服务器模式下由网关侧推进心跳（≥1Hz），维持 PLC 远程在线看门狗 tonHb。
      heartbeatTimer = setInterval(() => store.advanceHeartbeat(), 500);
    }
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
    if (leaseOwner) ws.send(JSON.stringify({ t: 'lease', owner: leaseOwner._clientId ?? null }));
    ws.send(JSON.stringify(commandEcho()));
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
        scheduleCommandEcho();
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
      clearTimeout(cmdEchoTimer);
      clearInterval(mockTimer);
      clearInterval(statusTimer);
      clearInterval(visionTimer);
      clearInterval(heartbeatTimer);
      for (const client of wss.clients) client.terminate();

      const closes = [
        closeComponent((done) => wss.close(done)),
        closeComponent((done) => httpServer.close(done)),
      ];
      if (modbusMaster) {
        closes.push(Promise.resolve(modbusMaster.close()));
      }
      if (modbusServer) {
        closes.push(closeComponent((done) => modbusServer.close(done)));
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
