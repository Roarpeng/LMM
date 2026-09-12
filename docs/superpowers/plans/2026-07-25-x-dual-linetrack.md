# X Dual LineTrack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉 `FB_GantryX` / `Axis_Virtual` / 电子齿轮，改为 `FB_XDual`（`FB_XLineTrack` + 双 `FB_Servo` 速度模式 + 平均相对位移判完成），并取消同步偏差报警 1008。

**Architecture:** `PRG_Axis_Control` 只组装 `fbX : FB_XDual` 与现有 Y/Z/R/力 FB。`FB_XDual` 内部调用 `FB_XLineTrack` 合成 `rVelM1/M2`，分别送给 `fbM1`/`fbM2`（`Axis` / `Axis_1`）。走距在 `xMoveRel` 上升沿锁存平均位置起点，用相对增量判 `xMoveDone`。同步相关反馈恒 0/FALSE。

**Tech Stack:** IEC 61131-3 ST、PLCopen TC6 `LMM.xml`、`tools/inject_st.py`、`tools/check_lmm.py`、Python `unittest`（纯逻辑镜像）、InoProShop 现场导入。

**Spec:** `docs/superpowers/specs/2026-07-25-x-dual-linetrack-design.md`

## Global Constraints

- 保持 3-POU 边界：`PRG_Axis_Control` 独立 ETHERCAT 任务；禁止跨任务 CALL。
- `AxisCmd_*` / `HMI_*` / Modbus 命令契约不变。
- 不做 `|PosM1−PosM2|` 联锁；无报警 1008。
- 走距完成：`|(PosM1+PosM2)/2 − rStart| ≥ |rMoveDist|`。
- X 轴 `xLimEn:=FALSE`；Y/Z/R 与力控路径不改。
- 改 `.st` 后必须 `python tools/inject_st.py` → `python tools/check_lmm.py`（0 error）。
- 设备树删除/禁用 `Axis_Virtual` 只在 InoProShop 做，本仓库计划只改 POU/文档/工具。
- 不提交除非用户明确要求。

## File Structure

| 文件 | 职责 |
|------|------|
| `plc/src/FB_XDual.st` | **新建** X 双驱封装：仲裁 + LineTrack + 双 Servo + 走距 |
| `plc/src/PRG_Axis_Control.st` | 用 `fbX` 替换 `fbGantry` |
| `plc/src/PRG_Logic.st` | 删除 1008 分支；`xFaultAggregate` 不再依赖 sync fault（若仍 OR 则改掉） |
| `plc/GVL.st` | 注释：同步项废弃、报警表去掉 1008 |
| `plc/src/FB_XLineTrack.st` | **不改语义**（已满足） |
| `tools/inject_st.py` | `FB_XDual` GUID；`FB_GantryX` 进 `DEAD_POUS` |
| `tools/check_lmm.py` | POU 集合：`-FB_GantryX` `+FB_XDual`；断言 Axis ST 无 Gear/Virtual |
| `tools/x_dual_logic.py` | 纯 Python 镜像（模式/走距）供单测 |
| `tools/test_x_dual_logic.py` | 单测 |
| `docs/plc/Axis_Control.md` 等 | 文档对齐 spec |

---

### Task 1: Python 镜像 + 单测（模式仲裁与走距）

**Files:**
- Create: `tools/x_dual_logic.py`
- Create: `tools/test_x_dual_logic.py`

**Interfaces:**
- Produces: `select_mode(jog_pos, jog_neg, spin_l, spin_r, move_rel, stop, enable) -> int`（0/1/2/3）
- Produces: `base_vel(mode, jog_pos, jog_neg, jog_vel, move_rel, move_dist, move_vel) -> float`
- Produces: `move_done_update(state, *, move_rel, stop, enable, pos_m1, pos_m2, move_dist) -> (done: bool, state)`
- Produces: `state` 含 `armed: bool`, `start: float`

- [ ] **Step 1: 写失败测试**

