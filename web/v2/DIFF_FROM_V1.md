# DIFF_FROM_V1

| Item | v1 | v2 | Reason |
|------|----|----|--------|
| 控制完整度 | 示意验收 | **完整手动控制台**（参数/模式/按住JOG/速度·位置反馈/动画） | 用户要求 |
| 架构 | 布局示意 | Axis 独立任务 + GVL 仅 IO | S4/S6 |
| X | sync/diff/indep | Indep / Sync同速 / Diff(纠偏·原地旋转一正一反·差速拐弯) + 跨距4~6 | 用户纠正 |
| 急停 | 点击锁存 | 按住=FALSE / 松开=TRUE，锁存保持 | HMI.md |
| Stop | 长按复位 | 点按停 + 长按3s ResetFault | HMI.md |
| 自动 | Step=0 禁用 | 无自动 | S2 |
| M5 | 预留节点 | R 禁用 | S5 |
