FUNCTION_BLOCK FB_Servo
(* =============================================================================
   FB_Servo — 单轴原子封装（SM3_Basic）。仅在 PRG_Axis_Control 任务内实例化。

   仲裁优先级：停止/故障 > 回零 > 绝对定位 > 相对定位 > 速度指令 > 点动。
   - 手动点动走 MC_Jog（松开即减速停）；速度指令走 MC_MoveVelocity
   - 运动切换靠 PLCopen 中止机制（新命令 FB 上升沿自动 abort 旧运动）
   - 全部运动请求撤销（松手/速度归零/停止/急停/撞限位）→ MC_Halt 减速停车
   - 硬限位：xLimEn=TRUE 时，所有模式都限制在 [rLimNeg, rLimPos] 内：
     点动/速度 越限方向被禁止；定位目标被夹紧；X 轴传 xLimEn:=FALSE
   ========================================================================== *)
VAR_IN_OUT
    Axis : AXIS_REF_SM3;
END_VAR
VAR_INPUT
    xEnable : BOOL;         (* 驱动器使能（来自 AxisCmd_xPower） *)
    xStop : BOOL;           (* 停止运动（保持使能） *)
    xResetFault : BOOL;     (* 故障复位（上升沿） *)
    xHome : BOOL;           (* 回零（电平，完成/撤销后由上层清） *)
    xMoveAbs : BOOL;        (* 绝对定位（电平保持至完成） *)
    rTargetPos : REAL;      (* 绝对目标位置 *)
    xMoveRel : BOOL;        (* 相对定位（电平保持至完成） *)
    rDist : REAL;           (* 相对距离（可正可负） *)
    xUseVelCmd : BOOL;      (* 速度指令模式（力跟随/X双驱） *)
    rVelCmd : REAL;         (* 速度给定（可正可负；|v|<1e-6 视为撤销） *)
    xJogPos : BOOL;         (* 点动+（电平，MC_Jog） *)
    xJogNeg : BOOL;         (* 点动-（电平，MC_Jog） *)
    rJogVel : REAL;         (* 点动速度（正值） *)
    rVel : REAL;            (* 定位速度（正值） *)
    rAcc : REAL;            (* 加速度 *)
    rDec : REAL;            (* 减速度 *)
    xLimEn : BOOL;          (* 硬限位使能（X=FALSE，Y/Z/R=TRUE） *)
    rLimPos : REAL;         (* 正方向硬限位（可手动改） *)
    rLimNeg : REAL;         (* 负方向硬限位（可手动改） *)
END_VAR
VAR_OUTPUT
    xPowered : BOOL;        (* 驱动器已上电 := fbPower.Status *)
    xReady : BOOL;          (* 就绪 := 上电且无故障 *)
    xMoving : BOOL;         (* 运动中（含回零） *)
    xStandstill : BOOL;     (* 静止 *)
    xHomed : BOOL;          (* 回零完成（置零后保持） *)
    xFault : BOOL;          (* 故障 := MC_ReadStatus.ErrorStop *)
    xMoveRelDone : BOOL;    (* 相对定位完成 *)
    xMoveAbsDone : BOOL;    (* 绝对定位完成 *)
    rActPos : LREAL;        (* 实际位置 *)
    rVelAct : REAL;         (* 实际速度；g 线 0.68 直控/回读专用 *)
    (* --- 诊断输出（g 线 0.5 新增；上层可不接线，在线直接看） --- *)
    xVelReq : BOOL;         (* 诊断：仲裁后速度请求已成立 *)
    xVelBusy : BOOL;        (* 诊断：MC_MoveVelocity.Busy *)
    xVelInVel : BOOL;       (* 诊断：MC_MoveVelocity.InVelocity *)
    xErrPower : BOOL;       (* 诊断：MC_Power.Error（驱动未就绪/通讯异常） *)
    xErrVel : BOOL;         (* 诊断：MC_MoveVelocity.Error（参数/平台拒绝） *)
    xErrJog : BOOL;         (* 诊断：MC_Jog.Error *)
    xErrHalt : BOOL;        (* 诊断：MC_Halt.Error *)
    xErrHome : BOOL;        (* 诊断：MC_Home.Error *)
    xErrAbs : BOOL;         (* 诊断：MC_MoveAbsolute.Error *)
    xErrRel : BOOL;         (* 诊断：MC_MoveRelative.Error *)
