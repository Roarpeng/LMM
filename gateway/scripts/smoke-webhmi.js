'use strict';
/**
 * smoke-webhmi.js — 本地 Mock 冒烟：起 Gateway(Mock) -> 校验页面/health/map/WS 新字段。
 * 用法: cd gateway && MOCK_PLC=1 node scripts/smoke-webhmi.js [port]
 */
const { startGateway } = require('../server.js');
const WebSocket = require('ws');

const port = String(process.argv[2] || 8097);
const gateway = startGateway({ MOCK_PLC: '1', HTTP_PORT: port });
const base = 'http://127.0.0.1:' + port;

function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

(async () => {
  await delay(400);
  const index = await fetch(base + '/');
  const html = await index.text();
  const health = await (await fetch(base + '/health')).json();
  const map = await (await fetch(base + '/map')).json();
  const required = [
    'AxisFb_rVelActM1', 'AxisFb_rVelActM2', 'AxisFb_rSyncErr', 'AxisFb_xSyncFault',
    'AxisFb_rVelActY', 'AxisFb_rVelActZ', 'AxisFb_rVelActR',
    'Direct2_xActiveX', 'Direct2_xActiveY', 'Direct2_xActiveZ', 'Direct2_xActiveR',
    'Direct2_xOnline', 'Direct2_xSafe', 'Direct2_wSeqEcho', 'HMI_rForceSetEcho',
    'Force_rPeak', 'Force_wRaw',
  ];
  const mapOk = required.every((n) => map.status.fields.some((f) => f.name === n));
  console.log('[smoke] index', index.status, html.length + 'B',
    'tabs=' + html.includes('data-tab="xdual"'), 'regtable=' + html.includes('id="regtable"'));
  console.log('[smoke] health', JSON.stringify(health));
  console.log('[smoke] map new status fields present:', mapOk);

  const ws = new WebSocket('ws://127.0.0.1:' + port);
  const got = { hello: false, status: false, actFields: false, lease: false, wack: false, err: null };
  ws.on('message', (raw) => {
    const m = JSON.parse(String(raw));
    if (m.t === 'hello') got.hello = true;
    if (m.t === 'lease') got.lease = true;
    if (m.t === 'wack') got.wack = true;
    if (m.t === 'err') got.err = m.code;
    if (m.t === 's') {
      got.status = true;
      if ('AxisFb_rVelActM1' in m && 'AxisFb_rVelActM2' in m && 'AxisFb_rSyncErr' in m
          && 'AxisFb_rVelActY' in m && 'AxisFb_rVelActZ' in m && 'AxisFb_rVelActR' in m
          && 'Direct2_xActiveX' in m && 'Direct2_xOnline' in m
          && 'Direct2_wSeqEcho' in m && 'HMI_rForceSetEcho' in m
          && 'Force_rPeak' in m && 'Force_wRaw' in m) got.actFields = true;
    }
  });
  await new Promise((resolve) => ws.once('open', resolve));
  ws.send(JSON.stringify({ t: 'w', HMI_xJogXPos: true, HMI_rJogVelX: 0.4 }));
  await delay(350);
  ws.send(JSON.stringify({ t: 'ping' }));
  await delay(150);
  console.log('[smoke] ws', JSON.stringify(got));
  ws.close();
  const ok = index.status === 200 && mapOk && got.hello && got.status && got.actFields && got.wack;
  console.log(ok ? '[smoke] PASS' : '[smoke] FAIL');
  gateway.close(() => process.exit(ok ? 0 : 1));
})().catch((error) => { console.error(error); process.exit(1); });