```python
# tools/test_x_dual_logic.py
import unittest
from tools.x_dual_logic import select_mode, base_vel, move_done_update, MoveState

class XDualLogicTests(unittest.TestCase):
    def test_spin_beats_jog(self):
        self.assertEqual(select_mode(True, False, True, False, False, False, True), 2)

    def test_jog_pos_mode1(self):
        self.assertEqual(select_mode(True, False, False, False, False, False, True), 1)
        self.assertEqual(base_vel(1, True, False, 0.4, False, 1.0, 0.5), 0.4)

    def test_move_rel_base_vel_sign(self):
        self.assertEqual(base_vel(1, False, False, 0.4, True, -2.0, 0.5), -0.5)

    def test_move_done_average_relative(self):
        st = MoveState()
        done, st = move_done_update(st, move_rel=True, stop=False, enable=True,
                                    pos_m1=0.0, pos_m2=0.0, move_dist=1.0)
        self.assertFalse(done)
        done, st = move_done_update(st, move_rel=True, stop=False, enable=True,
                                    pos_m1=0.6, pos_m2=0.6, move_dist=1.0)
        self.assertTrue(done)

    def test_stop_clears_done(self):
        st = MoveState(armed=True, start=0.0)
        done, st = move_done_update(st, move_rel=True, stop=True, enable=True,
                                    pos_m1=2.0, pos_m2=2.0, move_dist=1.0)
        self.assertFalse(done)
        self.assertFalse(st.armed)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest tools.test_x_dual_logic -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现最小镜像**

```python
# tools/x_dual_logic.py
from dataclasses import dataclass

@dataclass
class MoveState:
    armed: bool = False
    start: float = 0.0
    prev_move: bool = False

def select_mode(jog_pos, jog_neg, spin_l, spin_r, move_rel, stop, enable):
    if stop or not enable:
        return 0
    if spin_l ^ spin_r:
        return 2 if spin_l else 3
    if (jog_pos ^ jog_neg) or move_rel:
        return 1
    return 0

def base_vel(mode, jog_pos, jog_neg, jog_vel, move_rel, move_dist, move_vel):
    if mode != 1:
        return 0.0
    if move_rel:
        return (1.0 if move_dist >= 0.0 else -1.0) * abs(move_vel)
    if jog_pos ^ jog_neg:
        return abs(jog_vel) if jog_pos else -abs(jog_vel)
    return 0.0

def move_done_update(state, *, move_rel, stop, enable, pos_m1, pos_m2, move_dist):
    avg = 0.5 * (pos_m1 + pos_m2)
    if stop or not enable or not move_rel:
        return False, MoveState(armed=False, start=0.0, prev_move=False)
    edge = move_rel and not state.prev_move
    armed = state.armed
    start = state.start
    if edge:
        armed = True
        start = avg
    done = armed and abs(avg - start) >= abs(move_dist)
    return done, MoveState(armed=armed, start=start, prev_move=True)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest tools.test_x_dual_logic -v`  
Expected: OK

- [ ] **Step 5: Commit（仅当用户要求）**

```bash
git add tools/x_dual_logic.py tools/test_x_dual_logic.py
git commit -m "test: add X dual LineTrack mode and move-done logic mirror"
```

---

### Task 2: 实现 `FB_XDual.st`

**Files:**
- Create: `plc/src/FB_XDual.st`
- Modify: `tools/inject_st.py`（`NEW_POU_GUIDS["FB_XDual"]`；`DEAD_POUS` 加 `FB_GantryX`；可移除仅用于 Gantry 的 GUID 或保留无害）
- Modify: `tools/check_lmm.py`（`EXPECTED_POUS`：`FB_XDual` 替换 `FB_GantryX`）

**Interfaces:**
- Consumes: `FB_XLineTrack`、`FB_Servo`、`AXIS_REF_SM3`（`Axis`/`Axis_1`）
- Produces: `FB_XDual` 输出与现 `fbGantry` 回写字段对齐（见下方 VAR_OUTPUT）
- GUID: `d4e5f6a7-b8c9-4012-c345-d6e7f8a90002`

- [ ] **Step 1: 扩展 inject / check 契约（先改工具，再写 ST）**

在 `tools/inject_st.py`:

```python
DEAD_POUS = ["FB_TCPServer", "PRG_Force485", "FB_XDiff", "FB_GantryX"]
NEW_POU_GUIDS = {
    "FB_XDual": "d4e5f6a7-b8c9-4012-c345-d6e7f8a90002",
}
```

在 `tools/check_lmm.py` 的 `EXPECTED_POUS` 中把 `FB_GantryX` 换成 `FB_XDual`。

- [ ] **Step 2: 写 `FB_XDual.st` 完整源码**

语义必须与 Task 1 镜像一致：Stop > Spin > Jog/MoveRel；走距上升沿锁存平均位置；完成后保持 `xMoveDone` 直到 `xMoveRel` 撤销或 Stop。

```iecst
FUNCTION_BLOCK FB_XDual
(* FB_XDual — M1/M2 独立速度 + FB_XLineTrack；无 Virtual/Gear。
   走距：平均相对位移；不做 |PosM1-PosM2| 联锁。 *)
