# DIFF_FROM_V1

| Item | v1/旧 v2 | 现行 v2 | Reason |
|------|----------|---------|--------|
| X 速度 | VelX 兼旋转 | **VelX + SpinVel** | 用户要求分开 |
| Y 行程 | AutoDistY | **`HMI_rWheelBase` 跨距=Y行程** | 同一机械量 |
| X 模式 | Indep/Sync/Diff 菜单 | 仅 JogX + Spin | 精简 |
| 旧符号 | Sync/Diff/M1/M2/Home/Δ/ω | **删除** | 易混淆 |
