# equipment-plc-workflow state

## Meta
- Project: LMM（XYZR 非标，鸣志 MDX EtherCAT + 汇川 SoftMotion）
- Entry mode: change-request
- Updated: 2026-07-14

## Current
- Stage: S8（契约变更后需导入/联调）
- Blocked by gate: none（逻辑变更，建议对照 Web v2）
- Next action: 导入更新后的使能/JOG/HMI 契约；触摸屏按 docs/plc/HMI.md 绑变量

## Change-request（2026-07-14）
用户反馈：
1. 复位后轴无法使能 — 无使能触发接口 → 新增 `HMI_xEnable`，Logic 上升沿切换 `xPowerLatched`
2. JOG = 点动电平 TRUE 移动 / FALSE 暂停
3. 提供触摸屏 HMI 接口表 → `docs/plc/HMI.md`

## Confirmations (evidence)
| Stage/Gate | Status | Evidence (user quote / file) | Date |
|------------|--------|------------------------------|------|
| S1 | pass | | 2026-07-13 |
| S2 | pass | 先手动 | 2026-07-13 |
| Gate A (Web v1) | pass | 「web v1 通过」 | 2026-07-13 |
| Gate B (S4 map) | pass | 「确认」+ Axis 独立进程 | 2026-07-13 |
| Gate C (S5 writers) | pass | 「确认」 | 2026-07-13 |
| S6 MD | pass | docs/plc/*.md（已按 CR 更新） | 2026-07-14 |
| Gate D (Web v2) | pass | 先前通过；本次 CR 微调 Enable | 2026-07-14 |
| S8 | in_progress | 使能触发 + HMI 表 | 2026-07-14 |

## Paths
- Web v1: web/v1/index.html
- Web v2: web/v2/index.html
- MD root: docs/plc/
- Align: docs/plc/WEB_PLC_ALIGN.md
- HMI 触摸屏: docs/plc/HMI.md
- PLC 源工程导出: LMM.xml

## Notes
- 复位/急停/故障后必须再按使能；点按停止只停运动不清使能闩
- JOG 松手=暂停，不断总使能
- Axis 独立任务；无自动；M5 预留
