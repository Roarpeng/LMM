# PLC 外部工步模式（Step Mode）接口设计 —— v0.2

> 读者：LMM PLC 负责人、网关维护者、RK3588 上位机开发。
> 依据：LMM `33677cd`（PLC g0.79，`plc/g/*.st`、`config/modbus-map.json`、`gateway/`）。
> 文中 `PRG_Logic.st:N` 等行号均指该版本 `plc/g/` 下的文件。
> 本文同步自视觉仓 `docs/PLC_STEP_MODE.md`；PLC/契约/网关部分以本仓库代码为准。
> 状态：**ST 草稿 + 契约 + mock-plc 已实现**（分支 `feat/step-mode-0.80`，生成 `LMM_g_0.80.xml`），
> 离线验收通过；**未经 InoProShop 编译、未上真机**，待 PLC 负责人审核/编译/台架。离线验收步骤见 §7。

## 0. TL;DR

- 新增第三种操作模式 **外部工步**（`eOpMode=2`），与手动(0) / 自动(1) 三选一。
- RK3588 每 30 ms 发一帧：心跳 + 视觉航向 + **工步块**（工步号、命令号、全部参数）。
  PLC 在**命令号变化时**锁存参数、执行一个工步，回报完成/失败。工步严格**顺序执行**。
- 工步只有 4 个原语 + 中止：**X 走距（带视觉纠偏）/ Z 压到力 / Y 恒力行程 / Y·Z·R 点位**。
  实时闭环（编码器走距、航向差速、同步补偿、恒力、定位、限位）全部留在 PLC。
- **所有上层要调的参数（恒力 F、力控增益、R 角、示教点、拉毛/行进速度、工作宽度）都随工步命令下发**，
  不走现有 `HMI_r*` 参数通道 —— 原因见 §2，那条通道在远程写入时有三个硬问题。
- 占用命令镜像空闲字 76–94 + word5 bit12，状态镜像空闲字 75–87；**不扩 96 字镜像**。
- RK 掉线 300 ms → PLC 中止工步并停；急停/Stop/故障永远优先。

---

## 1. 现有控制模式回顾（为什么要加新模式）

### 1.1 三层结构

```
第 1 层 操作模式   HMI_xAutoMode → eOpMode 0 手动 / 1 自动              PRG_Logic.st:102
        公共安全门 xSafe(急停未按且未锁存) ∧ ¬HMI_xStop ∧ 无轴故障       :106-108
第 2 层 手动下的指令来源  点动(面板/触摸屏/Web) │ 全轴直控 │ 旧 Vis_* 通道
第 3 层 轴级   X：FB_XDual eMode 0~4；Y/Z/R：FB_Servo 优先级
```

FB_XDual 的 `eMode`（`FB_XDual.st:348-392`，优先级 Stop > 旋转 > 外部直控 > 直行）：

| eMode | 触发 | M1/M2 | 视觉航向 | 同步补偿 |
|---|---|---|---|---|
| 0 停 | 无请求 / Stop | Halt | — | — |
| 1 直行 | 点动 X / 走距 `xMoveRel` | 基速 ± trim | ✅ trim=(\|e\|−0.003)×Kp，钳 ±0.01 m/s，滤波 | ✅ 期望同步差含 trim 积分，二者不打架 |
| 2/3 旋转 | 左/右旋 | M1=−M2 | ❌ | ❌ |
| 4 外部直控 | 直控 X 速度 / `Vis_*` | 原样 | ❌ 忽略 | ❌ 无，且无斜坡 |

走距完成判据：两轮编码器平均位移 ≥ 目标（`FB_XDual.st:848`）。

### 1.2 现有四种模式对比

| | A 手动点动 | B 直控·只 Y/Z/R | C 直控·X 速度 | D 自动循环 |
|---|---|---|---|---|
| 进入 | 手动 + 安全门 | 手动 + `xDirectEnable` + 心跳 + `ModeX=0` | 同 B，`ModeX=1` | 自动 + `AutoStart` 上升沿 |
| X | 点动 eMode1 | 仍可点动 eMode1 | eMode4 | 走距 eMode1 |
| 视觉航向生效 | ✅ | ✅（**当前视觉伺服用此模式**） | ❌ | ✅ |
| Z 恒力 | ✅ 力引导 | ❌ 被屏蔽 `:306` | ❌ | ✅ |
| Y/Z/R | 点动 | 速度/绝对/相对 | 同 B | 状态机，R 锁存保持 |
| 掉线 | 网关租约 1 s → Stop | 300 ms 心跳 → 停 | 同 B | **PLC 不看上位心跳**，只有网关 1 s 后航向清零 |

