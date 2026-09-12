#!/usr/bin/env node
'use strict';

/*
 * Minimal DOM stub that boots web/live/app.js in Node to prove the page
 * initializes without throwing. No dependencies, no browser.
 *
 *   node tools/dom-stub-check.js
 */

const fs = require('node:fs');
const path = require('node:path');

const liveDir = path.join(__dirname, '..', 'web', 'live');
const indexHtml = fs.readFileSync(path.join(liveDir, 'index.html'), 'utf8');
const appJs = fs.readFileSync(path.join(liveDir, 'app.js'), 'utf8');
const ids = Array.from(indexHtml.matchAll(/id="([^"]+)"/g), (m) => m[1]);

const errors = [];
function fail(where, error) {
  errors.push(where + ': ' + ((error && error.stack) || error));
}

/* ---------- canvas 2d context stub ---------- */
function makeCtx() {
  const noop = () => {};
  return new Proxy({
    canvas: null,
    setTransform: noop,
    clearRect: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    stroke: noop,
    fill: noop,
    fillText: noop,
    setLineDash: noop,
    measureText: () => ({ width: 0 }),
    save: noop,
    restore: noop,
    translate: noop,
    rotate: noop,
  }, { get: (t, k) => (k in t ? t[k] : undefined), set: (t, k, v) => { t[k] = v; return true; } });
}

/* ---------- element stub ---------- */
let elSeq = 0;
function makeEl(tag) {
  const el = {
    tagName: String(tag || 'div').toUpperCase(),
    _id: ++elSeq,
    children: [],
    parentNode: null,
    className: '',
    textContent: '',
    innerHTML: '',
    value: '',
    checked: false,
    disabled: false,
    dataset: {},
    style: {},
    clientWidth: 900,
    clientHeight: 220,
    width: 900,
    height: 220,
    scrollTop: 0,
    _listeners: {},
    classList: {
      add() {}, remove() {}, toggle() {}, contains() { return false; },
    },
    addEventListener(ev, fn) { (el._listeners[ev] = el._listeners[ev] || []).push(fn); },
    removeEventListener() {},
    dispatch(ev, arg) { (el._listeners[ev] || []).forEach((fn) => fn(arg || {})); },
    appendChild(child) { child.parentNode = el; el.children.push(child); return child; },
    prepend(child) { child.parentNode = el; el.children.unshift(child); return child; },
    removeChild(child) {
      const i = el.children.indexOf(child);
      if (i >= 0) el.children.splice(i, 1);
      return child;
    },
    remove() { if (el.parentNode) el.parentNode.removeChild(el); },
    setAttribute(k, v) { el[k] = v; },
    getAttribute(k) { return el[k]; },
    querySelector() { return makeEl('span'); },
    querySelectorAll() { return []; },
    getContext() { return ctx; },
    click() {},
    focus() {},
    setSelectionRange() {},
  };
  const ctx = makeCtx();
  ctx.canvas = el;
  Object.defineProperty(el, 'lastChild', { get: () => el.children[el.children.length - 1] || null });
  Object.defineProperty(el, 'firstChild', { get: () => el.children[0] || null });
  return el;
}

const idStore = new Map(ids.map((id) => [id, makeEl('div')]));

const documentStub = {
  getElementById(id) {
    if (!idStore.has(id)) idStore.set(id, makeEl('div'));
    return idStore.get(id);
  },
  createElement(tag) { return makeEl(tag); },
  querySelector(sel) { return sel === '#regtable tbody' ? makeEl('tbody') : null; },
  querySelectorAll() { return []; },
  addEventListener() {},
  body: makeEl('body'),
  documentElement: makeEl('html'),
};

/* ---------- other browser globals ---------- */
const wsInstances = [];
class WebSocketStub {
  constructor(url) {
    this.url = url;
    this.readyState = 1;
    this.sent = [];
    wsInstances.push(this);
  }
  send(data) { this.sent.push(data); }
  close() { this.readyState = 3; }
  terminate() { this.readyState = 3; }
}

const health = {
  ok: true, mode: 'mock', clients: 1, leaseOwner: null, statusIsOffline: false,
  lastValidStatusAgeMs: 42, mock: true,
  master: { connected: true, host: '127.0.0.1', port: 502, unitID: 1, pollMs: 50, errorCount: 0, lastError: null, lastSuccessAt: Date.now() },
  version: '1.0.0', startedAt: Date.now() - 1000, uptimeMs: 1000,
};
const map = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'config', 'modbus-map.json'), 'utf8'));
const fetchStub = (url) => Promise.resolve({ ok: true, json: () => Promise.resolve(String(url).indexOf('/map') === 0 || String(url).indexOf('map') !== -1 ? map : health), text: () => Promise.resolve('') });

const lsStore = new Map();
const localStorageStub = {
  getItem: (k) => (lsStore.has(k) ? lsStore.get(k) : null),
  setItem: (k, v) => { lsStore.set(k, String(v)); },
  removeItem: (k) => { lsStore.delete(k); },
  clear: () => { lsStore.clear(); },
};

let rafSeq = 0;
const winStub = {
  addEventListener() {}, removeEventListener() {}, devicePixelRatio: 2, HMI: undefined,
  requestAnimationFrame(cb) { const id = ++rafSeq; setTimeout(() => cb(performance.now()), 0); return id; },
};