END_VAR
VAR
    fbPower : MC_Power;
    fbHalt : MC_Halt;
    fbHome : MC_Home;
    fbReset : MC_Reset;
    fbReadStatus : MC_ReadStatus;
    fbReadPos : MC_ReadActualPosition;
    fbSetPos : MC_SetPosition;
    fbMoveRel : MC_MoveRelative;
    fbMoveAbs : MC_MoveAbsolute;
    fbMoveVel : MC_MoveVelocity;
    fbJog : MC_Jog;
    eDir : MC_DIRECTION;
    xReqStop : BOOL;
    xReqHome : BOOL;
    xReqAbs : BOOL;
    xReqRel : BOOL;
    xReqVel : BOOL;
    xReqJogPos : BOOL;
    xReqJogNeg : BOOL;
    xReqAny : BOOL;
    xReqHomePrev : BOOL;
    xSetZeroTrig : BOOL;
    xVelRunPrev : BOOL;
    xDirFlip : BOOL;
    xNeedStop : BOOL;
    xHaltPrev : BOOL;
    xResetPrev : BOOL;
    xBlockPos : BOOL;
    xBlockNeg : BOOL;
    rAbsTarget : REAL;
    rRelDist : REAL;
    rVelInPrev : REAL;
END_VAR

(* 1. 状态与位置 *)
fbReadStatus(Axis := Axis, Enable := TRUE);
fbReadPos(Axis := Axis, Enable := TRUE);
rActPos := fbReadPos.Position;
rVelAct := LREAL_TO_REAL(Axis.fActVelocity);
xStandstill := fbReadStatus.StandStill;
xFault := fbReadStatus.ErrorStop;
xMoving := fbReadStatus.DiscreteMotion OR fbReadStatus.ContinuousMotion OR fbReadStatus.Homing;

(* 2. 故障复位（上升沿） *)
fbReset(Axis := Axis, Execute := xResetFault AND NOT xResetPrev);
xResetPrev := xResetFault;

(* 3. 驱动器使能（xStop 不掉使能） *)
fbPower(Axis := Axis, Enable := TRUE,
        bRegulatorOn := xEnable AND NOT xFault,
        bDriveStart := xEnable AND NOT xFault);
xPowered := fbPower.Status;
xReady := xPowered AND NOT xFault;

(* 4. 硬限位：越限方向禁止；定位目标夹紧（已越限时仍允许向回运动） *)
xBlockPos := xLimEn AND (rActPos >= rLimPos);
xBlockNeg := xLimEn AND (rActPos <= rLimNeg);
rAbsTarget := rTargetPos;
rRelDist := rDist;
IF xLimEn THEN
    rAbsTarget := LIMIT(rLimNeg, rTargetPos, rLimPos);
    rRelDist := LIMIT(rLimNeg, rActPos + rDist, rLimPos) - rActPos;
END_IF;

(* 5. 命令仲裁：停止/故障 > 回零 > 绝对 > 相对 > 速度 > 点动 *)
xReqStop := xStop OR NOT xEnable OR xFault;
xReqHome := xHome AND NOT xReqStop;
xReqAbs := xMoveAbs AND xPowered AND NOT xReqStop AND NOT xReqHome;
xReqRel := xMoveRel AND (ABS(rRelDist) > 1.0E-9) AND xPowered
           AND NOT xReqStop AND NOT xReqHome AND NOT xReqAbs;
xReqVel := xUseVelCmd AND (ABS(rVelCmd) > 1.0E-6) AND xPowered
           AND NOT ((rVelCmd > 0.0) AND xBlockPos) AND NOT ((rVelCmd < 0.0) AND xBlockNeg)
           AND NOT xReqStop AND NOT xReqHome AND NOT xReqAbs AND NOT xReqRel;