**结论**：没有任何一个现有模式能同时满足"外部按步触发 + 视觉纠偏 + 恒力 + 点位轨迹 + 掉线即停"。
D 最接近但步序写死，且**拉完一道不抬 Z**（第 4 步后直接回第 1 步 X 走距），没有清洗/示教。

---

## 2. 现有参数通道能不能"直接写 PLC"？—— 能写，但不可靠

上层需要调的参数，现状逐项：

| 参数 | 现有字段（命令镜像 word） | 现在 RK 能否经网关写 | 问题 |
|---|---|---|---|
| 恒力目标 F | `HMI_rForceSet` w28 ×100 N | 有条件可写（§2.1） | 有回显 `HMI_rForceSetEcho`（状态 w44），**唯一有回显的参数** |
| 力控"PID" | `HMI_rKpForce` w36 ×1000 | 有条件可写 | **只有 P**，见 §2.4；死区写死 0.5 N；限速取 `HMI_rAutoVelZ`（为 0 时退到 `HMI_rJogVelZ`） |
| R 工作角 | **无** | ❌ | 自动循环在启动瞬间锁存当前 R（`:321`）；`HMI_rDirectPosR` 只在直控下有效 |
| 示教点位 | **无** | ❌ | PLC 没有点位表 |
| 拉毛速度（Y 恒力行程） | `HMI_rAutoVelY` w22 | 有条件可写 | 自动循环里 Y 回零也用它，不能分开设 |
| 行进速度（X） | `HMI_rAutoVelX` w20 / `HMI_rJogVelX` w8 | 有条件可写 | — |
| 单次工作宽度 | `HMI_rAutoDistX` w18 | 有条件可写 | — |
| Y 行程 | `HMI_rWheelBase` w26 | 有条件可写 | **被钳在 4~6 m**（`PRG_Logic.st:241`），行程 < 4 m 写不进去 |
| 抬起/接近高度 | **无** | ❌ | — |
| 纠偏 Kp | `HMI_rKpTrack` w34 | 有条件可写 | 视觉侧已在写 |
| 加减速 | `HMI_rAcc*/Dec*` w38–53 | 有条件可写 | RETAIN；<阈值 PLC 兜底 100 |
| 软限位 | `Cfg_rLim*` | ❌ 不在镜像 | **应保持只在 PLC 侧改**（安全参数） |

### 2.1 问题一：参数只在"控制源 = 远程"时才生效

`PRG_TcpHmi.st:403-428`：上表所有 `HMI_r*`（**包括 `HMI_rHeadingErr`**）只在 `eCtrlSrc = 1` 时从网关影子复制。
而 `eCtrlSrc` 切到 1 的条件（`PRG_TcpHmi.st:383-398`）是远程发了**操作位**（启动/停止/点动/回零/力引导/去皮…），
**单纯写参数不算**；面板任一按键又会切回 0；网关掉线也切回 0。

后果：
- RK 写了 F，如果此前最后一次操作来自面板/触摸屏，**PLC 静默不采纳**，且除 F 外无回显可查。
- **安全隐患（现有代码即存在）**：视觉在写航向，操作员在**面板**点动 X → `eCtrlSrc=0` →
  `HMI_rHeadingErr` **冻结在最后一个值**，PLC 持续按旧误差打差速。建议无论是否上工步模式都修：
  `eCtrlSrc<>1` 或 `NOT Tcp_xOnline` 时 `HMI_rHeadingErr := 0`。

### 2.2 问题二：整块覆盖，未写的参数被写成 0 并掉电保持

