# GVL / HMI 精简方案 A — 设计说明

> 日期：2026-07-23  
> 状态：待用户确认后写实施计划  
> 选型：方案 A（砍重复、保能力；各轴独立 Jog±；补 Acc/Dec；报警二元）

## 1. 目标

- **物理操作**：仅 **启动 / 停止 / 复位** 三键（硬急停另线，不计入“手动精简”集合）。
- **HMI_***：各轴 **速度 + 加减速 + 触发**（点动电平、回零上升沿）；自动/力控参数保留但与手动分区。
- **报警对外**：`HMI_ALARM`（BOOL）+ `HMI_ALARMID`（INT）。
- **不绑屏**：`AxisCmd_*`、`Tcp_*` 影子、`MB_*` 过程映像。

非目标（本轮不做）：轴选择器方案 B、结构体数组方案 C、改变机械坐标系/回零模式。

## 2. 分层

```text
物理 DI          HMI 写/读              Logic 仲裁           Axis 层
─────────        ──────────            ──────────           ────────
StartBtn    →    （可不绑 HMI）         → 起停状态机
StopBtn     →    （可不绑 HMI）         → 停机
ResetBtn    →    （可不绑 HMI）         → 复位/清故障
EStop       →    HMI_xEStop（更严 AND） → 安全门控
                 HMI_xJog* / Vel/Acc   → AxisCmd_*      → FB_Servo
                 HMI_xHomeY/Z/R        → AxisCmd_xHome*
                 HMI_ALARM / ALARMID ← iAlarm 判定
```

原则：

1. 三键优先走物理 DI；触摸屏/Web 若要同功能，**复用同一语义名**，不再平行维护 `*Req` 森林（见 §5）。
2. 点动仍 **各轴独立 Jog±**（X、Spin、Y、Z、R），习惯不变。
3. Acc/Dec **暴露到 HMI**，Logic 拷到 `AxisCmd_rAcc/rDec`（本轮可先全局一套；轴级覆盖列为可选扩展）。
4. 回零 **只留** `HMI_xHomeY/Z/R`；删除 `HMI_iHomeAxis` + `HMI_xHomeExec`。
5. 报警 **只对外两个名字**；旧 `HMI_iAlarmShow` 迁移为 `HMI_ALARMID`，并新增 `HMI_ALARM := (HMI_ALARMID <> 0)`。

## 3. 物理三键（保持）

| DI | 语义 | Logic 行为 |
|----|------|------------|
| `StartBtn` | 启动 | 上升沿：允许运行 / 解除停机锁（与现 `HMI_xStart` 等效） |
| `StopBtn` | 停止 | TRUE：停机、中止运动 |
| `ResetBtn` | 复位 | TRUE：清故障锁存、等同现 `HMI_xStopHold3s` 复位语义 |
| `EStop` | 急停 | TRUE=正常，FALSE=按下；与屏/Web 急停相与（更严） |

屏上若放置启动/停止/复位：直接写同一套内部起停变量，或写 `HMI_xStart` / `HMI_xStop` / `HMI_xReset`（见命名），**禁止**再绑一套仅触摸屏用的平行命令（迁移期内可 OR 兼容）。

## 4. HMI 手动集合（方案 A 对外清单）

### 4.1 写 — 模式

| 变量 | 类型 | 说明 |
|------|------|------|
| `HMI_xAutoMode` | BOOL | FALSE 手动 / TRUE 自动 |

### 4.2 写 — 点动触发（电平，按住 TRUE）

| 变量 | 说明 |
|------|------|
| `HMI_xJogXPos` / `HMI_xJogXNeg` | X 直行 ± |
| `HMI_xSpinLeft` / `HMI_xSpinRight` | 原地旋（与 X± 互斥） |
| `HMI_xJogYPos` / `HMI_xJogYNeg` | Y ± |
| `HMI_xJogZPos` / `HMI_xJogZNeg` | Z ± |
| `HMI_xJogRPos` / `HMI_xJogRNeg` | R ± |

### 4.3 写 — 速度 / 加减速

| 变量 | 说明 |
|------|------|
| `HMI_rJogVelX` | X 直行速度 |
| `HMI_rSpinVel` | 旋转速度（与 VelX 分离） |
| `HMI_rJogVelY` / `Z` / `R` | Y/Z/R 点动速度 |
| `HMI_rAcc` | 全局加速度（新增绑屏；默认进 `AxisCmd_rAcc`） |
| `HMI_rDec` | 全局减速度（新增绑屏；默认进 `AxisCmd_rDec`） |

可选扩展（本轮可不实现）：`HMI_rAccX/Y/Z/R`、`HMI_rDecX/Y/Z/R` 轴级覆盖。

### 4.4 写 — 回零触发（上升沿，只此一种）

| 变量 | 说明 |
|------|------|
| `HMI_xHomeY` / `HMI_xHomeZ` / `HMI_xHomeR` | 单轴回零 |

