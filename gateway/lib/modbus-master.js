'use strict';

const ModbusRTU = require('modbus-serial');
const map = require('../../config/modbus-map.json');

/**
 * Modbus TCP master that polls a PLC slave:
 * FC16 write command image @ command.baseAddress
 * FC03 read status image @ status.baseAddress
 */
function createModbusMaster(options) {
  const host = options.host;
  const port = Number(options.port);
  const unitID = Number(options.unitID || 1);
  const store = options.store;
  const pollMs = Number(options.pollMs || 100);
  const onError = options.onError || (() => {});
  const onConnected = options.onConnected || (() => {});
  const onDisconnected = options.onDisconnected || (() => {});

  const client = new ModbusRTU();
  let timer = null;
  let closed = false;
  let connecting = false;
  let connected = false;
  let pollInFlight = false;
  let pollCount = 0;
  let errorCount = 0;
  let lastSuccessAt = 0;
  let lastError = null;

  async function connect() {
    if (closed || connecting || connected) return;
    connecting = true;
    try {
      client.setTimeout(500);
      await client.connectTCP(host, { port });
      if (closed) {
        try {
          client.close(() => {});
        } catch {
          /* ignore */
        }
        return;
      }
      client.setID(unitID);
      connected = true;
      onConnected();
    } catch (error) {
      connected = false;
      if (!closed) onError(error);
      try {
        client.close(() => {});
      } catch {
        /* ignore */
      }
    } finally {
      connecting = false;
    }
  }

  async function pollOnce() {
    if (closed || pollInFlight) return;
    if (!connected) {
      await connect();
      if (!connected) return;
    }
    pollInFlight = true;
    try {
      // 每周期推进心跳，维持 PLC 远程在线看门狗（否则停顿 >1s 会被判远程超时）
      if (typeof store.advanceHeartbeat === 'function') store.advanceHeartbeat();
      const commandWords = Array.from(store.getCommandWords());
      // 0.60: 写命令镜像 word0..59（含网关中继的视觉块 56..59）；尾序号 word63 单独写
      await client.writeRegisters(map.command.baseAddress, commandWords.slice(0, 60));
      await client.writeRegisters(
        map.command.baseAddress + map.command.header.tailSequence,
        [commandWords[map.command.header.tailSequence]],
      );
      const result = await client.readHoldingRegisters(
        map.status.baseAddress,
        map.protocol.imageWords,
      );
      pollCount += 1;
      lastSuccessAt = Date.now();
      try {
        store.ingestStatusWords(result.data);
        lastError = null;
      } catch (dataError) {
        // 数据/协议错误（如 PLC 状态映射缺失导致 magic/version 不匹配）：
        // 保留 TCP 连接并记录，避免每周期断开重连；状态仍按离线处理。
        errorCount += 1;
        lastError = dataError && dataError.message ? dataError.message : String(dataError);
      }
    } catch (error) {
      connected = false;
      errorCount += 1;
      lastError = error && error.message ? error.message : String(error);
      onError(error);
      onDisconnected();
      try {
        client.close(() => {});
      } catch {
        /* ignore */
      }
    } finally {
      pollInFlight = false;
    }
  }

  function start() {
    if (timer) return;
    closed = false;
    timer = setInterval(() => {
      pollOnce().catch((error) => onError(error));
    }, pollMs);
    pollOnce().catch((error) => onError(error));
  }

  function close() {
    closed = true;
    clearInterval(timer);
    timer = null;
    connected = false;
    connecting = false;
    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        resolve();
      };
      const watchdog = setTimeout(finish, 250);
      try {
        client.close(() => {
          clearTimeout(watchdog);
          finish();
        });
      } catch {
        clearTimeout(watchdog);
        finish();
      }
      try {
        if (client._port && typeof client._port.destroy === 'function') {
          client._port.destroy();
        }
      } catch {
        /* ignore */
      }
    });
  }

  return {
    start,
    close,
    getDiagnostics() {
      return {
        connected,
        connecting,
        pollCount,
        errorCount,
        lastSuccessAt,
        lastError,
        host,
        port,
        unitID,
        pollMs,
      };
    },
    get connected() {
      return connected;
    },
  };
}

module.exports = { createModbusMaster };