`eCtrlSrc = 1` 期间，**全部约 25 个参数每扫描**都从网关镜像复制。网关镜像初值是 fail-safe 全 0
（`gateway/lib/modbus-store.js` `FAIL_SAFE_COMMAND_VALUES`，`server.js` 未传 `initialCommands`）。
所以只要网关重启后没人写过某个参数，一旦远程发生任何操作，PLC 上的该 RETAIN 参数就被写成 0
并**掉电保持**（速度 0、F=0、跨距被钳到 4 m…）。触摸屏上改过的值同样会被覆盖。

### 2.3 问题三：无回读

状态镜像除 F 外不回显任何参数，RK 无法确认 PLC 当前用的是什么值。

### 2.4 力控现状：纯 P，作用于 Z 速度

`plc/src/FB_ForceFollow.st`：`vZ = −Kp·(F_set − F_act)`，限幅 `±VelMax`，死区 0.5 N 内输出 0，到软限位截断。
- 由于输出是**速度**、Z 位置是其积分，P 力控对"力→位置"等效带积分，静差为 0 —— 对恒力跟随而言 **P 一般够用**，
  不建议上来就加 I/D。真正需要的是：死区可调、力信号低通、以及 Kp 的分辨率。
- Kp 量纲 (m/s)/N，镜像 ×1000 → 最小 0.001 (m/s)/N，即 10 N 误差就给 1 cm/s。现场 Kp 大概率要更细，
  本草案工步块里改为 ×1e6。

**结论**：现有参数通道只适合人在 WebHMI 上手调，**不适合当上位机的参数下发通道**。
工步模式下，参数随每条工步命令下发、PLC 在命令号变化时锁存、并回显实际采用值（§4）。

---

## 3. 外部工步模式：控制逻辑

### 3.1 进入 / 退出

`eOpMode := 2` 当且仅当：
`HMI_xStepMode`（新，命令 w5 bit12）∧ `NOT HMI_xAutoMode` ∧ 公共安全门。

- `HMI_xStepMode`、工步块字段与 `HMI_wDirectSeq` 一样在 `PRG_TcpHmi` 里**每周期无条件跟随**影子
  （同 `PRG_TcpHmi.st:179-190` 直控字段的做法），**不受 `eCtrlSrc` 门控**。
- 工步模式下 `HMI_rHeadingErr` / `HMI_rKpTrack` 也无条件跟随（解决 §2.1）。
- `eOpMode=2` 时：手动点动、自动循环、全轴直控（`Direct2_xSafe` 已要求 eOpMode=0）全部不生效；
  **面板 Stop / 急停 / 复位照常有效**。
- 退出：清 `HMI_xStepMode` → 执行中的工步以 `ERR_MODE` 失败 → eOpMode 回 0。
- **进入模式瞬间吞掉当前 `HMI_wStepId`**（不执行模式切换前残留的命令）。RK 必须先进入模式、再递增命令号。
- 网关离线（`Tcp_xOnline=FALSE`）时 PLC 自行清 `HMI_xStepMode`；网关写者断开时网关 fail-safe 也会把它写成 FALSE。
- 航向误差（实现细节）：`Tcp_xOnline ∧ (eCtrlSrc=1 ∨ HMI_xStepMode)` 时采用远程值，**否则清零**。
  这同时修了 §2.1：面板点动 X 时不再沿用冻结的旧航向（行为变化：面板点动时视觉纠偏不生效）。

### 3.2 心跳

复用 `HMI_wDirectSeq`（w75）与 `Cfg_tDirectTimeout`（300 ms）看门狗（`PRG_Logic.st:111-119`）。
工步模式下心跳丢失 → 当前工步失败 `ERR_HEARTBEAT`、所有工步运动减速停、力跟随关闭；
**不自动恢复**，RK 重新上线后须重新下发命令。

### 3.3 命令握手

```
RK  : 每 30 ms 发 {HMI_wDirectSeq++, HMI_rHeadingErr, HMI_rKpTrack, 工步块(全部字段)}
      新命令 = 填好参数 + HMI_wStepId+1，**同一条 t:"w" 里发出**（网关整帧原子写入）
PLC : 发现 HMI_wStepId ≠ 上次 → 锁存全部工步参数 → 校验 → 执行
      Step_wIdEcho := HMI_wStepId；Step_iState: 1 执行 → 2 完成 / 3 失败
RK  : 看到 IdEcho=本次 Id 且 State=2 才发下一条；State=3 进入故障处理
```

