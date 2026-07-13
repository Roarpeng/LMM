# Web v2 ↔ MD checklist

- [x] Module list matches S4（GVL / FB_Servo / FB_XDiff / Axis_Control / PRG_Logic / HMI / PLC_PRG）
- [x] Step chart matches Logic/process MD（本期无自动步；Manual only — N/A）
- [x] Interlocks match MD（Y±/Z± 限位、Fault、Z 动禁 Y；见 PRG_Logic.md）
- [x] HMI request bits labeled as in GVL/HMI MD（EStop 极性、Stop 点按/长按、eMode、eDiffFunc、JOG）
- [x] X 完整动作：Indep / Sync 同速⊥Y / Diff（纠偏·原地旋转一正一反·差速拐弯）+ 跨距 4~6
- [x] Alarm/Step IDs match S5（1001/1002/1003/1004/1099）
- [x] DIFF_FROM_V1.md filled
- [x] WEB_PLC_ALIGN.md 与 Web v2 / MD 公式一致
- [x] User confirmation: 「web2 理解是正确的了」— 2026-07-13；并要求与 PLC 功能对齐
