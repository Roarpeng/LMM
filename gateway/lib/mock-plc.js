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

// 0.80 外部工步：与 plc/g/PRG_Logic.st 同语义的离线模拟（不是 PLC 本身，验收见 docs/plc/STEP_MODE.md）
const STEP_LIMITS = Object.freeze({
  velMaxX: 0.5, velMaxY: 0.5, velMaxZ: 0.2, velMaxR: 30, // Cfg_rDirectVelMax*
  yNeg: 0, yPos: 6, zNeg: -0.7, zPos: 0, rNeg: -180, rPos: 180, // Cfg_rLim*
  phaseMax: 0.01, headingDeadband: 0.003, // Cfg_rPhaseMax / FB_XDual 死区
  forceDeadband: 0.5, // FB_ForceFollow
  heartbeatS: 0.3, // Cfg_tDirectTimeout
});
const STEP_ERR = Object.freeze({
  MODE: 1, PARAM: 2, LIMIT: 3, BUSY: 4, TIMEOUT: 10, SAFETY: 11, HEARTBEAT: 12, NO_CONTACT: 20,
});

function approach(value, target, maxStep) {
  const delta = target - value;
  if (Math.abs(delta) <= maxStep) return target;
  return value + Math.sign(delta) * maxStep;
}

/**
 * @param {object} initialCommands 初始命令镜像
 * @param {object} options groundZ：地面接触高度(m，Z 向下为负)；stiffness：接触刚度 N/m。
 *   力 = 力模拟值(HMI_xForceSimEnable 时) + 接触力 max(0, groundZ − Z)·stiffness。
 */
