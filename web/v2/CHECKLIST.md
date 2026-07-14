# Web v2 ↔ MD checklist

- [x] Module list matches S4（GVL / FB_Servo / FB_XDiff / Axis_Control / PRG_Logic / HMI）
- [x] Step chart matches Logic MD：0 Idle → 1 MoveX → 2 PressZ → 3 MoveY+恒力 → 4 RWobble占位 → 5 Done
- [x] Interlocks match MD（Y/Z 限位、Fault、急停；自动中禁手动 JOG）
- [x] HMI 请求位按 HMI.md：JogX / SpinL/R / JogYZR · AutoStart/Abort · ForceSim
- [x] 设备三态灯：Stop / Run / Error（HMI_xDev*）
- [x] Alarm IDs：1001 急停 · 1002 故障 · 1003 限位 · 1004 无许可
- [x] DIFF_FROM_V1.md filled
- [ ] User confirmation: 「Web v2 通过」— quote/date:
