#!/usr/bin/env node
'use strict';

/**
 * LMM WebHMI gateway
 * Browser <-WebSocket/JSON-> Gateway <-Modbus TCP-> PLC master
 */
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const ModbusRTU = require('modbus-serial');
const { WebSocketServer, WebSocket } = require('ws');

const map = require('../config/modbus-map.json');
const { createMockPlc } = require('./lib/mock-plc');
const { createModbusStore } = require('./lib/modbus-store');

const ROOT = path.join(__dirname, '..', 'web', 'live');
const statusDefaults = Object.freeze(Object.fromEntries(
  map.status.fields.map((field) => [field.name, field.type === 'BOOL' ? false : 0]),
));

function resolveGatewayMode(env = process.env) {
  return env.MOCK_PLC === '1' ? 'mock' : 'modbus-server';
}

function createOfflineStatus(previous = {}, mode = 'modbus-server') {
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

function createHttpServer(root = ROOT) {
  return http.createServer((request, response) => {
    let url = request.url.split('?')[0];
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
  const httpPort = Number(env.HTTP_PORT || env.WS_PORT || 8080);
  const modbusHost = env.MODBUS_HOST || '0.0.0.0';
  const modbusPort = Number(env.MODBUS_PORT || 502);
  const unitID = Number(env.MODBUS_UNIT_ID || 1);
  const writerLeaseMs = Number(env.WRITER_LEASE_MS || 1000);
  const statusTimeoutMs = Number(env.STATUS_TIMEOUT_MS || 1000);
  const statusCheckMs = Number(env.STATUS_CHECK_MS || 100);
  const httpServer = createHttpServer();
  const wss = new WebSocketServer({ server: httpServer });
  let latestStatus = createOfflineStatus({}, mode);
  let lastValidStatusAt = 0;
  let statusIsOffline = true;
  let leaseOwner = null;
  let leaseTimer = null;
  let closing = false;

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

  let modbusServer = null;
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
  }

  function renewWriterLease(ws) {
    leaseOwner = ws;
    clearTimeout(leaseTimer);
    leaseTimer = setTimeout(() => safeguardAndRelease(ws), writerLeaseMs);
  }

  if (mode === 'mock') {
    mockPlc = createMockPlc();
    latestStatus = { ...mockPlc.statusMessage(), _gateway: mode };
    let lastTick = Date.now();
    mockTimer = setInterval(() => {
      const now = Date.now();
      mockPlc.tick((now - lastTick) / 1000);
      lastTick = now;
      latestStatus = { ...mockPlc.statusMessage(), _gateway: mode };
      broadcast(latestStatus);
    }, 100);
    console.log('[gateway] MOCK_PLC=1 — in-process mock');
  } else {
    modbusServer = new ModbusRTU.ServerTCP(store.vector, {
      host: modbusHost,
      port: modbusPort,
      unitID,
    });
    modbusServer.on('initialized', () => {
      console.log(`[gateway] Modbus TCP listening ${modbusHost}:${modbusPort} unit=${unitID}`);
    });
    modbusServer.on('serverError', (error) => {
      console.error('[gateway] Modbus TCP server error:', error.message);
    });
    modbusServer.on('socketError', (error) => {
      console.warn('[gateway] Modbus TCP socket error:', error.message);
    });
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
  }

  wss.on('connection', (ws) => {
    ws.send(JSON.stringify(latestStatus));
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
        ws.send(JSON.stringify({ t: 'pong' }));
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
      for (const client of wss.clients) client.terminate();

      const closes = [
        closeComponent((done) => wss.close(done)),
        closeComponent((done) => httpServer.close(done)),
      ];
      if (modbusServer) closes.push(closeComponent((done) => modbusServer.close(done)));
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
    modbusServer,
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