- **参数锁存**：执行中改工步块字段**无效**，只有新 Id 才生效（防止半帧参数）。
- **忙时新命令**：`cmd≠0` 且上一工步仍在执行 → 视为协议错误：**停当前工步**，新命令以 `ERR_BUSY` 失败
  （回显的是新命令号）。正常 RK 不会这样发；`cmd=0` 永远立即受理（中止，State=2）。
- **重复 Id**：同 Id 重复帧不重新执行（30 ms 重发是常态）。

### 3.4 工步原语

所有工步期间 **R 保持**在工步开始时锁存的实际角度（与自动循环 `xCmdHoldR` 同机制），
R 只能通过工步 4 改变。工步 1–3 期间不在本工步内运动的轴保持静止（伺服位置保持）。

| cmd | 名称 | 动作（PLC 内部） | 使用的参数 | 完成判据 | 失败 |
|---|---|---|---|---|---|
| 0 | 中止/空闲 | 所有工步运动减速停，关力跟随 | — | 立即 State=2 | — |
| 1 | X 走距 | `xMoveRelX`，eMode1，**视觉 trim 生效** | `rStepDist`(±m)、`rStepVel` | `AxisFb_xMoveDoneX` | 超时、Stop/急停/故障 |
| 2 | Z 压到力 | [可选去皮 + 300 ms] → 力跟随 | `rStepForce`、`rStepKpForce`、`rStepVelZMax`、flags.bit3 去皮 | 力 ≥ **F − 0.5 N** 持续 100 ms（0.5 N = 力跟随死区，死区内 Z 不再动，判 ≥F 会永远等不到） | Z 到 `Cfg_rLimZNeg` 仍未达力 = `ERR_NO_CONTACT`；超时 |
| 3 | Y 恒力行程 | 力跟随 + Y 相对走 | `rStepDist`、`rStepVel`(拉毛速度)、`rStepForce`、`rStepKpForce`、`rStepVelZMax` | `AxisFb_xMoveDoneY` | Y 目标越限（拒绝，不钳位）、超时；力偏离只报 `Step_xForceLow` 不中止（demo 先观察） |
| 4 | 点位 | Y/Z/R 绝对定位，按 flags 掩码选轴，**同时**运动 | `rStepPosY/Z/R`、`rStepVel`(Y/Z)、`rStepVelR`、flags.bit0-2 | 所选轴全部静止且误差 < 1 mm / 0.1° | 目标越限（拒绝）、超时 |

- **工步 2、3 完成后力跟随保持**，直到下一条命令（否则两步之间压力会松）。下一条一般是工步 4 抬 Z，自然结束力跟随。
- 示教轨迹 = RK 依次发多条工步 4；"先抬 Z 再横移再下 Z"由 RK 拆成多点，PLC 不做路径规划。
- 停留/沥干是**没有运动**的等待，在 RK 侧计时，不占 PLC 工步。
- 越限一律**拒绝**而非钳位（钳位会让 RK 以为到了示教点）。
- 工步 4 同时选 Y 和 Z 时共用 `rStepVel`，须 ≤ 两轴直控上限的较小者（默认 Z 0.2 m/s）；要不同速度就拆成两条。
- 速度上限复用 `Cfg_rDirectVelMaxX/Y/Z/R`（0.5 / 0.5 / 0.2 m/s / 30 °/s）；默认超时：工步 1/3 = 距离/速度×2+5 s，工步 2/4 = 60 s。

### 3.5 一道作业的工步序列（RK 编排，顺序执行）

```
#   cmd  参数                                   说明
1   4    Y,Z,R = 行进姿态(示教)                  行进姿态（可设在水槽上方，X 走时顺便沥干）
2   1    dist = 0.60 + 补偿, vel = 行进速度      X 走距，视觉纠偏
3   4    Y,Z,R = 起刷点(示教)                    含 R 工作角
4   2    F, Kp, VelZMax, 去皮                     Z 下压到恒力
5   3    dist = Y 行程, vel = 拉毛速度, F, Kp     恒力拉毛（单向）
6   4    Z = 抬起高度（只选 Z）                   结束力跟随
7   4×n  清洗轨迹各点（示教）                     本道需清洗时；每点后 RK 计时停留
8        —                                        回到 1
```

