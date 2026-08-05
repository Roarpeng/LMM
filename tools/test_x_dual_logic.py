# tools/test_x_dual_logic.py
import unittest
from tools.x_dual_logic import (
    select_mode, base_vel, move_done_update, MoveState,
    hold_state, sync_trim_active, sync_err_linear, m1_vel_execute, m1_track_execute,
    m1_regulator_on, suppress_fault, m2_dir_flip, m2_vel_same_sign,
    m2_vel_request, m2_need_halt, dual_vel_request, softhold_exit_should_reset,
    dual_sync_velocities, clamp_sync_corr, soft_acc, slew_velocity, sync_scale_at_speed,
)

class XDualLogicTests(unittest.TestCase):
    def test_spin_beats_jog(self):
        self.assertEqual(select_mode(True, False, True, False, False, False, True), 2)

    def test_jog_pos_mode1(self):
        self.assertEqual(select_mode(True, False, False, False, False, False, True), 1)
        self.assertEqual(base_vel(1, True, False, 0.4, False, 1.0, 0.5), 0.4)

    def test_move_rel_base_vel_sign(self):
        self.assertEqual(base_vel(1, False, False, 0.4, True, -2.0, 0.5), -0.5)

    def test_move_done_average_relative(self):
        st = MoveState()
        done, st = move_done_update(st, move_rel=True, stop=False, enable=True,
                                    pos_m1=0.0, pos_m2=0.0, move_dist=1.0)
        self.assertFalse(done)
        done, st = move_done_update(st, move_rel=True, stop=False, enable=True,
                                    pos_m1=1.0, pos_m2=1.0, move_dist=1.0)
        self.assertTrue(done)

    def test_stop_clears_done(self):
        st = MoveState(armed=True, start=0.0)
        done, st = move_done_update(st, move_rel=True, stop=True, enable=True,
                                    pos_m1=2.0, pos_m2=2.0, move_dist=1.0)
        self.assertFalse(done)
        self.assertFalse(st.armed)

    def test_hold_run_when_moving(self):
        st, latched = hold_state(e_mode=1, x_stop=False, x_enable=True,
                                 ton_still_m1=False, ton_still_m2=False, latched=False)
        self.assertEqual(st, 0)
        self.assertFalse(latched)

    def test_hold_decel_before_still(self):
        st, latched = hold_state(e_mode=0, x_stop=False, x_enable=True,
                                 ton_still_m1=False, ton_still_m2=True, latched=False)
        self.assertEqual(st, 1)
        self.assertFalse(latched)

    def test_hold_softhold_when_both_still(self):
        st, latched = hold_state(e_mode=0, x_stop=False, x_enable=True,
                                 ton_still_m1=True, ton_still_m2=True, latched=False)
        self.assertEqual(st, 2)
        self.assertTrue(latched)

    def test_hold_latched_ignores_noise(self):
        st, latched = hold_state(e_mode=0, x_stop=False, x_enable=True,
                                 ton_still_m1=False, ton_still_m2=False, latched=True)
        self.assertEqual(st, 2)
        self.assertTrue(latched)

    def test_hold_fallback_enters_under_oscillation(self):
        # 0.20：极限环摆动使静止条件永不满足，低速兜底 2s 强制进入
        st, latched = hold_state(e_mode=0, x_stop=False, x_enable=True,
                                 ton_still_m1=False, ton_still_m2=False,
                                 latched=False, ton_fallback=True)
        self.assertEqual(st, 2)
        self.assertTrue(latched)

    def test_hold_fallback_blocked_by_stop(self):
        st, latched = hold_state(e_mode=0, x_stop=True, x_enable=True,
                                 ton_still_m1=False, ton_still_m2=False,
                                 latched=False, ton_fallback=True)
        self.assertEqual(st, 0)
        self.assertFalse(latched)

    def test_hold_fallback_blocked_when_moving_mode(self):
        st, latched = hold_state(e_mode=1, x_stop=False, x_enable=True,
                                 ton_still_m1=False, ton_still_m2=False,
                                 latched=False, ton_fallback=True)
        self.assertEqual(st, 0)
        self.assertFalse(latched)

    def test_hold_no_softhold_on_estop(self):
        st, latched = hold_state(e_mode=0, x_stop=True, x_enable=True,
                                 ton_still_m1=True, ton_still_m2=True, latched=True)
        self.assertEqual(st, 0)
        self.assertFalse(latched)

    def test_sync_trim_gate(self):
        self.assertTrue(sync_trim_active(e_mode=1, x_sync_enable=True))
        self.assertFalse(sync_trim_active(e_mode=1, x_sync_enable=False))
        self.assertFalse(sync_trim_active(e_mode=0, x_sync_enable=True))

    def test_sync_trim_active_during_jog(self):
        # 0.23：Jog（MoveRel=False）也要 trim，否则线轴直行拧架摇摆
        self.assertTrue(sync_trim_active(e_mode=1, x_sync_enable=True, move_rel=False))
        self.assertTrue(sync_trim_active(e_mode=1, x_sync_enable=True, move_rel=True))

    def test_sync_err_linear_no_rotary_wrap(self):
        # 线轴：差分 >180 不得折到负值（旧旋转轴 ±180 语义）
        self.assertEqual(sync_err_linear(200.0, 0.0), 200.0)
        self.assertEqual(sync_err_linear(0.0, 200.0), -200.0)
        self.assertAlmostEqual(sync_err_linear(1.25, 1.0), 0.25)

    def test_m1_vel_execute_softhold_releases_vel(self):
        self.assertFalse(m1_vel_execute(motion_req=False, soft_hold=True, vel_abs=0.0, vel_error=False))
        self.assertFalse(m1_vel_execute(motion_req=True, soft_hold=False, vel_abs=0.0, vel_error=False))
        self.assertTrue(m1_vel_execute(motion_req=True, soft_hold=False, vel_abs=0.5, vel_error=False))
        self.assertFalse(m1_vel_execute(motion_req=True, soft_hold=False, vel_abs=0.5, vel_error=True))

    def test_m1_track_execute_disabled(self):
        self.assertFalse(m1_track_execute(soft_hold=True, tick=1))
        self.assertFalse(m1_track_execute(soft_hold=True, tick=2))

    def test_m1_regulator_stays_on_in_softhold(self):
        # 0.23：SoftHold 不得松调节器（线轴松手「丢使能」根因）
        self.assertTrue(m1_regulator_on(soft_hold=True, x_enable=True, x_stop=False))
        self.assertTrue(m1_regulator_on(soft_hold=False, x_enable=True, x_stop=False))
        self.assertFalse(m1_regulator_on(soft_hold=False, x_enable=False, x_stop=False))
        self.assertFalse(m1_regulator_on(soft_hold=True, x_enable=True, x_stop=True))

    def test_suppress_fault_in_softhold(self):
        self.assertFalse(suppress_fault(soft_hold=True, axis_error=True))
        self.assertTrue(suppress_fault(soft_hold=False, axis_error=True))
        self.assertFalse(suppress_fault(soft_hold=False, axis_error=False))

    def test_suppress_fault_in_decel(self):
        # 0.23：Jog 释放后 Decel 窗口也抑 Fault，避免 StopAll 掉使能
        self.assertFalse(suppress_fault(soft_hold=False, axis_error=True, i_hold_state=1))
        self.assertTrue(suppress_fault(soft_hold=False, axis_error=True, i_hold_state=0))

    def test_m2_dir_flip_on_sign_change(self):
        # JogPos(+)->JogNeg(-) 且 Execute 仍保持：必须撤 Execute 一拍
        self.assertTrue(m2_dir_flip(req_vel=True, vel_run_prev=True,
                                    vel_cmd=-0.4, vel_cmd_prev=0.0))
        self.assertTrue(m2_dir_flip(req_vel=True, vel_run_prev=True,
                                    vel_cmd=-0.4, vel_cmd_prev=0.4))
        self.assertFalse(m2_dir_flip(req_vel=True, vel_run_prev=False,
                                     vel_cmd=-0.4, vel_cmd_prev=0.4))
        self.assertFalse(m2_dir_flip(req_vel=True, vel_run_prev=True,
                                     vel_cmd=0.4, vel_cmd_prev=0.3))

    def test_m2_vel_same_sign_blocks_trim_invert(self):
        # trim=+2 不得把 JogNeg 的 M2 拧成正向
        self.assertEqual(m2_vel_same_sign(-0.4, -0.4 + 2.0), 0.0)
        self.assertEqual(m2_vel_same_sign(0.4, 0.4 - 2.0), 0.0)
        self.assertAlmostEqual(m2_vel_same_sign(-0.4, -0.4 + 0.1), -0.3)
        self.assertAlmostEqual(m2_vel_same_sign(0.4, 0.4 + 0.1), 0.5)

    def test_m2_vel_request_drops_on_jog_release(self):
        # 松手 cmd=0：必须立刻撤 Execute（不能零速保持）
        self.assertFalse(m2_vel_request(raw=False, vel_cmd=0.0, req_prev=True))
        self.assertFalse(m2_vel_request(raw=True, vel_cmd=0.0, req_prev=True))
        self.assertTrue(m2_vel_request(raw=True, vel_cmd=-0.4, req_prev=False))
        self.assertFalse(m2_vel_request(raw=True, vel_cmd=0.4, req_prev=True, vel_error=True))

    def test_m2_need_halt_not_blocked_by_decel(self):
        self.assertTrue(m2_need_halt(power_gate=True, soft_hold=False, stop=False, req_vel=False))
        self.assertFalse(m2_need_halt(power_gate=True, soft_hold=False, stop=False, req_vel=True))
        self.assertFalse(m2_need_halt(power_gate=True, soft_hold=True, stop=False, req_vel=False))

    def test_dual_vel_request_symmetric(self):
        # 0.26/0.27：Jog± 都走 MoveVelocity；松手 eMode=0 立刻撤
        self.assertTrue(dual_vel_request(e_mode=1, soft_hold=False, soft_hold_exit=False,
                                         power_gate=True, vel_cmd=0.4))
        self.assertTrue(dual_vel_request(e_mode=1, soft_hold=False, soft_hold_exit=False,
                                         power_gate=True, vel_cmd=-0.4))
        self.assertFalse(dual_vel_request(e_mode=0, soft_hold=False, soft_hold_exit=False,
                                          power_gate=True, vel_cmd=0.0))

    def test_dual_vel_request_not_blocked_by_softhold_exit(self):
        # 0.27：SoftHold 退出沿不得挡启动（否则第二次 Jog 卡死）
        self.assertTrue(dual_vel_request(e_mode=1, soft_hold=False, soft_hold_exit=True,
                                         power_gate=True, vel_cmd=0.4))
        self.assertFalse(dual_vel_request(e_mode=1, soft_hold=True, soft_hold_exit=False,
                                          power_gate=True, vel_cmd=0.4))
        self.assertFalse(softhold_exit_should_reset())

    def test_dual_sync_symmetric_no_pull(self):
        # M1 超前 → M1 略慢、M2 略快；平均仍≈base
        v1, v2 = dual_sync_velocities(0.4, 0.0, 0.1)
        self.assertAlmostEqual(v1, 0.35)
        self.assertAlmostEqual(v2, 0.45)
        self.assertAlmostEqual(0.5 * (v1 + v2), 0.4)
        # 视觉 trim：与旧 M2=M1-2*trim 差速等价
        v1, v2 = dual_sync_velocities(0.4, 0.05, 0.0)
        self.assertAlmostEqual(v1 - v2, 0.1)

    def test_clamp_sync_corr_light(self):
        self.assertEqual(clamp_sync_corr(0.01, r_base=0.4), 0.0)  # deadband
        self.assertAlmostEqual(clamp_sync_corr(0.2, kp=0.1, r_base=0.4), 0.02)
        # 不超过 40% base
        self.assertAlmostEqual(clamp_sync_corr(10.0, kp=1.0, trim_max=1.0, r_base=0.4), 0.16)

    def test_soft_acc_clamps_hmi_100(self):
        # 0.31：不再上限钳位，HMI Acc 原样生效（仅保底）
        self.assertEqual(soft_acc(100.0), 100.0)
        self.assertEqual(soft_acc(0.1), 0.8)
        self.assertEqual(soft_acc(2.0), 2.0)
        self.assertEqual(soft_acc(100.0, hi=4.0), 4.0)  # 显式传 hi 才钳

    def test_slew_velocity_soft_step(self):
        self.assertAlmostEqual(slew_velocity(0.0, 0.4, 0.016), 0.016)
        self.assertAlmostEqual(slew_velocity(0.39, 0.4, 0.016), 0.4)
        self.assertAlmostEqual(slew_velocity(0.4, -0.4, 0.016), 0.384)

    def test_sync_scale_ramps_in(self):
        self.assertEqual(sync_scale_at_speed(r_base=0.4, r_vel_act_m1=0.0, r_vel_act_m2=0.0), 0.0)
        self.assertEqual(sync_scale_at_speed(r_base=0.4, r_vel_act_m1=0.3, r_vel_act_m2=0.3), 1.0)
        self.assertAlmostEqual(sync_scale_at_speed(r_base=0.4, r_vel_act_m1=0.14, r_vel_act_m2=0.28), 0.5)

if __name__ == "__main__":
    unittest.main()
