# equipment-plc-workflow state

## Meta
- Project: LMM XYZR + 力传感
- Entry: change-request（X 双电机速度透传 + WebHMI v2）
- Updated: 2026-09-12

## Current
- Stage: S6/S7 — WebHMI v2 与 PLC 0.63 增量已落地（Web 为验收视图，MD 为源）
- Spec: `docs/superpowers/specs/2026-09-12-x-speed-webhmi-v2-design.md`
- Plan: `docs/superpowers/plans/2026-09-12-x-speed-webhmi-v2.md`
- 在役基线：`LMM_g_0.67.xml`（PLC 导出；Modbus TCP 从站 Type 40502 通道 `16#1000/16#1100` ↔ `%IW103/%QW44`；POU 逻辑=0.66+0.64+0.63；**WebHMI 实控验证 OK**）
- 通讯方向：Gateway（Modbus TCP 主站）→ PLC（从站）`192.168.1.88:502`；命令 Holding `4096..4159`（0x1000）、状态 `4352..4415`（0x1100）
- 速度透传（两层）：
  - Web 先行：状态 word29/30 `Direct_rVelM1Act/M2Act`（实际速度，各模式有效）已在 WebHMI v2「X 双驱」显示，**无需重烧**
  - PLC 0.63：新增状态 word32..38（`AxisFb_rVelActM1/M2`、Moving/Powered/SyncWarn/Fault、`AxisFb_rSyncErr`）
- 交付物：
  - `web/live/index.html` v2（自动/手动/X 双驱/调试/日志；键盘点动、X 直控滑条、寄存器表、趋势/快照、CSV）
  - `gateway/server.js`（`GET /health`、`t:"hello"/"lease"`、离线合并、`PLC_POLL_MS` 默认 50）
  - `gateway/lib/mock-plc.js`（实际速度/新字段）、`gateway/lib/modbus-master.js`（`getDiagnostics()`）
  - `tools/patch_g063.py` → `LMM_g_0.63.xml`；`gateway/scripts/smoke-webhmi.js`
- 验证：
  - `cd gateway && npm test` → **43 PASS**
  - `python3 tools/patch_g063.py` 幂等；`LMM_g_0.63.xml` XML 解析 OK；`inject_g.py --check` OK
  - Mock 冒烟 `node gateway/scripts/smoke-webhmi.js` → PASS（页面/health/map/WS hello·status·lease·新字段）
- Next: 真机联调 WebHMI v2（自动/手动/急停与面板一致；X 双驱页 M1/M2 实际速度跟随；点动按住动/松开停）

## Field findings（2026-09-12）
- **已解决（2026-09-12）**：Gateway 连 `192.168.1.88:502` 成功；PLC 程序侧正常（`MB_StatusOut[0]=19533`、`[2]` 每周期跳）。
- 根因：InoProShop 从站映射「起始地址」字段是**十六进制**，填 `1000`/`1100` 实际为 `0x1000`=**4096** / `0x1100`=**4352**；
  网关原按十进制 1000/1100 读写，落到空白区 → `MAGIC_MISMATCH,VERSION_MISMATCH`。
- 实测：Holding `4096..4159` = 命令镜像（PLC 状态 `word3` 回显命令序号），`4352..4415` = `0x4C4D 0x0100` + 序号递增。
- 处理：`config/modbus-map.json` 基址改为 4096/4352（**无需再改/下载 PLC**）；`generate_modbus_map.py` 与全部文档同步；
  Gateway 另有 `PLC_CMD_BASE`/`PLC_STATUS_BASE` 覆盖、协议错不再断开重连、`/health`、只读探针 `probe-plc.js`。
- 验证：真机 `/health` → `statusIsOffline=false`、`lastError=null`；启动日志 `cmd@4096 status@4352`；`npm test` 43 PASS。
- 踩坑备忘：从站 I/O 映射变量名不能与 GVL 同名（`MB_CmdIn`/`MB_StatusOut`），否则编译 `C0136/C0018`。
- **急停锁存 / 心跳（2026-09-12）**：真机状态 `HMI_iAlarmShow=1001`、`HMI_xLampEStop=TRUE`、`HMI_eDevState=2`、
  `AxisFb_xReady=FALSE` → PLC `xEStopLatched` 锁存，所有轴被 `xSafe` 锁住。
  - 操作：**松开物理急停 → 网页按一次「复位」**（`HMI_xStopHold3s` 上升沿）清锁存 + 轴故障复位。
  - Gateway fail-safe 由 `HMI_xEStop=FALSE` 改为 `HMI_xStop=TRUE + HMI_xEStop=TRUE`（停止不锁存）；
    新增 `store.advanceHeartbeat()` 每周期推进心跳，避免停顿 >1s 被判远程超时。
  - `npm test` → **44 PASS**。