清洗策略（每道 / 每 N 道 / 仅结束）、停留与沥干时间都在 RK，不影响 PLC。

### 3.6 安全与异常（优先级从高到低）

| 事件 | PLC 行为 | 工步状态 |
|---|---|---|
| 急停 / Stop / 轴故障 | 现有公共安全门：`AxisCmd_xStopAll` | 3 失败，`ERR_SAFETY` |
| 心跳 300 ms 丢失 | 工步运动减速停，力跟随关 | 3 失败，`ERR_HEARTBEAT` |
| 退出工步模式 | 同 cmd 0 | 3 失败，`ERR_MODE` |
| 视觉丢目标 | PLC 无感知（航向=0 即不纠偏） | 不变；RK 连续失效则不发下一条 |
| 超时 | 本工步运动停 | 3 失败，`ERR_TIMEOUT` |

失败后 PLC 停在原地，**不自动回退、不自动重试**；由操作员在 RK Web 上决定（重试本步 / 抬 Z / 中止作业）。

---

## 4. 契约字段（`config/modbus-map.json` 新增）

> 契约生成器原先只允许 scale 100/1000，本次放宽到 10/100/1000/1000000（`tools/generate_modbus_map.py`）；
> 网关编解码与 PLC 对 scale 无假设。协议版本号不变（PLC 校验 `wVersion=256`）。

### 4.1 命令镜像（w5 bit12 + w76–94，恰好用完剩余空闲字）

| word | 字段 | 类型 | 缩放 | 单位 | 说明 |
|---|---|---|---|---|---|
| 5.12 | `HMI_xStepMode` | BOOL | — | — | 请求外部工步模式 |
| 76 | `HMI_iStepCmd` | UINT | — | — | 0 中止 / 1 X走距 / 2 Z压力 / 3 Y恒力 / 4 点位 |
| 77 | `HMI_wStepId` | UINT | — | — | 命令号，变化即新命令 |
| 78 | `HMI_wStepFlags` | UINT | — | — | bit0/1/2 点位选 Y/Z/R；bit3 压力前去皮 |
| 79–80 | `HMI_rStepDist` | SCALED_DINT | 1000 | m | 工步 1/3 相对距离（带符号） |
| 81 | `HMI_rStepVel` | SCALED_INT | 1000 | m/s | 工步 1 X / 工步 3 Y / 工步 4 Y·Z 速度 |
| 82 | `HMI_rStepVelR` | SCALED_INT | 100 | °/s | 工步 4 R 速度 |
| 83–84 | `HMI_rStepPosY` | SCALED_DINT | 1000 | m | 工步 4 |
| 85–86 | `HMI_rStepPosZ` | SCALED_DINT | 1000 | m | 工步 4（Z 向下为负，0=顶） |
| 87–88 | `HMI_rStepPosR` | SCALED_DINT | 1000 | ° | 工步 4 |
| 89–90 | `HMI_rStepForce` | SCALED_DINT | 100 | N | 工步 2/3 恒力目标 |
| 91–92 | `HMI_rStepKpForce` | SCALED_DINT | 1000000 | (m/s)/N | 工步 2/3 力控 P |
| 93 | `HMI_rStepVelZMax` | SCALED_INT | 1000 | m/s | 工步 2/3 力跟随 Z 限速 |
| 94 | `HMI_tStepTimeout` | UINT | 10 | s | 0 = PLC 默认（按距离/速度估算 ×2 + 5 s） |

### 4.2 状态镜像（w75–87）

