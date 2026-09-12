'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const WebSocket = require('ws');

const map = require('../../config/modbus-map.json');
const {
  decodeCommandImage,
  encodeStatusImage,
} = require('../lib/modbus-codec');
const { FAIL_SAFE_COMMAND_VALUES } = require('../lib/modbus-store');
const { createMockPlc, MOCK_COMMAND_DEFAULTS } = require('../lib/mock-plc');
const { startGateway } = require('../server');

let portCounter = 0;

function nextModbusPort() {
  portCounter += 1;
  return 20000 + (process.pid % 10000) + portCounter;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitUntil(predicate, timeout = 1000) {
  const deadline = Date.now() + timeout;
  while (!(await predicate())) {
    if (Date.now() >= deadline) throw new Error('condition timeout');
    await delay(5);
  }
}

async function readCommand(store) {
  const words = [];
  for (let offset = 0; offset < map.protocol.imageWords; offset += 1) {
    const value = await new Promise((resolve, reject) => {
      store.vector.getHoldingRegister(
        map.command.baseAddress + offset,
        1,
        (error, result) => (error ? reject(error) : resolve(result)),
      );
    });
    words.push(value);
  }
  return decodeCommandImage(Uint16Array.from(words)).values;
}

function submitStatus(store, values = {}) {
  const words = Array.from(encodeStatusImage(values, 1, 1, 1));
  store.ingestStatusWords(words);
}

async function connectBrowser(httpServer) {
  const messages = [];
  const ws = new WebSocket(`ws://127.0.0.1:${httpServer.address().port}`);
  ws.on('message', (raw) => messages.push(JSON.parse(String(raw))));
  await new Promise((resolve, reject) => {
    ws.once('open', resolve);
    ws.once('error', reject);
  });
  return { messages, ws };
}

async function closeGateway(gateway) {
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('gateway close timeout')), 1000);
    gateway.close((error) => {
      clearTimeout(timeout);
      if (error) reject(error);
      else resolve();
    });
  });
}

async function startMockGateway(overrides = {}) {
  const gateway = startGateway({
    MOCK_PLC: '1',
    HTTP_PORT: '0',
    WRITER_LEASE_MS: '1000',
    ...overrides,
  });
  await new Promise((resolve) => gateway.httpServer.once('listening', resolve));
  return gateway;
}

async function startProductionGateway(overrides = {}) {
  const gateway = startGateway({
    MOCK_PLC: '0',
    HTTP_PORT: '0',
    PLC_HOST: '127.0.0.1',
    PLC_PORT: String(nextModbusPort()),
    PLC_POLL_MS: '200',
    ...overrides,
  });
  await new Promise((resolve) => gateway.httpServer.once('listening', resolve));
  return gateway;
}

test('only the lease owner may write while its lease is active', { timeout: 3000 }, async () => {
  const gateway = await startMockGateway();
  const owner = await connectBrowser(gateway.httpServer);
  const contender = await connectBrowser(gateway.httpServer);
  try {
    owner.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false, HMI_xEnable: true }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xEnable === true);

    contender.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false }));
    await waitUntil(() => contender.messages.some((message) => message.code === 'WRITE_LEASED'));

    assert.equal((await readCommand(gateway.store)).HMI_xStop, false);
  } finally {
    owner.ws.terminate();
    contender.ws.terminate();
    await closeGateway(gateway);
  }
});

test('owner disconnect atomically safeguards commands', { timeout: 3000 }, async () => {
  const gateway = await startMockGateway();
  const owner = await connectBrowser(gateway.httpServer);
  try {
    owner.ws.send(JSON.stringify({
      t: 'w',
      HMI_xStop: false,
      HMI_xEnable: true,
      HMI_xJogXPos: true,
      HMI_xAutoStart: true,
      HMI_xForceSimEnable: true,
    }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xJogXPos === true);
    owner.ws.terminate();
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xStop === true);

    const commands = await readCommand(gateway.store);
    for (const [key, expected] of Object.entries(FAIL_SAFE_COMMAND_VALUES)) {
      assert.equal(commands[key], expected, key);
    }
  } finally {
    owner.ws.terminate();
    await closeGateway(gateway);
  }
});

test('lease timeout safeguards commands and releases ownership', { timeout: 3000 }, async () => {
  const gateway = await startMockGateway({ WRITER_LEASE_MS: '40' });
  const owner = await connectBrowser(gateway.httpServer);
  const nextOwner = await connectBrowser(gateway.httpServer);
  try {
    owner.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false, HMI_xEnable: true }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xEnable === true);
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xStop === true);

    nextOwner.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false, HMI_xEnable: true }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xEnable === true);
    assert.equal(nextOwner.messages.some((message) => message.t === 'err'), false);
  } finally {
    owner.ws.terminate();
    nextOwner.ws.terminate();
    await closeGateway(gateway);
  }
});

test('owner ping keeps the write lease alive without resending commands', {
  timeout: 3000,
}, async () => {
  const gateway = await startMockGateway({ WRITER_LEASE_MS: '60' });
  const owner = await connectBrowser(gateway.httpServer);
  let keepAlive;
  try {
    owner.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false, HMI_xEnable: true }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xEnable === true);

    keepAlive = setInterval(() => {
      owner.ws.send(JSON.stringify({ t: 'ping' }));
    }, 20);
    await delay(160);

    assert.equal((await readCommand(gateway.store)).HMI_xEnable, true);
    clearInterval(keepAlive);
    keepAlive = null;
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xStop === true);
  } finally {
    clearInterval(keepAlive);
    owner.ws.terminate();
    await closeGateway(gateway);
  }
});