- **1005 误报修复（2026-09-12）**：`Force_xTimeout`/`Force_xCommOk` 原有两个写者——`PRG_Force485`（真实回文判定）
  与 `PRG_Axis_Control`（`FB_Force` 的“原始值 2s 不变”看门狗）。力稳定时后者误置 TRUE → 偶尔报警 1005。
  - 修：删除 `PRG_Axis_Control` 里 `Force_xCommOk := fbForce.xCommOk;` / `Force_xTimeout := fbForce.xTimeout;`，
    使 `PRG_Force485` 成为唯一写者；`tools/patch_g064.py` 由 0.63 生成 **`LMM_g_0.64.xml`**（幂等、XML 解析 OK）。
  - 代价：启动时 3 次读失败 → 1006（`Force_xSlaveFail`）；运行中失联的持续检测另行用 RTU 从站诊断位（待现场确认）。
- **1007 静默误报修复（2026-09-12）**：`FB_XDual` 的 M1/M2 就绪判据误含 `NOT xStop`：
  `xReadyM1 := xEnable AND NOT xStop AND NOT xFaultM1`。`xStop` 来自 `AxisCmd_xStopAll`（`HMI_xStop` 等），
  设备停止/静默时 `xStop=TRUE` → Ready 立即 FALSE，而 `AxisCmd_xPower` 仍真且无故障 → `tonReady` 2s 后报 1007。
  - 0.65 曾误改为 `xPoweredM1/M2 AND NOT xFault`：`xRegOn` 在静态（eMode=0 且非停止）为 FALSE → `xPowered=FALSE` → 静态持续报 1007（回归）。
  - **正确修（0.66）**：`xReadyM1/M2 := xEnable AND NOT xFaultM1/M2`（不含 `xStop`、也不要求 `xPowered`）；
    `tools/patch_g066.py` 由 0.65 生成 **`LMM_g_0.66.xml`**。
  - `xPowerGate` 仍含 `NOT xStop`，运动互锁不变；仅「就绪」/1007 判据修正。
- **WebHMI v3（2026-09-12）**：前端重构为 `web/live/{index.html, styles.css, app.js}`（无构建）；信息架构 = 总览/自动/手动/X双驱/力传感/趋势/报警/调试/系统，左导航 + 设备视图 + 急停覆盖层；通讯层与 WS 契约不变。
  - Spec：`docs/superpowers/specs/2026-09-12-webhmi-v3-ui-design.md`。
  - `gateway/test/web-client.test.js` 改为读取三文件拼接校验；`npm test` 44 PASS、运行时自检 + Mock 冒烟 PASS。