| word | 字段 | 类型 | 缩放 | 说明 |
|---|---|---|---|---|
| 75 | `Step_wIdEcho` | UINT | — | 已受理的命令号 |
| 76 | `Step_iCmdEcho` | UINT | — | 已受理的工步类型 |
| 77 | `Step_iState` | UINT | — | 0 空闲 / 1 执行 / 2 完成 / 3 失败 |
| 78 | `Step_iErr` | UINT | — | 见 §4.3 |
| 79 | `Step_iPhase` | UINT | — | 工步内部子阶段（诊断） |
| 80 | 位字 | BOOL×16 | — | bit0 `Step_xModeActive`(eOpMode=2) / 1 `Step_xForceFollow` / 2 `Step_xForceReached` / 3 `Step_xForceLow` / 4 `Step_xRHold` / 5–7 `AxisFb_xStandstillY/Z/R` |
| 81–82 | `Step_rProgress` | SCALED_DINT ×1000 | m | 工步 1/3 已走距离 |
| 83–84 | `Step_rKpForceEcho` | SCALED_DINT ×1e6 | (m/s)/N | 实际采用的力控 Kp |
| 85–86 | `Step_rRHoldPos` | SCALED_DINT ×1000 | ° | 当前 R 保持目标 |
| 87 | `Step_tElapsed` | UINT ×10 | s | 本工步已用时 |

`HMI_rForceSetEcho`（w44）语义改为"实际下发给力跟随的 F"（工步模式下即锁存的 `rStepForce`）。
状态 w80 bit5–7 = `AxisFb_xStandstillY/Z/R`；w88–94 保留。

### 4.3 错误码

| 码 | 名称 | 含义 |
|---|---|---|
| 0 | OK | |
| 1 | ERR_MODE | 不在工步模式 / 中途退出 |
| 2 | ERR_PARAM | 参数非法（速度≤0、超上限、Kp≤0…） |
| 3 | ERR_LIMIT | 目标越软限位（拒绝，不钳位） |
| 4 | ERR_BUSY | 上一工步执行中又来非 0 命令 |
| 10 | ERR_TIMEOUT | 超时 |
| 11 | ERR_SAFETY | 急停 / Stop / 轴故障 |
| 12 | ERR_HEARTBEAT | 心跳丢失 |
| 20 | ERR_NO_CONTACT | Z 到下限仍未达力 |

---

## 5. 上层参数归属（谁存、怎么到 PLC）

| 参数 | 存放 | 下发方式 | 回读 |
|---|---|---|---|
| 恒力 F、力控 Kp、Z 力跟随限速 | RK 参数 YAML | 工步 2/3 参数 | `HMI_rForceSetEcho`、`Step_rKpForceEcho` |
| R 工作角 | RK（属于起刷点示教） | 工步 4（选 R） | `AxisFb_rPosR`、`Step_rRHoldPos` |
| 示教点（行进姿态、起刷点、清洗轨迹 n 点） | RK 示教 YAML | 工步 4 | `AxisFb_rPosY/Z/R` |
| 拉毛速度 / 行程 | RK | 工步 3 | `Step_rProgress` |
| 行进速度 / 工作宽度(0.60+补偿) | RK | 工步 1 | `Step_rProgress`、`AxisFb_rPosM1/M2` |
| 抬起高度 | RK | 工步 4（选 Z） | `AxisFb_rPosZ` |
| 纠偏 Kp | RK（视觉配置已有 `plc.kp_track`） | 每帧 `HMI_rKpTrack` | — |
| 加减速、软限位、驱动参数 | **PLC**（调试期在触摸屏/WebHMI 设，RETAIN） | 不由 RK 下发 | — |

原则：**会随工艺/现场调整的值归 RK**（唯一来源、可版本化、Web 可调）；**保护机器的值归 PLC**。

---

## 6. 实施清单与进度

**PLC（LMM 分支 `feat/step-mode-0.80`）—— 已起草，待 PLC 负责人审核/编译/烧录**
1. ✅ `tools/patch_g080.py`：0.79 → 0.80，GVL 新增 §4 全部变量（`plc/GVL.st` 同步文档）。
2. ✅ `plc/g/PRG_TcpHmi.st`：解码 w5.12、w76–94 直写 `HMI_*`；网关离线清 `HMI_xStepMode`；编码状态 w75–87；航向清零修复。
3. ✅ `plc/g/PRG_Logic.st`：`eOpMode=2`；工步状态机；力参数改为局部选用值、扫描末尾一次性写 `AxisCmd_rForce*`
   （避免 ETHERCAT 任务采到中途值）；`HMI_rForceSetEcho` 回显实际下发值。