VAR_IN_OUT
    AxisM1 : AXIS_REF_SM3;
    AxisM2 : AXIS_REF_SM3;
END_VAR
VAR_INPUT
    xEnable : BOOL;
    xStop : BOOL;
    xResetFault : BOOL;
    xJogPos : BOOL;
    xJogNeg : BOOL;
    xSpinLeft : BOOL;
    xSpinRight : BOOL;
    xMoveRel : BOOL;
    rMoveDist : REAL;
    rMoveVel : REAL;
    rJogVel : REAL;
    rSpinVel : REAL;
    rHeadingErr : REAL;
    rKpTrack : REAL;
    rAcc : REAL;
    rDec : REAL;
    rTrimMax : REAL;        (* 纠偏限幅；接 Cfg_rPhaseMax *)
END_VAR
VAR_OUTPUT
    xMoveDone : BOOL;
    rPosV : REAL;           (* 平均位置，兼容旧 rPosX 名 *)
    rSyncErr : REAL;        (* 恒 0 *)
    rVelFactor : REAL;      (* 恒 0 *)
    xCoupled : BOOL;        (* 恒 FALSE *)
    xInGearM1 : BOOL;
    xInGearM2 : BOOL;
    xPoweredV : BOOL;
    xSyncWarn : BOOL;
    xSyncFault : BOOL;
    iState : INT;           (* 恒 0 *)
    rVelCmdM1 : REAL;
    rVelCmdM2 : REAL;
    rPosM1 : REAL;
    rPosM2 : REAL;
    xMovingM1 : BOOL;
    xMovingM2 : BOOL;
    xStandstillM1 : BOOL;
    xStandstillM2 : BOOL;
    xPoweredM1 : BOOL;
    xPoweredM2 : BOOL;
    xReadyM1 : BOOL;
    xReadyM2 : BOOL;
    xFaultM1 : BOOL;
    xFaultM2 : BOOL;
END_VAR
VAR
    fbTrack : FB_XLineTrack;
    fbM1 : FB_Servo;
    fbM2 : FB_Servo;
    eMode : INT;
    rBase : REAL;
    xMovePrev : BOOL;
    xArmed : BOOL;
    rStart : REAL;
    rAvg : REAL;
END_VAR

(* 废弃同步输出 *)
rSyncErr := 0.0; rVelFactor := 0.0; iState := 0;
xCoupled := FALSE; xInGearM1 := FALSE; xInGearM2 := FALSE;
xPoweredV := FALSE; xSyncWarn := FALSE; xSyncFault := FALSE;

(* 模式：Stop > Spin > Jog/MoveRel *)
IF xStop OR NOT xEnable THEN
    eMode := 0; rBase := 0.0;
ELSIF xSpinLeft XOR xSpinRight THEN
    eMode := SEL(xSpinLeft, 3, 2); rBase := 0.0;