- **视觉直控全轴（2026-09-12，change-request；实现完成，待烧录 0.68）**：视觉工控机**也运行 WebHMI**，与操作员共用同一 WS/JSON 接口与页面 → **不新增 /vision/* 协议**；把「每轴直控」纳入现有命令/状态映射。
  镜像 **64W → 96W**（尾部序号 63→95，单次 FC16/FC03 内）；新增每轴 方式/速度/位置 与 Y/Z/R 实际速度/直控状态反馈；
  **M1/M2 不单独写位置**（速度环 + 机械耦合；X 位置为整机目标 `HMI_rDirectPosX` 或视觉自闭环）；
  使能/报警/限位/急停仍 **PLC 独占**；`PRG_TcpHmi` 解码、`PRG_Logic` 直控路由 + `HMI_wDirectSeq` 300ms 看门狗；`PRG_Axis_Control` 基本不变。
  - 实现：契约 `config/modbus-map.json`（96W，命令 60..75 / 状态 39..45）；PLC **`LMM_g_0.68.xml`**（`tools/patch_g068.py` 幂等，sha `54cebbe4…`；新建 `plc/g/PRG_TcpHmi.st`，GVL +58 变量）；Gateway 分块 95+1 + mock；WebHMI 新增「直控」页。
  - 验收：`ET.parse(0.68)` OK、`inject_g --check` OK、`generate_modbus_map.py` 与 `MODBUS_MAP.md` 同步、`npm test` 44 PASS、`smoke-webhmi` PASS、无 `ARRAY[0..63]`/`MB_CmdIn[63]` 残留。
  - 现场待办：InoProShop 导入 0.68 → 编译 0 error → 下载（设备树两条通道已补齐 64..95 的 Value）。
- **0.68 上线事故与修复（2026-09-12）**：0.68 把镜像扩到 96W，但 Modbus TCP 从站参数 `MODBUSCHANNELSET` 的 `ReadRegLeg/WriteRegLeg` 仍是 **64**（0.67 遗留，agent 漏改）→ 状态输出区只发布 64 字，`MB_StatusOut[95]` 读回 0 → 网关 `seq==tail` 校验失败 → 判离线，webHMI 连不上。
  - 立即修复（无需重烧）：`modbus-codec.validateImage` 在尾序号字为 0（未映射）时跳过 `SEQUENCE_MISMATCH`；**更新网关并重启**即恢复。
  - 根治：`tools/patch_g069.py` 由 0.68 生成 **`LMM_g_0.69.xml`**（两条通道 Leg 64→96，sha `6201f685…`，幂等），导入后状态尾部恢复发布。
  - 验证：真机 `/health` → `connected:true, statusIsOffline:false, lastValidStatusAgeMs:28, errorCount:0`；`npm test` 44 PASS。
  - 设计：`docs/superpowers/specs/2026-09-12-vision-axis-control-design.md`（含 Gate C 写者矩阵）；接口：`docs/plc/VISION_AXIS_API.md`。
- **WebHMI v3 六页完善 + 力峰值接口（2026-09-12，完成）**：直控/调试/趋势/报警/力传感/系统 达到最终可用版本。
  - 验收：`node --check app.js` OK、`tools/dom-stub-check.js` OK（336 id / 无异常）、`npm test` 44 PASS、`smoke-webhmi` PASS、section 10:10 平衡；新 PLC 0.70 `sha b5a26d97…`。
  - 新 PLC 接口：`HMI_xForcePeakReset`（命令 word5 bit11，脉冲）、`Force_rPeak`（状态 46，SCALED_DINT×100，N）、`Force_wRaw`（状态 48，UINT 原始计数）；PLC 出 **0.70**。
  - 网关：`/health` 增 `version/startedAt`；mock 上报力峰值/原始值；冒烟 `required/actFields` 同步（PASS）。
  - Web：直控加视觉角度纠偏；力传感加峰值/原始值/复位；报警历史 localStorage 持久化 + 未确认计数；趋势加坐标/图例/暂停/窗口；调试加寄存器过滤/命令历史/WS 报文/日志过滤/RTT 曲线；系统用 /health 全量 + 一键自检 + 诊断导出。
- **现场定稿 0.67（2026-09-12）**：`LMM_g_0.67.xml` 由 PLC 导出，POU 与 0.66 完全一致；
  设备树 TCP 从站为 `Type 40502 ModbusTcpSlave`（Port 502, UnitID 255），Channel 01 input `16#1000..103F`→`%IW103`(MB_CmdIn)、
  Channel 02 output `16#1100..113F`→`%QW44`(MB_StatusOut)。**WebHMI 自动/手动实控验证通过**，报警 1007/1005 不再出现。

## Field findings（brownfield-debug，2026-09-12 晚）

- **X− 点动顿挫/停死（现场报障）**：WebHMI jog 模式，X− 一顿 2~3 次后停死不动；X+ 顺畅可直行。
  - 代码核查：`FB_XDual`（0.67 与 0.69 逐行仅差注释）方向对称——命令字 word4 bit6/bit7、模式选择、速度合成、Execute/Direction、Halt 全对称；设备树 5 轴 `SWLimitEnable=FALSE`（无软限位）。0.59 单沿起步（消 250Hz 沿风暴）已在 0.67/0.69。
  - **已发现代码级缺陷（方向无关）**：`xTrimPulse` 限频重触发写作 `xTrimPulsePrev := xTrimWant`（应回写 `xTrimPulse`），导致 want 持续为真时脉冲恒 0 → 起步沿之后 `rVelLatch` 不再刷新，稳态视觉 trim/sync 修正不生效。可能放大「M2 拖后」。
  - 真机：`192.168.1.88:502` 可达，运行 96W 镜像（0.69/0.70）；静置 `AxisFb_xReady=1`、`rSyncErr≈0`、无 M1/M2 故障、pos≈0.491m。
  - 取证工具：`gateway/scripts/trace-x-live.js`（只读；同采命令镜像 4096 与状态镜像 4352，输出 `gateway/x-trace-live.csv`）。
  - **取证结论（2026-09-12 晚；真机录波 `gateway/x-trace-live.csv`，8 段 jog：4×X+ / 4×X−）**：
    - 命令位全程 =1（无丢失）；`vCmd=±0.110`（`HMI_rJogVelX=110`，`HMI_rAccX=HMI_rDecX=300`）符合设定；`AxisFb_xFaultM1/M2` 恒 0、`HMI_iAlarmShow=0`。
    - X+：位置速率 **+0.107~+0.109 m/s**，按住至录波结束全程不 stall（`vAct` 符号抖动是反馈纹波，位置平滑单调）。
    - X−：移动段 −0.070~−0.103 m/s，跑 **6~13s 后位置速率塌到 0.003~0.008 m/s（顿死后不动）**，此时命令仍 −0.11、双轴 `powered=1`、`syncWarn` 置位、`xFaultM1=0`。
    - 现场 M1 驱动红灯闪、停一会自恢复 → **根因 C：X− 方向驱动/机械负载不对称（M1 过载告警）**，非 PLC 逻辑（方向对称、0.59 单沿在、无软限位）。
    - 副发现：`AxisFb_xFaultM1` 映不出驱动告警（`AxisM1.bError` 未置位），驱动红灯在 WebHMI 不可见。
  - **现场澄清（用户）**：M1 驱动**故意反向**（设备树 `MDX_EC→Axis` InvertDirection=TRUE；同向会与 M2 拉扯）；M1/M2 **均直连车轮**（无减速箱）；**过载 + 跟随误差都报过**。
  - **设备树核对**：X 双驱 M1=`MDX_EC` / M2=`MDX_EC_1`，**两者均 0x6060=9（CSV 速度模式）**，非混合模式；Y/Z/R=`MDX_EC_2/3/4` 为 0x6060=8（CSP）。=> 两轮同构速度环 + 机械刚性耦合；任何速度环增益/限幅不一致都会退化成互相较劲。
  - 待办：① 读 M1 驱动故障码（过载/跟随误差具体 Er.xxx）；② 逐项对齐 M1/M2 速度环增益、滤波、**分方向转矩/电流限幅 0x60E0/0x60E1、0x6072**（M1 反向时限幅被镜像，非对称限幅会让 X− 偏弱）；③ X− 阻力/车轮打滑/重量转移等机械核查；④ `xTrimPulse` 重触发逻辑评估（直接"修好"会每 200ms 重踢 Execute，有 0.58 共振风险，需台架验证）；⑤ 状态镜像加轴状态/驱动错误码透传。

## 0.71 交付：X 双驱 M1/M2 转矩/电流回传（2026-09-12 晚，待烧录）

- 背景：驱动 TxPDO 固定映射，`0x6077/0x6078/0x606C` 在 CoE 字典存在但**加不进 PDO**；改用 Inovance 的 `ETC_CO_SdoRead`（EtherCATStack，按从站物理地址读，非循环 SDO）。
- PLC：`FB_XDual` 新增 4 个 `ETC_CO_SdoRead`（M1/M2 的 0x6077 转矩、0x6078 电流），100ms 时隙 ×4 轮询（单次一个 SDO，各自独立 2 字节缓冲，约 400ms 刷新）；`PRG_Axis_Control` 透传 → GVL `AxisFb_rTorqueM1/M2`、`AxisFb_rCurrentM1/M2`、`AxisFb_xParamErr`。
- 站号：新增 RETAIN `Cfg_wSdoDevM1/M2`（默认 1001/1002）= `MDX_EC` / `MDX_EC_1` 的 EtherCAT 物理地址，**必须与 InoProShop 设备树 Address 一致**（地址不在导出 XML 里，无法自动取）。
- 镜像：状态 word49..52 = M1/M2 转矩/电流（`SCALED_INT ×1000`，线上值=千分比额定，网关解码 1.0=100%），word53 bit0 = 读取错误。
- 链路：`config/modbus-map.json`（status 字段 49..53）+ `docs/plc/MODBUS_MAP.md`（已重生成）+ WebHMI「X 双驱」页显示；`gateway/lib/mock-plc.js` 已补。
- 构建：`tools/patch_g071.py`（0.70 → `LMM_g_0.71.xml`，幂等，sha256 `46636e79…`）；校验：XML parse OK、`inject_g --check` OK、`check_plcopen_xml.py` OK、`npm test` 44 PASS。
- **烧录步骤**：InoProShop 导入 `LMM_g_0.71.xml` → 编译（若报 `ETC_CO_SdoRead` 未定义则加 `EtherCATStack` 库；若参数名不符按提示对齐，如 `bySubindex/usiChannel`）→ 核对 `Cfg_wSdoDevM1/M2` 与设备树 Address 一致 → 下载。设备树/PDO 不动。
- 预期：WebHMI「X 双驱」页出现 M1/M2 转矩/电流（%，100%=额定）+ CoE 读取错误位；X+ / X− 时对比可判定均载。
- 注意：0x6077/0x6078 按 CiA402 为千分比额定（1000=100%）；若驱动手册单位不同，按比例修正编码前的系数。

## 0.72 交付：X 双驱驱动诊断全量回传（2026-09-12 晚，待烧录）

- 目的：查清"X− 空旷卡死、两台各 100%、手能推、M1 过流 0x2000"。把驱动内部状态拉进 WebHMI。
- PLC：`FB_XDual` 每台驱动轮询 **7 个 CoE 对象**（0x6077 转矩 / 0x6078 电流 / **0x6041 状态字** / **0x603F 错误码** / **0x6072 最大转矩** / **0x60E0 正向限** / **0x60E1 反向限**），14 时隙 ×100ms（一轮约 1.4s），各自独立缓冲。
- 镜像：状态 word49..52 转矩/电流（0.71 已有）；**word54..63** = M1/M2 状态字/错误码/最大转矩/正反限幅（原始 16 位）。
- 链路：map status 字段 54..63 + `MODBUS_MAP.md` 重生成 + WebHMI「X 双驱」新增「驱动诊断」卡（状态字/错误码十六进制，限幅 ÷10=%）+ mock。
- 构建：`tools/patch_g072.py`（0.71 → `LMM_g_0.72.xml`，幂等，sha256 `1ccc6206…`）；校验：XML parse OK、`inject_g --check` OK、`check_plcopen_xml.py` OK、`npm test` 44 PASS。
- **烧录**：导入 `LMM_g_0.72.xml` → 编译下载（库/参数名同 0.71 说明）。WebHMI 硬刷新。
- 判读：卡住时 M1 `0x6041` bit3=1 → 驱动已 Fault（输出撤了）→"先故障后停"；`0x6072/0x60E0/0x60E1` 若 ~1000(100%) → 限幅没余量；`0x603F` 显示具体错误码（M1 实测 0x2000 = 电流类）。
- 现场已排除：一体机无 UVW 接线、抱闸已松、增益已标定、单驱因刚性走不动、不在行程头。

## 0.73 交付：MDX 模式 + 转矩限值回传（2026-09-12 晚，待烧录）

- 目的：0.72 显示"驱动使能中(0x1237)、无故障、无内部限幅，却只给 ~100% 顶不动"，需确认运行模式与 MDX 特有转矩限值。
- PLC：`FB_XDual` 每台驱动轮询 **12 个对象** = 0.72 的 7 个 + **0x6060 模式** + **0x2403/0x2404/0x2405/0x2406（MDX 转矩限值）**；24 时隙 ×100ms（一轮约 2.4s）。
- 镜像：状态 **word64..73** = M1/M2 的 0x6060 与 0x2403~0x2406（原始 16 位）。
- 链路：map 字段 64..73 + MODBUS_MAP 重生成 + WebHMI「驱动诊断」卡加 M1/M2 模式与限值 + mock。
- 构建：`tools/patch_g073.py`（0.72 → `LMM_g_0.73.xml`，幂等，sha256 `9441523d…`）；XML parse OK、`inject_g --check` OK、`check_plcopen_xml.py` OK、`npm test` 44 PASS。
- 另修：WebHMI「CoE 读取错误」标签写死的 bug（录波证明 paramErr 全程 0）→ 改为按 `AxisFb_xParamErr` 动态显示 正常/错误。
- **0.72 记录的在役事实**：0x6077 单位 0.1%（1000=100%）；卡住全程 M1/M2 状态字 `0x1237`（使能中、无 Fault、无内部限幅）；限幅 M1 300/400/400%、M2 300/300/300%；`0x603F` 抓到 `0xFF34`。
- 现场已排除：一体机无 UVW、抱闸已松、增益已标定、单驱因刚性走不动、不在行程头。

## 0.74 交付：X 双驱强制 CSV 速度模式（2026-09-12 晚，待烧录）

- 根因线索：设备树 `0x6060=9`，但**运行时读到 8（CSP）**；现场又出现"跟随误差"（CSP 才有的概念）。SM3 DS402 接口默认按 `SMC_position` 给了 CSP。
- 修复：`FB_XDual` 第 11 节在**空闲且使能**时调 `SMC_SetControllerMode(Axis, SMC_velocity)` 把 M1/M2 切到 CSV（`SMC_velocity=2`）；Done/Error 都置 done 防反复；`bError` 经 `xModeCsvErrM*` 暴露。
- 配置：GVL RETAIN `Cfg_xForceCsvX`（默认 TRUE，可关）。
- 镜像：状态 **word74** bit0 M1done / bit1 M1err / bit2 M2done / bit3 M2err。
- 链路：map 字段 + MODBUS_MAP 重生成 + WebHMI「驱动诊断」加"已切CSV/失败" + mock。
- 构建：`tools/patch_g074.py`（0.73 → `LMM_g_0.74.xml`，幂等，sha256 `15b81b5d…`）；XML parse OK、`inject_g --check` OK、`check_plcopen_xml.py` OK、`npm test` 44 PASS。
- 风险/前提：`SMC_SetControllerMode` 需驱动支持 CSV 且速度 PDO(0x60FF) 已映射；若 `AxisFb_xModeCsvErrM*`=TRUE 则不支持，需在 InoProShop 改轴/PDO。若 `SMC_SetControllerMode` 未定义，编译会报，需改用 InoProShop 配置法。
- 验证：烧后看 `AxisFb_wModeM1/M2` 是否变 9、`AxisFb_xModeCsvM1/M2` 是否 done。

## 0.75 交付：启动直写 0x6060=9（2026-09-12 晚，待烧录）

- 现象：烧 0.74 后 CoE `0x6060` 仍=8 → `SMC_SetControllerMode` 没被驱动接受（或被 SM3 回写）。
- 做法（按用户要求、最小化）：`FB_XDual` 第 12 节在**空闲且使能**时用 `ETC_CO_SdoWrite4` **直写 `0x6060=9`**，写一次；0.74 的 `SMC_SetControllerMode` 保留。
- 无 GVL / 镜像 / Web 变化；构建 `tools/patch_g075.py`（0.74→`LMM_g_0.75.xml`，幂等，sha256 `95696664…`）；XML parse / `check_plcopen_xml` / `inject_g --check` OK。
- 验证：烧后看 `AxisFb_wModeM1/wModeM2`（word64/69）是否=9。仍=8 则驱动/PDO 不支持 CSV（查 `0x6502`、RxPDO 是否含 `0x60FF`）。

## 0.76 交付：SMC_SetControllerMode 每秒脉冲切 CSV（2026-09-12 晚，待烧录）

- 现象：0.74 的切换条件窗口太窄（只切一次、出错即锁），运行时 0x6060 仍是 8。
- 做法：FB_XDual 第 11 节改为**空闲且使能时每秒给一次 bExecute 脉冲**调 `SMC_SetControllerMode(SMC_velocity)`；成功判据 = `bDone` 或 **0x6060 读回=9**。0.75 的直写 0x6060 保留兜底。
- 无 GVL / 镜像变化；`tools/patch_g076.py`（0.75→`LMM_g_0.76.xml`，幂等，sha256 `83f6a4d0…`）。
- 驱动能力已确认：`0x6502 = 66477 = 0x103AD` → bit7 csp、**bit8 csv 均支持**，CSV 可做。
- 验证：烧 0.76 后使能并停几秒，`AxisFb_wModeM1/wModeM2` 应变 9；`AxisFb_xModeCsvM1/M2`=TRUE，`ErrM1/M2`=FALSE。

## 0.77 交付：修 0.76 重触发 bug（保持 bExecute 到 Done）（2026-09-12 晚，待烧录）

- 现场：烧 0.76 后 `w74=0`、mode 仍 8。**根因**：`SMC_SetControllerMode` 切换最长约 1000 周期(~4s)，0.76 每秒脉冲会在**切完前重启** → 永远完不成。
- 修复：第 11 节改为**保持 bExecute 到 Done/Error**，空闲且使能时切一次。
- 无 GVL/镜像变化；`tools/patch_g077.py`（0.76→`LMM_g_0.77.xml`，幂等，sha256 `09845010…`）；XML parse / PLCopen / `inject_g --check` OK。
- 验证：烧 0.77 后使能并停 ~5s，`AxisFb_xModeCsvM1/M2`=TRUE（w74 bit0/bit2=1），`AxisFb_wModeM1/wModeM2`→9。

## 0.79 交付：CSV 根因定论 + 删除无效运行时切模式（2026-09-13，待烧录 + 设备树改 PDO）

- 现象（用户）：0.78 已"设置 M1/M2 速度模式"，在线 CoE 看 6060 仍是 8（位置模式）。
- **根因定论（两层）**：
  1. **设备树 PDO 是 CSP 集合**：M1/M2 轴选中 RxPDO1（`0x1600` = 6040+**6060**+**607A**+60B8+60FE）；目标速度 **0x60FF 未映射**（轴映射 `diSetVelocity` AdrOffset=`0xFFFFFFFF`）。`0x6060` 在 RxPDO 内，进 OP 后由驱动组件**每周期按映像中的设定值通道写 8**；启动参数/SDO 写的 9 只在上电瞬间生效，下一拍即被覆盖 → "设了速度模式但运行时还是位置模式"。
  2. **0.74~0.78 的运行时切换代码双重无效**：第 11 节 `SMC_SetControllerMode` 被注入脚本误嵌进 `IF fbSdoTq03M2.xDone THEN`（每 ~2.4s 只执行 1 个周期，bExecute 保持不住 ~4s → 永远切不完，w74 恒 0）；第 12 节 `ETC_CO_SdoWrite4` 直写 6060 必然被 PDO 下一拍覆盖。且即使切成功，60FF 未映射速度设定值也没有下发通道。
- **修复路径 = 设备树（唯一生效点）**：InoProShop 中 MDX_EC / MDX_EC_1 过程数据把 RxPDO 从 **RxPDO1(0x1600, CSP)** 改为 **RxPDO4(0x1603 = 6040+6060+60FF+60FE，CSV)**（或 RxPDO2/0x1601，多 60B8）；改后轴映射自动获得 set velocity 通道，组件使能时自行写 6060=9。FB_XDual 只用 MC_MoveVelocity/Halt/Stop/SetPosition（无定位 FB），切 CSV 不破坏功能。
- **PLC（0.79）**：删除 0.74~0.77 的运行时切 CSV 死代码（`SMC_SetControllerMode`/`ETC_CO_SdoWrite4`/`xForceCsv` 入参）；`xModeCsvM1/M2` 改为 **6060 实测=9 只读诊断**；word74 bit0/bit2=6060=9（Err 位取消）。GVL `Cfg_xForceCsvX` 保留不用（无害）。
- 构建：`tools/inject_g.py LMM_g_0.78.xml LMM_g_0.79.xml`（sha256 `434b934b…`）；校验：XML parse OK、`inject_g --check` OK、`check_plcopen_xml.py` OK；0.79 与 0.78 差异仅 FB_XDual/PRG_Axis_Control/PRG_Logic/PRG_TcpHmi 的上述清理，无现场手改被覆盖。
- 烧录/验证：InoProShop 导入 0.79 → 改 MDX_EC/MDX_EC_1 的 RxPDO 选择 → 编译下载 → 使能后 WebHMI 驱动诊断 `AxisFb_wModeM1/M2`（word64/69）=9、word74 bit0/bit2=1；在线 CoE 6060=9。

## Locked decisions
- Modbus 角色维持 **Gateway 主站 / PLC 从站**（现场 Modbus client 连 `:502` 验证）
- Web 急停仍为**请求**；物理急停 AND 仲裁不变（非安全等级）
- 速度透传先 Web、后 PLC 0.63；命令区与浏览器 WS/JSON 契约不变
- `Axis_Control` 独立任务、仅 GVL 交换，未改动

## Paths
- `web/live/index.html`, `gateway/`, `config/modbus-map.json`, `docs/plc/MODBUS_MAP.md`, `LMM_g_0.63.xml`, `tools/patch_g063.py`