同时只允许一轴回零；停/急停中止。完成后当前位置为 0。

### 4.5 读 — 报警（对外仅此二元）

| 变量 | 类型 | 说明 |
|------|------|------|
| `HMI_ALARM` | BOOL | TRUE=有报警 |
| `HMI_ALARMID` | INT | 报警号；0=无。代码表沿用 1001…1007 等 |

派生：`HMI_ALARM := (HMI_ALARMID <> 0)`（Logic 写，HMI 只读）。

### 4.6 读 — 手动相关状态（保留，监控用）

| 变量 | 说明 |
|------|------|
| `HMI_xHomedY/Z/R` | 已回零 |
| `HMI_xHomeBusyY/Z/R` | 回零中 |
| `HMI_eOpMode` | 0 手动 / 1 自动 |
| `AxisFb_rPos*` / Ready / Fault | 位置与轴状态（可不改名前缀） |

### 4.7 自动 / 力控（保留，非本轮裁剪重点）

`HMI_xAutoStart` / `Abort`、`HMI_rAutoDistX`、`HMI_rAutoVelX/Y/Z`、`HMI_rWheelBase`、`HMI_iAutoPasses`、`HMI_rForceSet`、Kp、力引导/去皮/模拟、`HMI_iAutoStepShow`、`HMI_xAutoBusy/Done`、`HMI_rForceShow` — **保持**，与手动分区绑定即可。

## 5. 废弃 / 迁移

| 现状 | 处置 |
|------|------|
| `HMI_xEnable` | **废弃绑屏**；内部可 `:= HMI_xStart` 兼容一版后删除 |
| `HMI_iHomeAxis` + `HMI_xHomeExec` | **删除**；Logic 只认 `HomeY/Z/R` |
| `HMI_iAlarmShow` | **改名为** `HMI_ALARMID`；Modbus/Web 同步改名 |
| （无） | **新增** `HMI_ALARM` |
| `HMI_xStopHold3s` | **改名为** `HMI_xReset`（语义=复位）；物理 `ResetBtn` 写入它 |
| `HMI_*Req` 双轨 | **收敛**：触摸屏写与 Web 仲裁后的同一 `HMI_*`；迁移期 OR 后删除 Req |
| `HMI_xDevStop/Run/Error` 与 `HMI_xLamp*` | **保留一套灯即可**（推荐保留 Lamp* + `eDevState`；Dev 三态可标废弃） |

已删除且仍禁止绑屏：`eXMode`、`JogXSync*` 等（见现 `GVL.md`）。

## 6. 数据流（手动）

1. 物理三键 → Logic 起停/复位状态机。  
2. HMI Jog± / Vel / Acc / Dec / Home* →（Web 则经 `Tcp_*` 仲裁）→ `HMI_*`。  
3. `PRG_Logic`：互锁、软限位、模式门控 → `AxisCmd_*`。  
4. `PRG_Axis_Control`：`FB_Servo` 等执行（Velocity≥0 + Direction）。  
5. 报警判定 → `HMI_ALARMID` / `HMI_ALARM`。

## 7. 通讯影响

- `config/modbus-map.json`、`docs/plc/MODBUS_MAP.md`、`web/live`：`HMI_iAlarmShow` → `HMI_ALARMID`；增加 `HMI_ALARM`；增加 `HMI_rAcc` / `HMI_rDec`。  
- 删除 map 中的 `HomeExec` / `iHomeAxis`（若已映射）。  
- Gateway 编解码与测试同步。

## 8. 验收标准

1. 现场可用物理 **启动/停止/复位** 完成起停与清故障，无需依赖屏上第二套起停变量名。  
2. 手动：各轴 Jog± 行为与现网一致；改 `HMI_rAcc/rDec` 能反映到轴运动加减速。  
3. 回零仅 `HomeY/Z/R` 有效；旧轴选+Exec 无效或已移除。  
4. 有报警时 `HMI_ALARM=TRUE` 且 `HMI_ALARMID` 为对应码；无报警两者为 FALSE/0。  
5. 触摸屏与 Web 绑定清单可按 §4 一页列完（手动区）。

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 旧屏仍绑 `iAlarmShow` / `HomeExec` / `Enable` | 文档废弃清单 + 导入检查；短过渡期别名拷贝 |
| Acc/Dec 全局改导致自动段过猛 | 默认沿用现 `AxisCmd` 默认值；自动可继续用独立 AutoVel |
| Modbus 偏移错位 | 改 map 后跑 gateway 测试 + XML 静态测 |

## 10. 实施边界（确认后出 plan）

1. 更新 `GVL` / `LMM.xml` 变量与 `PRG_Logic` 报警/回零/AccDec 映射。  
2. 更新 HMI.md、GVL.md、MODBUS、Web、annotate。  
3. 测试：XML 良构、map 名、Logic 报警派生、回零单路径。  
4. **不**在本轮改 FB_Servo 点动方向逻辑（已另修）。
