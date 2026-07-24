# FB_Servo.md — 单轴原子封装（SM3_Basic）

> 源码：`plc/src/FB_Servo.st`。**仅在 PRG_Axis_Control 任务内实例化**，不对 Logic/HMI 暴露 CALL。

## 行为

每拍按优先级直接仲裁，无状态机：

```
停止/故障 > 回零 > 绝对定位 > 相对定位 > 速度指令 > 点动
```

- **手动点动**：`MC_Jog`（JogForward/JogBackward 电平，松开即减速停）
- **速度指令**（力跟随 / X 双驱）：`MC_MoveVelocity`，`Velocity := ABS(rVelCmd)`，方向走 `Direction := positive / negative`（本机库字面值）；运行中换向先撤 Execute 一拍再重触发
- **定位**：`MC_MoveAbsolute` / `MC_MoveRelative`，Execute 电平保持，Done 上报
- **运动切换**：新命令 FB 的 Execute 上升沿自动 abort 旧运动（mcAborting），无需手工过渡
- **停车**：有使能但无任何运动请求（松手/速度归零/停止/急停/撞限位）→ `MC_Halt` 减速
- **回零**：`MC_Home(0)` → Done → `MC_SetPosition(0)` → `xHomed`
- **使能**：`MC_Power(Enable:=TRUE, bRegulatorOn/bDriveStart := xEnable AND NOT xFault)`；`xReady := xPowered AND NOT xFault`

## 硬限位（所有模式强制）

`xLimEn=TRUE` 时（Y/Z/R；X 传 FALSE）：

| 模式 | 行为 |
|------|------|
| 点动 / 速度 | 越限方向被禁止；运动中撞到限位 → MC_Halt |
| 绝对 / 相对定位 | 目标位置夹紧到 `[rLimNeg, rLimPos]` |
| 已越限（限位被改小） | 仍允许向回运动 |

限位值来自 GVL `Cfg_rLim*`（触摸屏/调试可手动改）。回零不受限位阻挡。

## 接口

```iecst
VAR_IN_OUT Axis : AXIS_REF_SM3; END_VAR
VAR_INPUT
    xEnable; xStop; xResetFault; xHome : BOOL;
    xMoveAbs; rTargetPos; xMoveRel; rDist;       (* 定位 *)
    xUseVelCmd; rVelCmd;                          (* 速度指令 *)
    xJogPos; xJogNeg; rJogVel;                    (* 点动 *)
    rVel; rAcc; rDec : REAL;
    xLimEn : BOOL; rLimPos; rLimNeg : REAL;       (* 硬限位 *)
END_VAR
VAR_OUTPUT
    xPowered; xReady; xMoving; xStandstill; xHomed; xFault : BOOL;
    xMoveRelDone; xMoveAbsDone : BOOL;
    rActPos : LREAL;
END_VAR
```

## CoDeSys / SM3 要点（勿再写错）

| 项 | 正确 | 错误 |
|----|------|------|
| `MC_MoveVelocity` | `Velocity:=ABS(v)`，`Direction := positive / negative`（**本机 InoProShop 库字面值**；CoDeSys 标准的 `mcPositiveDirection` 在本机未定义） | `Velocity:=-ABS(v)` 或把 REAL 赋给 Direction |
| 点动 | `MC_Jog` 电平输入 | 用 MoveVelocity 模拟点动 |
| 停车 | `MC_Halt`（可随时被新命令中止） | `MC_Stop`（Execute 期间锁死新命令） |
| 故障判定 | 仅 `MC_ReadStatus.ErrorStop` | OR 各 FB 的 `.Error` |
| 使能就绪 | `MC_Power.Status` | 用 ReadStatus 冒充（无 `Operational`） |
| 枚举 | 显式声明 `MC_DIRECTION` 变量 | 隐式枚举（本工程编译不过的旧坑） |
