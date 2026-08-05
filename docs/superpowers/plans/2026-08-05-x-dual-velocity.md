# X Dual Velocity (0.26) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make X-axis M1/M2 both velocity-controlled (symmetric CSV-style SoftMotion path) so jog reverse and jog-release stop work reliably with vision heading trim.

**Architecture:** Single `FB_XDual` owns both axes. No `MC_Jog`. Shared `xVelRaw` gate, per-axis Execute, per-axis direction-flip re-trigger, Halt on release.

**Tech Stack:** IEC 61131-3 ST, Codesys SoftMotion (`MC_MoveVelocity` / `MC_Halt` / `MC_Power`), Python mirror logic in `tools/x_dual_logic.py`, inject via `tools/inject_g.py`.

---

### Task 1: Pure-logic tests for dual-velocity request

**Files:**
- Modify: `tools/x_dual_logic.py`
- Modify: `tools/test_x_dual_logic.py`

- [ ] **Step 1: Add `dual_vel_request` helper and tests for jog+/jog−/release**
- [ ] **Step 2: Run tests — expect pass for new helpers**

### Task 2: Rewrite `FB_XDual` motion path

**Files:**
- Modify: `plc/g/FB_XDual.st`

- [ ] **Step 1: Remove `fbJogM1`; drive M1 with `fbVelM1` using `rVelCmdM1`**
- [ ] **Step 2: Mirror M2 request/stop/dir-flip onto M1**
- [ ] **Step 3: Keep vision trim + light sync trim with same-sign clamp**

### Task 3: Inject and verify

**Files:**
- Create: `LMM_g_0.26.xml`

- [ ] **Step 1: `python tools/inject_g.py LMM_g_0.25.xml LMM_g_0.26.xml`**
- [ ] **Step 2: Confirm body has no `MC_Jog`, has `xDirFlipM1/M2`**
- [ ] **Step 3: Run `python -B -m unittest tools.test_x_dual_logic -v`**