ELSIF (xJogPos XOR xJogNeg) OR xMoveRel THEN
    eMode := 1;
    IF xMoveRel THEN
        rBase := SEL(rMoveDist >= 0.0, -ABS(rMoveVel), ABS(rMoveVel));
    ELSIF xJogPos THEN
        rBase := ABS(rJogVel);
    ELSE
        rBase := -ABS(rJogVel);
    END_IF;
ELSE
    eMode := 0; rBase := 0.0;
END_IF;

fbTrack(xEnable := xEnable, xStop := xStop, eMode := eMode,
    rBaseVel := rBase, rSpinVel := rSpinVel,
    rHeadingErr := rHeadingErr, rKpTrack := rKpTrack, rTrimMax := rTrimMax);
rVelCmdM1 := fbTrack.rVelM1; rVelCmdM2 := fbTrack.rVelM2;

fbM1(Axis := AxisM1, xEnable := xEnable, xStop := xStop, xResetFault := xResetFault,
    xUseVelCmd := TRUE, rVelCmd := rVelCmdM1, rAcc := rAcc, rDec := rDec, xLimEn := FALSE);
fbM2(Axis := AxisM2, xEnable := xEnable, xStop := xStop, xResetFault := xResetFault,
    xUseVelCmd := TRUE, rVelCmd := rVelCmdM2, rAcc := rAcc, rDec := rDec, xLimEn := FALSE);

rPosM1 := LREAL_TO_REAL(fbM1.rActPos); rPosM2 := LREAL_TO_REAL(fbM2.rActPos);
rAvg := (rPosM1 + rPosM2) * 0.5; rPosV := rAvg;
xMovingM1 := fbM1.xMoving; xMovingM2 := fbM2.xMoving;
xStandstillM1 := fbM1.xStandstill; xStandstillM2 := fbM2.xStandstill;
xPoweredM1 := fbM1.xPowered; xPoweredM2 := fbM2.xPowered;
xReadyM1 := fbM1.xReady; xReadyM2 := fbM2.xReady;
xFaultM1 := fbM1.xFault; xFaultM2 := fbM2.xFault;

IF xStop OR NOT xEnable OR NOT xMoveRel THEN
    xArmed := FALSE; xMoveDone := FALSE;
ELSIF xMoveRel AND NOT xMovePrev THEN
    xArmed := TRUE; rStart := rAvg; xMoveDone := FALSE;
ELSIF xArmed AND (ABS(rAvg - rStart) >= ABS(rMoveDist)) THEN
    xMoveDone := TRUE;