test('non-owner ping does not keep another browser write lease alive', {
  timeout: 3000,
}, async () => {
  const gateway = await startMockGateway({ WRITER_LEASE_MS: '60' });
  const owner = await connectBrowser(gateway.httpServer);
  const observer = await connectBrowser(gateway.httpServer);
  let keepAlive;
  try {
    owner.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false, HMI_xEnable: true }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xEnable === true);

    keepAlive = setInterval(() => {
      observer.ws.send(JSON.stringify({ t: 'ping' }));
    }, 20);
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xStop === true);

    assert.equal((await readCommand(gateway.store)).HMI_xEnable, false);
  } finally {
    clearInterval(keepAlive);
    owner.ws.terminate();
    observer.ws.terminate();
    await closeGateway(gateway);
  }
});

test('invalid browser values return t:err and leave gateway running', { timeout: 3000 }, async () => {
  const gateway = await startMockGateway();
  const browser = await connectBrowser(gateway.httpServer);
  try {
    browser.ws.send(JSON.stringify({ t: 'w', HMI_xEnable: 'yes' }));
    await waitUntil(() => browser.messages.some(
      (message) => message.t === 'err' && message.code === 'INVALID_WRITE',
    ));

    browser.ws.send(JSON.stringify({ t: 'w', HMI_xStop: false, HMI_xEnable: true }));
    await waitUntil(async () => (await readCommand(gateway.store)).HMI_xEnable === true);
  } finally {
    browser.ws.terminate();
    await closeGateway(gateway);
  }
});

test('production starts offline and times out one second after last valid status image', { timeout: 4000 }, async () => {
  const gateway = await startProductionGateway({
    STATUS_TIMEOUT_MS: '1000',
    STATUS_CHECK_MS: '20',
  });
  const browser = await connectBrowser(gateway.httpServer);
  try {
    const initial = browser.messages[0];
    assert.equal(initial.Tcp_xConnected, false);
    assert.equal(initial.Tcp_xTimeout, true);
    assert.equal(initial.HMI_xDevRun, false);

    submitStatus(gateway.store, {
      Tcp_xConnected: false,
      Tcp_xTimeout: true,
      HMI_xDevStop: false,
      HMI_xDevRun: true,
      HMI_xAutoBusy: true,
      AxisFb_xReady: true,
    });
    await waitUntil(() => browser.messages.some(
      (message) => message.Tcp_xConnected === true && message.HMI_xDevRun === true,
    ));

    await delay(1050);
    await waitUntil(() => browser.messages.some(
      (message) => message.Tcp_xTimeout === true && message.HMI_xDevRun === false,
    ));
    const offline = browser.messages.at(-1);
    assert.equal(offline.Tcp_xConnected, false);
    assert.equal(offline.Tcp_xTimeout, true);
    assert.equal(offline.HMI_xDevStop, true);
    assert.equal(offline.HMI_xDevRun, false);
    assert.equal(offline.HMI_xAutoBusy, false);
    assert.equal(offline.AxisFb_xReady, false);
  } finally {
    browser.ws.terminate();
    await closeGateway(gateway);
  }
});

test('mock command defaults remain independent from production fail-safe defaults', () => {
  const mock = createMockPlc();

  assert.notDeepEqual(MOCK_COMMAND_DEFAULTS, FAIL_SAFE_COMMAND_VALUES);
  assert.equal(mock.getCommandValues().HMI_xStop, false);
  assert.equal(mock.getCommandValues().HMI_xForceSimEnable, true);
});

test('close terminates clients and waits for WS, Modbus master, and HTTP exactly once', {
  timeout: 3000,
}, async () => {
  const gateway = await startProductionGateway();
  const browser = await connectBrowser(gateway.httpServer);
  let callbackCount = 0;

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('gateway close timeout')), 1000);
    gateway.close((error) => {
      callbackCount += 1;
      clearTimeout(timeout);
      if (error) reject(error);
      else resolve();
    });
  });
  await delay(20);

  assert.equal(callbackCount, 1);
  assert.equal(gateway.httpServer.listening, false);
  assert.ok(gateway.modbusMaster);
  assert.equal(gateway.modbusMaster.connected, false);
  assert.equal(browser.ws.readyState, WebSocket.CLOSED);
});

test('GET /health reports mode and diagnostics without crashing', { timeout: 3000 }, async () => {
  const gateway = await startMockGateway();
  try {
    const res = await fetch('http://127.0.0.1:' + gateway.httpServer.address().port + '/health');
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.ok, true);
    assert.equal(body.mode, 'mock');
    assert.equal(body.mock, true);
    assert.ok(body.clients >= 0);
  } finally {
    await closeGateway(gateway);
  }
});

test('mock status carries the 0.63 X actual-velocity passthrough fields', { timeout: 3000 }, async () => {
  const gateway = await startMockGateway();
  const browser = await connectBrowser(gateway.httpServer);
  try {
    await waitUntil(() => browser.messages.some(
      (message) => message.t === 's' && 'AxisFb_rVelActM1' in message,
    ));
  } finally {
    browser.ws.terminate();
    await closeGateway(gateway);
  }
});
