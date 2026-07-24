'use strict';

const map = require('../../config/modbus-map.json');

const commandKeys = new Set(map.command.fields.map((field) => field.name));
const MOCK_COMMAND_DEFAULTS = Object.freeze({
  HMI_xEStop: true,
  HMI_xStop: false,
  HMI_rJogVelX: 0.4,
  HMI_rSpinVel: 0.3,
  HMI_rJogVelY: 0.3,
  HMI_rJogVelZ: 0.2,
  HMI_rJogVelR: 0.2,
  HMI_rAutoDistX: 1,
  HMI_rAutoVelX: 0.4,
  HMI_rAutoVelY: 0.3,
  HMI_rAutoVelZ: 0.15,
  HMI_rWheelBase: 5,
  HMI_rForceSet: 100,
  HMI_iAutoPasses: 1,
  HMI_xForceSimEnable: true,
  HMI_rForceSim: 0,
});

function createMockPlc(initialCommands = {}) {
  const req = { ...MOCK_COMMAND_DEFAULTS, ...initialCommands };
  const state = {
    eDevState: 0,
    eOpMode: 0,
    iAutoStep: 0,
    autoBusy: false,
    autoDone: false,
    forceShow: 0,
    alarm: 0,
    estopLatch: false,
    autoStartPrev: false,
    posY: 0,
    posZ: 0,
    posR: 0,
    homedY: false,
    homedZ: false,
    homedR: false,
    homeBusyY: false,
    homeBusyZ: false,
    homeBusyR: false,
  };

  function applyWrite(message) {
    for (const [key, value] of Object.entries(message || {})) {
      if (commandKeys.has(key)) req[key] = value;
    }
  }

  function tick(dt) {
    if (!req.HMI_xEStop) state.estopLatch = true;
    if (req.HMI_xStopHold3s) {
      state.estopLatch = false;
      state.iAutoStep = 0;
      state.autoBusy = false;
    }
    const safe = Boolean(req.HMI_xEStop) && !state.estopLatch;
    if (!safe) state.eDevState = 2;
    else if (req.HMI_xStop) state.eDevState = 0;
    else state.eDevState = 1;

    state.eOpMode = req.HMI_xAutoMode ? 1 : 0;
    if (req.HMI_xForceSimEnable) state.forceShow = Number(req.HMI_rForceSim) || 0;

    const homeBusy = state.homeBusyY || state.homeBusyZ || state.homeBusyR;
    const trigY = req.HMI_xHomeY || (req.HMI_iHomeAxis === 1 && req.HMI_xHomeExec);
    const trigZ = req.HMI_xHomeZ || (req.HMI_iHomeAxis === 2 && req.HMI_xHomeExec);
    const trigR = req.HMI_xHomeR || (req.HMI_iHomeAxis === 3 && req.HMI_xHomeExec);
    if (!safe || req.HMI_xStop) {
      state.homeBusyY = state.homeBusyZ = state.homeBusyR = false;
    } else if (state.eOpMode === 0 && !homeBusy) {
      if (trigY && !state.homeYPrev) {
        state.homeBusyY = true;
        state.homedY = false;
      } else if (trigZ && !state.homeZPrev) {
        state.homeBusyZ = true;
        state.homedZ = false;
      } else if (trigR && !state.homeRPrev) {
        state.homeBusyR = true;
        state.homedR = false;
      }
    }
    state.homeYPrev = Boolean(trigY);
    state.homeZPrev = Boolean(trigZ);
    state.homeRPrev = Boolean(trigR);

    if (state.homeBusyY) {
      state.posY = 0;
      state.homedY = true;
      state.homeBusyY = false;
    }
    if (state.homeBusyZ) {
      state.posZ = 0;
      state.homedZ = true;
      state.homeBusyZ = false;
    }
    if (state.homeBusyR) {
      state.posR = 0;
      state.homedR = true;
      state.homeBusyR = false;
    }

    if (safe && !req.HMI_xStop && state.eOpMode === 0 && !homeBusy) {
      if (req.HMI_xJogYPos) state.posY += Number(req.HMI_rJogVelY || 0) * dt;
      if (req.HMI_xJogYNeg) state.posY -= Number(req.HMI_rJogVelY || 0) * dt;
      if (req.HMI_xJogZPos) state.posZ += Number(req.HMI_rJogVelZ || 0) * dt;
      if (req.HMI_xJogZNeg) state.posZ -= Number(req.HMI_rJogVelZ || 0) * dt;
      if (state.homedZ) state.posZ = Math.max(-0.7, Math.min(0, state.posZ));
      if (req.HMI_xJogRPos) state.posR += Number(req.HMI_rJogVelR || 0) * dt;
      if (req.HMI_xJogRNeg) state.posR -= Number(req.HMI_rJogVelR || 0) * dt;
    }

    const autoEdge = req.HMI_xAutoStart && !state.autoStartPrev;
    state.autoStartPrev = Boolean(req.HMI_xAutoStart);
    if (req.HMI_xAutoAbort || !safe || req.HMI_xStop) {
      state.autoBusy = false;
      state.iAutoStep = 0;
    } else if (autoEdge && state.eOpMode === 1) {
      state.iAutoStep = 1;
      state.autoBusy = true;
      state.autoDone = false;
    } else if (state.autoBusy) {
      state.iAutoStep += 0.4 * Math.max(0, dt);
      if (state.iAutoStep >= 5) {
        state.autoBusy = false;
        state.autoDone = true;
        state.iAutoStep = 0;
      }
    }
  }

  function statusMessage() {
    return {
      t: 's',
      Tcp_iCommStatus: 2,
      HMI_eDevState: state.eDevState,
      HMI_eOpMode: state.eOpMode,
      HMI_iAlarmShow: state.eDevState === 2 ? 1001 : state.alarm,
      HMI_iAutoStepShow: Math.floor(state.iAutoStep),
      HMI_xDevStop: state.eDevState === 0,
      HMI_xDevRun: state.eDevState === 1,
      HMI_xDevError: state.eDevState === 2,
      HMI_xLampEStop: state.estopLatch || !req.HMI_xEStop,
      HMI_xLampEnableOk: state.eDevState === 1,
      HMI_xLampFault: state.eDevState === 2,
      HMI_xAutoBusy: state.autoBusy,
      HMI_xAutoDone: state.autoDone,
      HMI_rForceShow: state.forceShow,
      HMI_xHomedY: state.homedY,
      HMI_xHomedZ: state.homedZ,
      HMI_xHomedR: state.homedR,
      HMI_xHomeBusyY: state.homeBusyY,
      HMI_xHomeBusyZ: state.homeBusyZ,
      HMI_xHomeBusyR: state.homeBusyR,
      Tcp_xConnected: true,
      Tcp_xTimeout: false,
      AxisFb_rPosY: state.posY,
      AxisFb_rPosZ: state.posZ,
      AxisFb_rPosR: state.posR,
      AxisFb_xHomedY: state.homedY,
      AxisFb_xHomedZ: state.homedZ,
      AxisFb_xHomedR: state.homedR,
      AxisFb_xReady: true,
    };
  }

  return {
    applyWrite,
    getCommandValues: () => ({ ...req }),
    statusMessage,
    tick,
  };
}

module.exports = { MOCK_COMMAND_DEFAULTS, createMockPlc };