END_IF;
xMovePrev := xMoveRel;
```

注意：`SEL(xSpinLeft, 3, 2)` 与 `SEL(rMoveDist >= 0.0, -ABS(...), ABS(...))` 的真/假分支顺序必须与 Python 镜像一致；实现时对照 Task 1 再核对一遍（IEC `SEL(G, IN0, IN1)`：G=FALSE→IN0，TRUE→IN1——**与常见直觉相反**）。若本机 SEL 语义如此，Spin 左应为：

```iecst
IF xSpinLeft THEN eMode := 2; ELSE eMode := 3; END_IF;
```

走距符号同理用 `IF` 写清，避免 SEL 踩坑。

- [ ] **Step 3: dry-run 解析**

Run: `python tools/inject_st.py --check`  
Expected: 能解析 `FB_XDual.st`（若 `--check` 只扫已注册文件，先确认 `main` 会枚举 `plc/src/*.st`）。

- [ ] **Step 4: 注入并静态校验**

Run:

```bash
python tools/inject_st.py
python tools/check_lmm.py
```

Expected: 新建 POU 壳 `FB_XDual`；删除 `FB_GantryX`；`check_lmm.py` 退出码 0。若 `PRG_Axis_Control` 仍引用 `FB_GantryX`，本步允许 Axis 相关 error，在 Task 3 消除。

- [ ] **Step 5: Commit（仅当用户要求）**

```bash
git add plc/src/FB_XDual.st tools/inject_st.py tools/check_lmm.py LMM.xml
git commit -m "feat: add FB_XDual independent dual-drive LineTrack block"
```

---

### Task 3: 改接 `PRG_Axis_Control` + 去掉 1008

**Files:**
- Modify: `plc/src/PRG_Axis_Control.st`
- Modify: `plc/src/PRG_Logic.st`
- Modify: `plc/GVL.st`（注释）
- Modify: `tools/check_lmm.py`（可选断言：`PRG_Axis_Control` ST 不含 `MC_GearIn`/`Axis_Virtual`/`FB_GantryX`）

**Interfaces:**
- Consumes: `FB_XDual`（Task 2）
- Produces: 现有 `AxisFb_*` 赋值；`AxisFb_xSyncFault` 恒 FALSE 后 `xFaultAggregate` 不再因同步跳闸

- [ ] **Step 1: 重写 Axis 中 X 段**

将 `fbGantry : FB_GantryX` 换为 `fbX : FB_XDual`，调用示例：

```iecst
fbX(
    AxisM1 := Axis, AxisM2 := Axis_1,
    xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xJogPos := AxisCmd_xJogXPos, xJogNeg := AxisCmd_xJogXNeg,
    xSpinLeft := AxisCmd_xSpinLeft, xSpinRight := AxisCmd_xSpinRight,
    xMoveRel := AxisCmd_xMoveRelX, rMoveDist := AxisCmd_rMoveDistX, rMoveVel := AxisCmd_rMoveVelX,
    rJogVel := AxisCmd_rJogVelX, rSpinVel := AxisCmd_rSpinVel,
    rHeadingErr := AxisCmd_rHeadingErr, rKpTrack := AxisCmd_rTrackKp,
    rAcc := AxisCmd_rAccX, rDec := AxisCmd_rDecX,
    rTrimMax := Cfg_rPhaseMax);
AxisFb_xMoveDoneX := fbX.xMoveDone;
AxisFb_rPosX := fbX.rPosV;
AxisFb_rSyncErr := fbX.rSyncErr;
AxisFb_rVelFactorX := fbX.rVelFactor;
AxisFb_xGantryCoupled := fbX.xCoupled;
AxisFb_xInGearM1 := fbX.xInGearM1;
AxisFb_xInGearM2 := fbX.xInGearM2;
AxisFb_xPoweredV := fbX.xPoweredV;
AxisFb_xSyncWarn := fbX.xSyncWarn;
AxisFb_xSyncFault := fbX.xSyncFault;
AxisFb_iGantryState := fbX.iState;
AxisFb_rVelCmdM1 := fbX.rVelCmdM1;
AxisFb_rVelCmdM2 := fbX.rVelCmdM2;
AxisFb_rPosM1 := fbX.rPosM1;
AxisFb_rPosM2 := fbX.rPosM2;
AxisFb_xMovingM1 := fbX.xMovingM1;
AxisFb_xMovingM2 := fbX.xMovingM2;
AxisFb_xStandstill1 := fbX.xStandstillM1;
AxisFb_xStandstill2 := fbX.xStandstillM2;
AxisFb_xPoweredM1 := fbX.xPoweredM1;
AxisFb_xPoweredM2 := fbX.xPoweredM2;
AxisFb_xReadyM1 := fbX.xReadyM1;
AxisFb_xReadyM2 := fbX.xReadyM2;
AxisFb_xFaultM1 := fbX.xFaultM1;
AxisFb_xFaultM2 := fbX.xFaultM2;
```

文件头注释改为：`X：FB_XDual（LineTrack + 双 FB_Servo，无 Virtual/Gear）`。

- [ ] **Step 2: Logic 去掉 1008**

删除：

```iecst
ELSIF AxisFb_xSyncFault THEN
    iAlarmID := 1008;
```

确认 `xFaultAggregate` **不要**再 OR `AxisFb_xSyncFault`（若当前有则删）。

GVL 注释：

```iecst
(* 【只读·报警号】1001急停 1002轴故障 1005力超时 1006从站失败 1007未就绪；1008已废 *)
(* 【只读·同步跳闸】已废，恒 FALSE *)
```

- [ ] **Step 3: check_lmm 加禁词断言**

```python
axis_st = all_st.get("PRG_Axis_Control", "")
for bad in ("FB_GantryX", "Axis_Virtual", "MC_GearIn", "MC_GearOut", "MC_Phasing"):
    if bad in axis_st:
        err(f"PRG_Axis_Control 仍引用禁词: {bad}")
```

- [ ] **Step 4: 注入 + 校验**

Run:

```bash
python tools/inject_st.py
python tools/check_lmm.py
python -m unittest tools.test_x_dual_logic -v
```

Expected: 全部 0 / OK。

- [ ] **Step 5: Commit（仅当用户要求）**

```bash
git add plc/src/PRG_Axis_Control.st plc/src/PRG_Logic.st plc/GVL.st tools/check_lmm.py LMM.xml
git commit -m "feat: wire FB_XDual and drop sync-fault alarm 1008"
```

---

### Task 4: 文档与现场清单

**Files:**
- Modify: `docs/plc/Axis_Control.md`
- Modify: `plc/README.md`
- Modify: `docs/plc/IMPORT_LMM_XML.md`（POU 列表）
- Modify: `docs/plc/PRG_Logic.md`（报警表去 1008）
- Modify: `docs/plc/REFACTOR_3POU.md`（X 描述）
- Modify: `docs/superpowers/specs/2026-07-25-x-dual-linetrack-design.md`（状态→已实现，实现完成后勾）

- [ ] **Step 1: 更新 Axis_Control.md**

替换为：双 `FB_Servo` + `FB_XLineTrack`（经 `FB_XDual`）；无 Gear；走距平均相对位移；无 1008。

- [ ] **Step 2: 更新 README / IMPORT / Logic / REFACTOR 中的 Gantry 表述**

POU 表：`FB_XDual` 替换 `FB_GantryX`；`FB_XLineTrack` 说明改为「由 `FB_XDual` 调用」。

- [ ] **Step 3: 现场 InoProShop 清单（文档段落，不自动化）**

1. 导入注入后的 `LMM.xml`
2. 编译：确认无 `FB_GantryX` / `Axis_Virtual` 未解析引用
3. 设备树：**禁用或删除** `Axis_Virtual`
4. 核对 `Axis` / `Axis_1` 仍为 M1/M2
5. 下载后验收：手动 X±、Spin、自动一步走距、确认无 1008

- [ ] **Step 4: 跑最终校验**

Run: `python tools/check_lmm.py && python -m unittest tools.test_x_dual_logic -v`

- [ ] **Step 5: Commit（仅当用户要求）**

```bash
git add docs/plc plc/README.md docs/superpowers/specs/2026-07-25-x-dual-linetrack-design.md
git commit -m "docs: align Axis Control docs with FB_XDual LineTrack"
```

---

## Spec Coverage (self-review)

| Spec 要求 | Task |
|-----------|------|
| 删 Virtual/Gear/`FB_GantryX` | 2, 3, 4 |
| LineTrack 手动 Jog + Spin | 1, 2, 3 |
| 自动 LineTrack + 平均相对位移 | 1, 2, 3 |
| 无同步偏差联锁 / 无 1008 | 2, 3, 4 |
| HMI/AxisCmd 契约不变 | 3（回写字段兼容） |
| Y/Z/R 不动 | 3（只改 X 段） |
| 文档 + 现场删 Virtual | 4 |

## Placeholder / SEL 风险

- ST 中避免依赖模糊的 `SEL` 真假顺序；Spin/走距符号用 `IF` 写死，并与 `tools/x_dual_logic.py` 对照。
- `LREAL_TO_REAL`：若工程用 `REAL` 读位置，按 `FB_Servo.rActPos` 实际类型调整（可能直接 `rPosM1 := fbM1.rActPos`）。