xReqJogPos := xJogPos AND NOT xJogNeg AND NOT xBlockPos AND xPowered
              AND NOT xReqStop AND NOT xReqHome AND NOT xReqAbs AND NOT xReqRel AND NOT xReqVel;
xReqJogNeg := xJogNeg AND NOT xJogPos AND NOT xBlockNeg AND xPowered
              AND NOT xReqStop AND NOT xReqHome AND NOT xReqAbs AND NOT xReqRel AND NOT xReqVel;
xReqAny := xReqHome OR xReqAbs OR xReqRel OR xReqVel OR xReqJogPos OR xReqJogNeg;

(* 6. 回零：MC_Home(0) → MC_SetPosition(0) → xHomed *)
IF xReqHome AND NOT xReqHomePrev THEN
    xHomed := FALSE;
END_IF;
xReqHomePrev := xReqHome;
fbHome(Axis := Axis, Execute := xReqHome, Position := 0.0);
IF fbHome.Done THEN
    xSetZeroTrig := TRUE;
END_IF;
fbSetPos(Axis := Axis, Execute := xSetZeroTrig, Position := 0.0);
IF fbSetPos.Done THEN
    xHomed := TRUE;
    xSetZeroTrig := FALSE;
END_IF;

(* 7. 绝对 / 相对定位（目标已夹紧；电平保持 Execute，Done 上报） *)
fbMoveAbs(Axis := Axis, Execute := xReqAbs, Position := rAbsTarget,
          Velocity := ABS(rVel), Acceleration := rAcc, Deceleration := rDec);
fbMoveRel(Axis := Axis, Execute := xReqRel, Distance := rRelDist,
          Velocity := ABS(rVel), Acceleration := rAcc, Deceleration := rDec);
xMoveAbsDone := fbMoveAbs.Done;
xMoveRelDone := fbMoveRel.Done;

(* 8. 速度指令：MC_MoveVelocity；Velocity 取绝对值，方向走 Direction *)
(* 注意：本机 SM3 库的方向字面值是 positive/negative（非 CoDeSys 的 mcPositiveDirection） *)
IF rVelCmd >= 0.0 THEN
    eDir := positive;
ELSE
    eDir := negative;
END_IF;
(* 运行中换向：先撤 Execute 一拍，下一拍带新方向重新触发 *)
xDirFlip := xReqVel AND xVelRunPrev AND ((rVelCmd >= 0.0) <> (rVelInPrev >= 0.0));
fbMoveVel(Axis := Axis, Execute := xReqVel AND NOT xDirFlip,
          Velocity := ABS(rVelCmd), Direction := eDir,
          Acceleration := rAcc, Deceleration := rDec);
xVelRunPrev := xReqVel;
rVelInPrev := rVelCmd;

(* 9. 手动点动：MC_Jog（按住动、松开减速停；越限方向已在仲裁禁止） *)
fbJog(Axis := Axis,
      JogForward := xReqJogPos,
      JogBackward := xReqJogNeg,
      Velocity := ABS(rJogVel),
      Acceleration := rAcc,
      Deceleration := rDec);

(* 10. 停车：有使能但无任何运动请求（松手/速度归零/停止/急停/撞限位）→ MC_Halt *)
xNeedStop := xPowered AND NOT xReqAny;
fbHalt(Axis := Axis, Execute := xNeedStop AND xMoving AND NOT xHaltPrev,
       Deceleration := rDec);
xHaltPrev := xNeedStop AND xMoving;

(* 11. 诊断输出（g 线 0.5） *)
xVelReq := xReqVel;
xVelBusy := fbMoveVel.Busy;
xVelInVel := fbMoveVel.InVelocity;
xErrPower := fbPower.Error;
xErrVel := fbMoveVel.Error;
xErrJog := fbJog.Error;
xErrHalt := fbHalt.Error;
xErrHome := fbHome.Error;
xErrAbs := fbMoveAbs.Error;
xErrRel := fbMoveRel.Error;
