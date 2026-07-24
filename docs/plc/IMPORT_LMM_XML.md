# LMM.xml 导入与联调（InoProShop / PLCopen TC6）

> PLC 侧改动一律走 `plc/` 工作流（见 `plc/README.md`）：
> 改 `.st` → `python3 tools/inject_st.py` → `python3 tools/check_lmm.py` → 导入本文件。
> 注入前自动备份 `LMM.xml.bak.inject`；更多历史备份在 `attic/bak/`。

## 工程内容

- POU（8 个）：`PLC_PRG` + `PRG_TcpHmi` / `PRG_Logic` / `PRG_Axis_Control` + `FB_Servo` / `FB_Force` / `FB_ForceFollow` / `FB_XLineTrack`
- GVL：唯一全局变量表（`plc/GVL.st` 注入）
- 任务：`ETHERCAT`(4ms, prio0)=EtherCAT_Task+PRG_Axis_Control；`MainTask`(4ms, prio1)=PLC_PRG

## 导入步骤

1. 改完 `.st` 跑 `inject_st.py` + `check_lmm.py`（0 error）
2. InoProShop 导入/覆盖 `LMM.xml`，编译
3. 若 `AXIS_REF_SM3` / `MC_*` 类型名与库版本不符，库管理器确认 **SM3_Basic**，按本机类型名微调 `FB_Servo.st` 再注入
4. 确认任务挂载（见上表，PLC_PRG 只在 MainTask）
5. 映射限位输入 `I_xLim*`（地址 TBD）；面板 IO 地址固定勿改（Start %IX1.6 / Stop %IX1.4 / EStop %IX0.4 正常=TRUE / StopLamp %QX0.6 / StartLamp %QX0.7）
6. 硬限位默认值在 GVL `Cfg_rLim*`，现场按机械行程改

## LE 拉压传感器（组态 Modbus RTU 主站，COM0）

程序侧只有 `FB_Force` 读组态映射变量；从站使能 `SM1001` 在组态里。

| 项 | 值 |
|----|-----|
| 电气 | DC12V；485+绿 / 485-白 |
| 串口 | COM0，115200 8N1 |
| 站号 | 1；使能 `SM1001`（失败重试 3 次 → 报警 1006） |
| 读力 | FC03 `0x0000` → `Force_wInRaw %IW102` |
| 去皮 | 写 `0x0011` → `Force_wOutTare %QW42` |
| 单位 | 写 `0x0002`=5(N) → `Force_wOutUnit %QW43` |

## 联调检查单

- [ ] 编译 0 错；两个任务挂载正确
- [ ] 面板 Jog 六向 + R 双向点动；Web 点动按住动松开停
- [ ] Y/Z/R 撞 Cfg 限位即停；改小限位后仍能向回点动
- [ ] 回零 Y/Z/R 完成置 0
- [ ] `Force_xCommOk=TRUE`；关模拟后 `HMI_rForceShow` 随压力变化
- [ ] `HMI_xForceGuide=TRUE` Z 跟力，FALSE 停
- [ ] 从站 3 次失败 → 报警 1006；力 2s 无变化 → 报警 1005
- [ ] Web：拔网线 ≤1s 远程动作清零；面板可接管（见 [TCP_HMI.md](TCP_HMI.md)）
