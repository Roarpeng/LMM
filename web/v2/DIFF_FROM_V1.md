# DIFF_FROM_V1

| Item | v1 | v2 | Reason |
|------|----|----|--------|
| 控制完整度 | 示意验收 | **设备操作台**：安全三态 + 手动 + 自动恒力 | S7 ↔ 现行 MD |
| X 操作 | Indep/Sync/Diff 菜单 | **X± Sync + 左/右旋转** | HMI 简化 |
| 自动 | 无 / 禁用 | **iAutoStep 0–5**（力模拟） | PRG_Logic.md |
| 力 | 无 | F_set + ForceSim + 恒力示意条 | GVL/HMI |
| R | 禁用 | xM5Ready 门控下可 JOG | 接口就绪 |
| 模式 | 仅手动提示 | HMI_xAutoMode 手动/自动切换 | HMI.md |
| 复位 | 长按 Stop | Stop 长按 + **ResetBtn** | 面板绑定 |