4. ⏸ 自动循环 D 的"拉完不抬 Z"、"判 ≥F 遇死区可能等不到"两个已有问题**本草案未改**（不动在役流程），单独评估。
5. ✅ `LMM_g_0.80.xml` 生成；`check_plcopen_xml.py` 通过；`check_lmm.py`（已支持传路径）与 0.79 基线同为 4 条历史 ERROR，
   **无新增**。❌ InoProShop 编译未做（本机无编译器）—— 尤其留意 `UDINT_TO_REAL(TIME_TO_UDINT(...))`、`T#1D`。

**契约、网关与 WebHMI** —— ✅ 已完成
6. `config/modbus-map.json` 增字段，`docs/plc/MODBUS_MAP.md` 已重新生成。网关按契约通用编解码，未改代码。
7. `gateway/lib/mock-plc.js`：与 ST 同语义的工步状态机 + 地面接触力模型（`MOCK_GROUND_Z`）；
   `Direct2_xOnline` 改为真实 300 ms 看门狗。
8. `gateway/test/step-mode.test.js`（13 项）+ `gateway/scripts/smoke-step.js`（上位机模拟 + 故障注入）。
9. WebHMI 直控页新增只读"外部工步"卡；运行方式显示支持"外部工步"。

**RK3588（视觉仓，不在本仓库）** —— 未开始
10. `comm/plc_direct.py` 拆航向通道/工步通道；`comm/plc_contract.py` 工步字段权限档；
    作业状态机、示教/参数 YAML、Web 作业/示教/参数页、局域网口令与操作者锁；`tools/mock_gateway.py` 同步。

## 7. 验证路径（demo 优先）

### 7.1 离线验收（不需要 PLC，现在就能做）

```bash
cd gateway                           # Node ≥ 18：source ~/.nvm/nvm.sh && nvm use 20
npm test                              # 网关全部测试，含 step-mode.test.js 13 项，期望 0 fail
node scripts/smoke-step.js            # 上位机模拟跑一道作业，逐步打印位置/力/用时，期望 [step] PASS
node scripts/smoke-step.js --hold     # 同上，跑完不退出；浏览器开 http://127.0.0.1:18081/ → 直控页「外部工步」卡
for f in heartbeat stop busy nocontact limit; do node scripts/smoke-step.js --fault $f; done
                                      # 故障注入，期望各自 PASS（得到 12/11/4/20/3）
cd .. && python3 tools/inject_g.py --check && python3 tools/patch_g080.py \
  && python3 tools/check_plcopen_xml.py LMM_g_0.80.xml && python3 tools/check_lmm.py LMM_g_0.80.xml
                                      # ST 可解析、XML 合法；check_lmm 只应有 0.79 就有的 4 条历史 ERROR
git diff main -- plc/g/               # 人工审 ST 改动（重点：PRG_Logic 0.80 工步段）
```

mock 是"与 ST 同语义的 JS 模型"，**不能代替 PLC 编译与台架**：它验证协议、握手、时序与失败路径，
ST 本身的正确性要靠 §7.2。

### 7.2 后续

| 阶段 | 环境 | 验什么 |
|---|---|---|
| 编译 | InoProShop 导入 `LMM_g_0.80.xml` | 0 error |
| 台架 | 真 PLC 0.80，**`HMI_xForceSimEnable` + `HMI_rForceSim` 模拟力**，Z 不接触；`smoke-step.js --url ws://<网关>:8080 --allow-motion` | 工步 1–4 真轴运动、点位精度、心跳/急停停机 |
| 现场 | 真力传感器、真地面 | F/Kp/Z 限速整定、工作宽度补偿、清洗轨迹示教 |

## 8. 待确认

1. 工步 2 "压到力"判据：`≥F−0.5N 持续 100 ms` 是否合适；是否还需要"最大下压行程"参数（目前用 `Cfg_rLimZNeg`）。
2. 工步 3 力偏离（`Step_xForceLow`）是否要中止，阈值多少。
3. `HMI_rStepKpForce` 量程：现场 Kp 大致数量级。
4. 是否接受 w76–94 用尽；后续再加字段需扩镜像（三方同步）。
5. 工步模式由谁切入：仅 RK Web，还是触摸屏也要能切（触摸屏切入需在 `PRG_TcpHmi` 加面板侧请求位）。