function createMockPlc(initialCommands = {}, options = {}) {
  const groundZ = Number.isFinite(options.groundZ) ? options.groundZ : -0.3;
  const stiffness = Number.isFinite(options.stiffness) ? options.stiffness : 4000;
  const req = { ...MOCK_COMMAND_DEFAULTS, ...initialCommands };
  const state = {
    clock: 0,
    seqSeenAt: null,
    step: {
      modePrev: false, idPrev: 0, idEcho: 0, cmdEcho: 0, state: 0, err: 0, phase: 0,
      latched: null, startedAt: 0, elapsed: 0, timeout: 0, progress: 0, startX: 0, startY: 0,
      forceKeep: false, forceReached: false, forceLow: false, forceFollow: false, rHold: 0,
      rHoldActive: false, tareAt: null, reachedSince: null, noContactSince: null, inPosSince: null,
    },
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
      if (!commandKeys.has(key)) continue;
      if (key === 'HMI_wDirectSeq' && value !== req.HMI_wDirectSeq) state.seqSeenAt = state.clock;
      req[key] = value;
    }
  }

  function heartbeatOnline() {
    return state.seqSeenAt !== null && state.clock - state.seqSeenAt <= STEP_LIMITS.heartbeatS;
  }

  function rawForce() {
    const sim = req.HMI_xForceSimEnable ? Number(req.HMI_rForceSim) || 0 : 0;
    return sim + Math.max(0, groundZ - state.posZ) * stiffness;
  }

  function currentForce() {
    return rawForce() - (state.forceTare || 0);
  }

  function validateStep(L) {
    const lim = STEP_LIMITS;
    const selY = (L.flags & 1) !== 0;
    const selZ = (L.flags & 2) !== 0;
    const selR = (L.flags & 4) !== 0;
    if (L.cmd === 1) {
      if (Math.abs(L.dist) < 0.001 || L.vel <= 0 || L.vel > lim.velMaxX) return STEP_ERR.PARAM;
    } else if (L.cmd === 2 || L.cmd === 3) {
      if (L.force <= 0 || L.kp <= 0 || L.velZ <= 0 || L.velZ > lim.velMaxZ) return STEP_ERR.PARAM;
      if (L.cmd === 3) {
        if (Math.abs(L.dist) < 0.001 || L.vel <= 0 || L.vel > lim.velMaxY) return STEP_ERR.PARAM;
        const target = state.posY + L.dist;
        if (target > lim.yPos || target < lim.yNeg) return STEP_ERR.LIMIT;
      }
    } else if (L.cmd === 4) {
      if (!(selY || selZ || selR)) return STEP_ERR.PARAM;
      if ((selY || selZ) && L.vel <= 0) return STEP_ERR.PARAM;
      if (selY && L.vel > lim.velMaxY) return STEP_ERR.PARAM;
      if (selZ && L.vel > lim.velMaxZ) return STEP_ERR.PARAM;
      if (selR && (L.velR <= 0 || L.velR > lim.velMaxR)) return STEP_ERR.PARAM;
      if (selY && (L.posY > lim.yPos || L.posY < lim.yNeg)) return STEP_ERR.LIMIT;
      if (selZ && (L.posZ > lim.zPos || L.posZ < lim.zNeg)) return STEP_ERR.LIMIT;
      if (selR && (L.posR > lim.rPos || L.posR < lim.rNeg)) return STEP_ERR.LIMIT;
    } else {
      return STEP_ERR.PARAM;
    }
    return 0;
  }

  // 与 PRG_Logic.st 0.80 工步段同序：模式沿 → 新命令(锁存/校验) → 监视 → 执行 → 输出
  function stepTick(dt, safe) {
    const st = state.step;
    const active = state.eOpMode === 2;
    const online = heartbeatOnline();
    const ok = safe && !req.HMI_xStop && online;
    st.forceFollow = false;
    if (active && !st.modePrev) {
      st.idPrev = Number(req.HMI_wStepId) || 0;
      st.idEcho = st.idPrev;
      st.cmdEcho = 0;
      st.state = 0;
      st.err = 0;
      st.phase = 0;
      st.forceKeep = false;
      st.rHold = state.posR;
    }
    st.modePrev = active;
    if (!active) {
      if (st.state === 1) {
        st.state = 3;
        st.err = STEP_ERR.MODE;
      }
      st.forceKeep = false;
      st.rHoldActive = false;
      return;
    }

    const id = Number(req.HMI_wStepId) || 0;
    if (id !== st.idPrev) {
      st.idPrev = id;
      const L = {
        cmd: Number(req.HMI_iStepCmd) || 0,
        flags: Number(req.HMI_wStepFlags) || 0,
        dist: Number(req.HMI_rStepDist) || 0,
        vel: Number(req.HMI_rStepVel) || 0,
        velR: Number(req.HMI_rStepVelR) || 0,
        posY: Number(req.HMI_rStepPosY) || 0,
        posZ: Number(req.HMI_rStepPosZ) || 0,
        posR: Number(req.HMI_rStepPosR) || 0,
        force: Number(req.HMI_rStepForce) || 0,
        kp: Number(req.HMI_rStepKpForce) || 0,
        velZ: Number(req.HMI_rStepVelZMax) || 0,
        timeout: Number(req.HMI_rStepTimeout) || 0,
      };
      let errNew = 0;
      if (st.state === 1 && L.cmd !== 0) errNew = STEP_ERR.BUSY;
      else if (L.cmd === 0) errNew = 0;
      else if (!online) errNew = STEP_ERR.HEARTBEAT;
      else if (!ok) errNew = STEP_ERR.SAFETY;
      else errNew = validateStep(L);
      st.latched = L;
      st.idEcho = id;
      st.cmdEcho = L.cmd;
      st.phase = 0;
      st.forceKeep = false;
      st.forceReached = false;
      st.forceLow = false;
      st.progress = 0;
      st.elapsed = 0;
      st.startedAt = state.clock;
      st.startX = (state.posM1 + state.posM2) / 2;
      st.startY = state.posY;
      st.tareAt = null;
      st.reachedSince = null;
      st.noContactSince = null;
      st.inPosSince = null;
      if (L.cmd === 0) {
        st.state = 2;
        st.err = 0;
      } else if (errNew) {
        st.state = 3;
        st.err = errNew;
      } else {
        st.state = 1;
        st.err = 0;
        st.timeout = L.timeout > 0 ? L.timeout
          : (L.cmd === 1 || L.cmd === 3 ? Math.abs(L.dist) / L.vel * 2 + 5 : 60);
      }
    }

    if (st.state === 1) {
      st.elapsed = Math.min(state.clock - st.startedAt, 3000);
      if (!online) {
        st.state = 3;
        st.err = STEP_ERR.HEARTBEAT;
      } else if (!ok) {
        st.state = 3;
        st.err = STEP_ERR.SAFETY;
      } else if (st.elapsed > st.timeout) {
        st.state = 3;
        st.err = STEP_ERR.TIMEOUT;
      }
    }
    if (!ok) st.forceKeep = false;

    const L = st.latched;
    const selR = L && L.cmd === 4 && (L.flags & 4) !== 0;
    if (st.state === 1) {
      const phaseElapsed = state.clock - st.startedAt;
      if (L.cmd === 1) {
        // X 走距：基速 ± 航向 trim（死区 + 钳位，与 FB_XDual eMode=1 同律）
        const base = Math.sign(L.dist) * L.vel;
        const e = Number(req.HMI_rHeadingErr) || 0;
        let trim = 0;
        if (Math.abs(e) > STEP_LIMITS.headingDeadband) {
          trim = (e - Math.sign(e) * STEP_LIMITS.headingDeadband) * (Number(req.HMI_rKpTrack) || 0);
          trim = Math.max(-STEP_LIMITS.phaseMax, Math.min(STEP_LIMITS.phaseMax, trim));
        }
        state.velCmdM1 = base + trim;
        state.velCmdM2 = base - trim;
        state.posM1 += state.velCmdM1 * dt;
        state.posM2 += state.velCmdM2 * dt;
        st.progress = Math.abs((state.posM1 + state.posM2) / 2 - st.startX);
        if (phaseElapsed >= 0.1 && st.progress >= Math.abs(L.dist)) {
          state.velCmdM1 = 0;
          state.velCmdM2 = 0;
          st.state = 2;
        }
      } else if (L.cmd === 2) {
        const tare = (L.flags & 8) !== 0;
        if (tare && st.tareAt === null) {
          st.tareAt = state.clock;
          state.forceTare = rawForce(); // 去皮：以当前读数为零
        }
        if (!tare || state.clock - st.tareAt >= 0.3) {
          st.phase = 1;
          st.forceFollow = true;
        }
      } else if (L.cmd === 3) {
        st.forceFollow = true;
        state.posY = approach(state.posY, st.startY + L.dist, L.vel * dt);
        st.progress = Math.abs(state.posY - st.startY);
        if (phaseElapsed >= 0.1 && Math.abs(state.posY - (st.startY + L.dist)) < 1e-6) {
          st.forceKeep = true;
          st.state = 2;
        }
      } else if (L.cmd === 4) {
        if (st.phase === 0) {
          st.phase = 1;
        } else {
          if (L.flags & 1) state.posY = approach(state.posY, L.posY, L.vel * dt);
          if (L.flags & 2) state.posZ = approach(state.posZ, L.posZ, L.vel * dt);
          if (L.flags & 4) state.posR = approach(state.posR, L.posR, L.velR * dt);
          const inPos = (!(L.flags & 1) || Math.abs(state.posY - L.posY) < 0.001)
            && (!(L.flags & 2) || Math.abs(state.posZ - L.posZ) < 0.001)
            && (!(L.flags & 4) || Math.abs(state.posR - L.posR) < 0.1);
          if (inPos && st.inPosSince === null) st.inPosSince = state.clock;
          if (!inPos) st.inPosSince = null;
          if (st.inPosSince !== null && state.clock - st.inPosSince >= 0.05) {
            if (L.flags & 4) st.rHold = L.posR;
            st.state = 2;
          }
        }
      }
    }
    if (st.forceKeep && st.state === 2) st.forceFollow = true;
    st.rHoldActive = !(st.state === 1 && selR);
    if (st.rHoldActive) state.posR = st.rHold;

    // Z 力跟随（FB_ForceFollow：vZ = −Kp·(F − F_act)，限速、死区、软限位）
    if (st.forceFollow && L) {
      const errF = L.force - currentForce();
      let vZ = Math.abs(errF) < STEP_LIMITS.forceDeadband ? 0 : -L.kp * errF;
      vZ = Math.max(-L.velZ, Math.min(L.velZ, vZ));
      state.posZ = Math.max(STEP_LIMITS.zNeg, Math.min(STEP_LIMITS.zPos, state.posZ + vZ * dt));
    }
    if (L && L.cmd === 3 && st.state === 1) {
      st.forceReached = currentForce() >= L.force - STEP_LIMITS.forceDeadband;
      st.forceLow = currentForce() < 0.8 * L.force;
    }
    if (st.state === 1 && L.cmd === 2 && st.phase === 1) {
      const after = currentForce();
      if (after >= L.force - STEP_LIMITS.forceDeadband) { // 死区内即到力（同 ST）
        if (st.reachedSince === null) st.reachedSince = state.clock;
      } else {
        st.reachedSince = null;
      }
      const atBottom = state.posZ <= STEP_LIMITS.zNeg + 0.001 && after < L.force - STEP_LIMITS.forceDeadband;
      if (atBottom && st.noContactSince === null) st.noContactSince = state.clock;
      if (!atBottom) st.noContactSince = null;
      if (st.reachedSince !== null && state.clock - st.reachedSince >= 0.1) {
        st.forceReached = true;
        st.forceKeep = true;
        st.state = 2;
      } else if (st.noContactSince !== null && state.clock - st.noContactSince >= 0.3) {
        st.forceFollow = false;
        st.state = 3;
        st.err = STEP_ERR.NO_CONTACT;
      }
    }
  }

  function tick(dt) {
    state.clock += Math.max(0, dt);
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

    if (req.HMI_xAutoMode) state.eOpMode = 1;
    else if (req.HMI_xStepMode) state.eOpMode = 2;
    else state.eOpMode = 0;
    // 力 = 模拟值(若启用) + 地面接触力 − 去皮
    state.forceShow = currentForce();
    if (req.HMI_xForcePeakReset) state.forcePeak = 0;
    state.forcePeak = Math.max(state.forcePeak || 0, Math.abs(state.forceShow || 0));

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

    stepTick(dt, safe);
    state.forceShow = currentForce();

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
      // 0.80：回显实际下发给力跟随的 F（工步力跟随时为锁存值）
      HMI_rForceSetEcho: state.step.forceFollow && state.step.latched
        ? state.step.latched.force : Number(req.HMI_rForceSet) || 0,
      Force_rPeak: state.forcePeak || 0,
      Force_wRaw: Math.max(0, Math.min(65535, Math.round((state.forceShow || 0) * 51.2 + 8192))),
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
      AxisFb_rTorqueM1: state.torqueM1 || 0,
      AxisFb_rTorqueM2: state.torqueM2 || 0,
      AxisFb_rCurrentM1: state.currentM1 || 0,
      AxisFb_rCurrentM2: state.currentM2 || 0,
      AxisFb_xParamErr: false,
      AxisFb_wSwM1: 0x0637, AxisFb_wErrM1: 0, AxisFb_wTqMaxM1: 3000, AxisFb_wLimPM1: 3000, AxisFb_wLimNM1: 3000,
      AxisFb_wSwM2: 0x0637, AxisFb_wErrM2: 0, AxisFb_wTqMaxM2: 3000, AxisFb_wLimPM2: 3000, AxisFb_wLimNM2: 3000,
      AxisFb_wModeM1: 9, AxisFb_wTq03M1: 3000, AxisFb_wTq04M1: 3000, AxisFb_wTq05M1: 3000, AxisFb_wTq06M1: 3000,
      AxisFb_wModeM2: 9, AxisFb_wTq03M2: 3000, AxisFb_wTq04M2: 3000, AxisFb_wTq05M2: 3000, AxisFb_wTq06M2: 3000,
      AxisFb_xModeCsvM1: true, AxisFb_xModeCsvErrM1: false, AxisFb_xModeCsvM2: true, AxisFb_xModeCsvErrM2: false,
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
      Direct2_xOnline: heartbeatOnline(),
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
      // 0.80 外部工步
      Step_wIdEcho: state.step.idEcho,
      Step_iCmdEcho: state.step.cmdEcho,
      Step_iState: state.step.state,
      Step_iErr: state.step.err,
      Step_iPhase: state.step.phase,
      Step_xModeActive: state.eOpMode === 2,
      Step_xForceFollow: state.step.forceFollow,
      Step_xForceReached: state.step.forceReached,
      Step_xForceLow: state.step.forceLow,
      Step_xRHold: state.eOpMode === 2 && state.step.rHoldActive,
      Step_rProgress: state.step.progress,
      Step_rKpForceEcho: state.step.latched ? state.step.latched.kp : 0,
      Step_rRHoldPos: state.step.rHold,
      Step_rElapsed: state.step.elapsed,
      AxisFb_xStandstillY: true,
      AxisFb_xStandstillZ: true,
      AxisFb_xStandstillR: true,
    };
  }

  return {
    applyWrite,
    getCommandValues: () => ({ ...req }),
    statusMessage,
    tick,
  };
}

module.exports = { MOCK_COMMAND_DEFAULTS, STEP_ERR, STEP_LIMITS, createMockPlc };
