# equipment-plc-workflow state

## Meta
- Project: LMM（XYZR 非标，鸣志 MDX EtherCAT + 汇川 SoftMotion）
- Entry mode: greenfield
- Updated: 2026-07-13

## Current
- Stage: S8
- Blocked by gate: none
- Next action: 用户导入 LMM.xml 编译联调；反馈编译错误则回写 MD/XML

## Notes
- LMM.xml FB_Servo 已按 SM3 修正：`xPowered := fbPower.Status`（无 Operational）
- 导入说明：docs/plc/IMPORT_LMM_XML.md

## Confirmations (evidence)
| Stage/Gate | Status | Evidence (user quote / file) | Date |
|------------|--------|------------------------------|------|
| S1 | pass | | 2026-07-13 |
| S2 | pass | 先手动 | 2026-07-13 |
| Gate A (Web v1) | pass | 「web v1 通过」 | 2026-07-13 |
| Gate B (S4 map) | pass | 「确认」+ Axis 独立进程 | 2026-07-13 |
| Gate C (S5 writers) | pass | 「确认」 | 2026-07-13 |
| S6 MD | pass | docs/plc/*.md | 2026-07-13 |
| Gate D (Web v2) | pass | 「web2 理解是正确的了」+ 要求与 PLC 对齐；WEB_PLC_ALIGN.md | 2026-07-13 |
| S8 | in_progress | 导入对齐后的 MD | 2026-07-13 |

## Paths
- Web v1: web/v1/index.html
- Web v2: web/v2/index.html
- MD root: docs/plc/
- Align: docs/plc/WEB_PLC_ALIGN.md
- PLC 源工程导出: LMM.xml

## Notes
- Web v2 = PLC 行为基准；导入按 WEB_PLC_ALIGN + GVL/Logic/Axis/XDiff
- X⊥Y；Diff 0/1/2；急停 FALSE 触发；Stop 长按 ResetFault
- Axis 独立任务；无自动；M5 预留