global.document = documentStub;
global.window = winStub;
global.WebSocket = WebSocketStub;
global.fetch = fetchStub;
global.localStorage = localStorageStub;
global.location = { protocol: 'http:', host: '127.0.0.1:8080', href: 'http://127.0.0.1:8080/' };
global.requestAnimationFrame = winStub.requestAnimationFrame;
global.cancelAnimationFrame = () => {};
global.Blob = class Blob { constructor(parts) { this.parts = parts; } };
global.URL.createObjectURL = () => 'blob:stub';
global.URL.revokeObjectURL = () => {};

process.on('uncaughtException', (e) => fail('uncaughtException', e));
process.on('unhandledRejection', (e) => fail('unhandledRejection', e));

/* ---------- boot ---------- */
try {
  require(path.join(liveDir, 'app.js'));
} catch (e) {
  fail('require(app.js)', e);
}

/* ---------- exercise the live path a little ---------- */
try {
  const ws = wsInstances[0];
  if (!ws) fail('boot', 'no WebSocket was created');
  else {
    if (typeof ws.onopen === 'function') ws.onopen();
    const status = {
      t: 's', HMI_eDevState: 1, HMI_eOpMode: 0, HMI_iAlarmShow: 0, HMI_iAutoStepShow: 0,
      HMI_xDevRun: true, HMI_xDevStop: false, HMI_xDevError: false,
      HMI_rForceShow: 12.5, Force_rPeak: 88.8, Force_wRaw: 8832, Force_xCommOk: true,
      AxisFb_rVelCmdM1: 0.1, AxisFb_rVelCmdM2: 0.1, AxisFb_rVelActM1: 0.1, AxisFb_rVelActM2: 0.1,
      AxisFb_rPosM1: 0.1, AxisFb_rPosM2: 0.1, AxisFb_rPosY: 0, AxisFb_rPosZ: 0, AxisFb_rPosR: 0,
      AxisFb_rSyncErr: 0, AxisFb_xReady: true, Direct2_xOnline: true, Direct2_xSafe: true,
      Tcp_iCommStatus: 2, Tcp_xConnected: true, Tcp_xTimeout: false,
    };
    if (typeof ws.onmessage === 'function') ws.onmessage({ data: JSON.stringify(status) });
    if (typeof ws.onmessage === 'function') ws.onmessage({ data: JSON.stringify({ t: 'wack', seq: 1, at: Date.now() }) });
    if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'ping' }));
    if (typeof ws.onclose === 'function') ws.onclose();
  }
  if (global.window.HMI && typeof global.window.HMI.patch === 'function') {
    global.window.HMI.patch({ HMI_rHeadingErr: 0.1, HMI_rKpTrack: 0.5 });
    global.window.HMI.pulse({ HMI_xForcePeakReset: true }, 10);
  }
} catch (e) {
  fail('exercise', e);
}

/* ---------- required test-hook assertions ---------- */
function section(start, end) {
  const a = appJs.indexOf(start);
  const b = appJs.indexOf(end, a + start.length);
  if (a < 0 || b < 0) return '';
  return appJs.slice(a, b);
}
const hookChecks = [
  ['let controlClaimed = false;', 'controlClaimed declaration'],
  ['if (!controlClaimed', 'flush guard'],
  ['controlClaimed = true', 'patch/bindParam claims control'],
  ['controlClaimed = false', 'onclose releases claim'],
  ['apply(r.value, false)', 'bindParam init does not claim'],
  ["addEventListener('input', () => apply(r.value, true))", 'bindParam input claims'],
  ['if (user) { controlClaimed = true', 'bindParam user claim'],
  ['HMI_xForceSimEnable: false', 'force sim default false'],
  ['msg.HMI_xDevStop', 'status pill by name'],
];
for (const [needle, label] of hookChecks) {
  if (appJs.indexOf(needle) === -1) fail('hook', 'missing hook: ' + label);
}
const simInput = indexHtml.match(/<input[^>]+id="force-sim"[^>]*>/);
if (!simInput) fail('hook', 'force-sim input missing');
else if (simInput[0].indexOf('checked') !== -1) fail('hook', 'force-sim must not be checked');
const onOpen = section('ws.onopen = () => {', 'ws.onclose = () => {');
if (onOpen.indexOf("t: 'ping'") === -1 && onOpen.indexOf('t:"ping"') === -1) fail('hook', 'onopen must ping');
if (onOpen.indexOf('flush(') !== -1) fail('hook', 'onopen must not flush');
if (onOpen.indexOf("t: 'w'") !== -1 || onOpen.indexOf('t:"w"') !== -1) fail('hook', 'onopen must not send t:w');

/* ---------- settle timers, then report ---------- */
setTimeout(() => {
  if (errors.length) {
    console.error('DOM stub check FAILED');
    errors.forEach((e) => console.error(' - ' + e));
    process.exit(1);
  }
  console.log('DOM stub check OK - web/live/app.js initialized with ' + ids.length + ' stub ids, ' + wsInstances.length + ' ws instance(s), no errors');
  process.exit(0);
}, 400);
