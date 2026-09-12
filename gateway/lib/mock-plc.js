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
    posM1: 0,
    posM2: 0,
    velCmdM1: 0,
    velCmdM2: 0,
    velActM1: 0,
    velActM2: 0,
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

    state.velCmdM1 = 0;
    state.velCmdM2 = 0;
    if (safe && !req.HMI_xStop && state.eOpMode === 0 && !homeBusy) {
      const trim = Math.max(-0.2, Math.min(0.2,
        Number(req.HMI_rKpTrack || 0) * Number(req.HMI_rHeadingErr || 0)));
      if (req.HMI_xJogXPos) {
        const v = Number(req.HMI_rJogVelX || 0);
        state.velCmdM1 = v + trim;
        state.velCmdM2 = v - trim;
      } else if (req.HMI_xJogXNeg) {
        const v = -Number(req.HMI_rJogVelX || 0);
        state.velCmdM1 = v + trim;
        state.velCmdM2 = v - trim;
      } else if (req.HMI_xSpinLeft) {
        const v = Number(req.HMI_rSpinVel || 0);
        state.velCmdM1 = v;
        state.velCmdM2 = -v;
      } else if (req.HMI_xSpinRight) {
        const v = Number(req.HMI_rSpinVel || 0);
        state.velCmdM1 = -v;
        state.velCmdM2 = v;
      }
      state.posM1 += state.velCmdM1 * dt;
      state.posM2 += state.velCmdM2 * dt;
      if (req.HMI_xJogYPos) state.posY += Number(req.HMI_rJogVelY || 0) * dt;
      if (req.HMI_xJogYNeg) state.posY -= Number(req.HMI_rJogVelY || 0) * dt;
      if (req.HMI_xJogZPos) state.posZ += Number(req.HMI_rJogVelZ || 0) * dt;
      if (req.HMI_xJogZNeg) state.posZ -= Number(req.HMI_rJogVelZ || 0) * dt;
      if (state.homedZ) state.posZ = Math.max(-0.7, Math.min(0, state.posZ));
      if (req.HMI_xJogRPos) state.posR += Number(req.HMI_rJogVelR || 0) * dt;
      if (req.HMI_xJogRNeg) state.posR -= Number(req.HMI_rJogVelR || 0) * dt;
    }

    // 0.63 mock: actual velocity ramps toward command (first-order, ~6 m/s^2)
    const velRamp = 6 * Math.max(0, dt);
    state.velActM1 += Math.max(-velRamp, Math.min(velRamp, state.velCmdM1 - state.velActM1));
    state.velActM2 += Math.max(-velRamp, Math.min(velRamp, state.velCmdM2 - state.velActM2));

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
    const safe = Boolean(req.HMI_xEStop) && !state.estopLatch;
    const directMode = (axis) => Number(req[`HMI_iDirectMode${axis}`]) || 0;
    const directActive = (axis) => directMode(axis) !== 0;
    const directVel = (axis) => (directMode(axis) === 1
      ? Number(req[`HMI_rDirectVel${axis}`]) || 0
      : 0);
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
      HMI_rForceSetEcho: Number(req.HMI_rForceSet) || 0,
      HMI_xHomedY: state.homedY,
      HMI_xHomedZ: state.homedZ,
      HMI_xHomedR: state.homedR,
      HMI_xHomeBusyY: state.homeBusyY,
      HMI_xHomeBusyZ: state.homeBusyZ,
      HMI_xHomeBusyR: state.homeBusyR,
      Tcp_xConnected: true,
      Tcp_xTimeout: false,
      AxisFb_rPosM1: state.posM1,
      AxisFb_rPosM2: state.posM2,
      AxisFb_rPosY: state.posY,
      AxisFb_rPosZ: state.posZ,
      AxisFb_rPosR: state.posR,
      AxisFb_rVelCmdM1: state.velCmdM1,
      AxisFb_rVelCmdM2: state.velCmdM2,
      AxisFb_rVelActM1: state.velActM1,
      AxisFb_rVelActM2: state.velActM2,
      AxisFb_rVelActY: directVel('Y'),
      AxisFb_rVelActZ: directVel('Z'),
      AxisFb_rVelActR: directVel('R'),
      Direct_rVelM1Act: state.velActM1,
      Direct_rVelM2Act: state.velActM2,
      Direct_xActive: false,
      Direct_xOnline: false,
      Direct_xEnable: Boolean(req.HMI_xDirectEnable),
      Direct_wSeqEcho: 0,
      Direct2_xActiveX: directActive('X'),
      Direct2_xActiveY: directActive('Y'),
      Direct2_xActiveZ: directActive('Z'),
      Direct2_xActiveR: directActive('R'),
      Direct2_xOnline: Number(req.HMI_wDirectSeq) > 0,
      Direct2_xSafe: safe,
      Direct2_wSeqEcho: Number(req.HMI_wDirectSeq) || 0,
      AxisFb_xMovingM1: Math.abs(state.velActM1) > 0.01,
      AxisFb_xMovingM2: Math.abs(state.velActM2) > 0.01,
      AxisFb_xPoweredM1: safe,
      AxisFb_xPoweredM2: safe,
      AxisFb_xSyncWarn: false,
      AxisFb_xSyncFault: false,
      AxisFb_rSyncErr: state.posM1 - state.posM2,
      AxisFb_xHomedY: state.homedY,
      AxisFb_xHomedZ: state.homedZ,
      AxisFb_xHomedR: state.homedR,
      AxisFb_xReady: true,
      AxisFb_xFaultM1: false,
      AxisFb_xFaultM2: false,
      AxisFb_xFaultY: false,
      AxisFb_xFaultZ: false,
      AxisFb_xFaultR: false,
      Force_xCommOk: true,
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
