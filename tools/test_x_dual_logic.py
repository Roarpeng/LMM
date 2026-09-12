# tools/test_x_dual_logic.py
import unittest
from tools.x_dual_logic import (
    select_mode, base_vel, move_done_update, MoveState,
    hold_state, sync_trim_active, sync_err_linear, m1_vel_execute, m1_track_execute,
    m1_regulator_on, suppress_fault, m2_dir_flip, m2_vel_same_sign,
    m2_vel_request, m2_need_halt, dual_vel_request, softhold_exit_should_reset,
    dual_sync_velocities, hybrid_follow_velocities,     vision_dual_velocities,
    encoder_sync_gain, clamp_sync_corr, soft_acc, slew_velocity, sm3_track_acc,
    slew_start_nonzero, vel_latch_on_exec, jog_hold, exec_hold, sync_scale_at_speed,
    distance_from_avg, applied_base_velocity, vel_request_no_coast,
    vel_execute, gantry_drop_retry, heading_trim, x_reg_on,
    sync_expect_step, sync_residual, friction_pos_corr, vision_friction_velocities,
    trim_lpf, apply_axis_ratio, need_halt_level,
    x_power_fb_enable, x_power_settled, vel_fb_hold, can_drop_regulator, stop_fallback,
    trim_start_locked, corr_limit_for_base, floor_cmd_vs_base,
    dual_jog_vel_request, one_shot_trim_retrigger, vision_retrigger_ok,
    ramp_lock_fb_vel, vel_error_holdoff,
    eff_ramp_acc, trim_retrigger_pulse, trim_want, moverel_decel_dist,
    moverel_decel_trigger, req_vel_ramp, exec_hold_059, halt_level_ramp,
    direct_velocities, direct_halt_demand,
)

class XDualLogicTests(unittest.TestCase):
    def test_spin_beats_jog(self):
        self.assertEqual(select_mode(True, False, True, False, False, False, True), 2)

    def test_jog_pos_mode1(self):
        self.assertEqual(select_mode(True, False, False, False, False, False, True), 1)
        self.assertEqual(base_vel(1, True, False, 0.4, False, 1.0, 0.5), 0.4)

    def test_direct_mode_beats_jog(self):
        self.assertEqual(select_mode(True, False, False, False, False, False, True, direct=True), 4)

    def test_direct_velocities_passthrough(self):
        self.assertEqual(direct_velocities(-0.4, -0.385), (-0.4, -0.385))

    def test_direct_zero_side_halts(self):
        self.assertTrue(direct_halt_demand(
            e_mode=4, req_m1=True, req_m2=False, moving_m1=False, moving_m2=True))
        self.assertFalse(direct_halt_demand(
            e_mode=1, req_m1=True, req_m2=False, moving_m1=False, moving_m2=True))

    def test_exec_hold_direct_release(self):
        self.assertFalse(exec_hold_059(e_mode=4, req=False, decel_active=False, hold_prev=True))
        self.assertTrue(exec_hold_059(e_mode=4, req=True, decel_active=False, hold_prev=False))

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
        self.assertFalse(m1_regulator_on(x_enable=False, x_stop=False, e_mode=1, moving=False))
        self.assertFalse(m1_regulator_on(x_enable=True, x_stop=True, e_mode=1, moving=False))

    def test_regulator_drops_when_jog_idle(self):
        # 空闲卸调节器；置零不得钉死。松手短窗 stopping 仍保持，好刹完再卸。
        self.assertFalse(m1_regulator_on(x_enable=True, x_stop=False, e_mode=0, moving=False))
        self.assertFalse(m1_regulator_on(x_enable=True, x_stop=False, e_mode=0, moving=True))
        self.assertFalse(x_reg_on(enable=True, stop=False, e_mode=0, pos_zeroed=False, set_pos_req=True))
        self.assertTrue(m1_regulator_on(x_enable=True, x_stop=False, e_mode=0, stopping=True))
        self.assertTrue(m1_regulator_on(x_enable=True, x_stop=False, e_mode=1, moving=False))
        self.assertTrue(m1_regulator_on(x_enable=True, x_stop=False, e_mode=2, moving=False))
        # Power FB 在调节器已关时仍要 Enable，否则驱动收不到卸使能
        self.assertTrue(x_power_fb_enable(enable=True))
        self.assertTrue(x_power_fb_enable(enable=False))
        self.assertFalse(can_drop_regulator(standstill_m1=False, standstill_m2=True))
        self.assertFalse(can_drop_regulator(standstill_m1=True, standstill_m2=False))
        self.assertTrue(can_drop_regulator(standstill_m1=True, standstill_m2=True))
        self.assertTrue(stop_fallback(stopping=True, timeout=True, standstill_m1=False, standstill_m2=True))
        self.assertFalse(stop_fallback(stopping=True, timeout=True, standstill_m1=True, standstill_m2=True))
        self.assertFalse(stop_fallback(stopping=True, timeout=False, standstill_m1=False, standstill_m2=False))

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
        # 保留旧对称公式对照；0.32 不再用于直行
        v1, v2 = dual_sync_velocities(0.4, 0.0, 0.1)
        self.assertAlmostEqual(v1, 0.35)
        self.assertAlmostEqual(v2, 0.45)
        self.assertAlmostEqual(0.5 * (v1 + v2), 0.4)
        v1, v2 = dual_sync_velocities(0.4, 0.05, 0.0)
        self.assertAlmostEqual(v1 - v2, 0.1)

    def test_hybrid_follow_m1_unmoved(self):
        v1, v2 = hybrid_follow_velocities(0.4, 0.05, 0.1)
        self.assertAlmostEqual(v1, 0.4)
        self.assertAlmostEqual(v2, 0.4 - 0.1 + 0.1)

    def test_second_jog_not_blocked_by_stale_softhold(self):
        # 0.37：再按时 eMode 已是 1，不得被上一拍 SoftHold 挡住
        self.assertTrue(vel_request_no_coast(
            e_mode=1, soft_hold=True, power_gate=True, vel_cmd=0.4))

    def test_jog_start_grace_hides_stale_error(self):
        # 松手 SoftHold 残留 bError 不得在再按时变成 Fault→StopAll
        self.assertFalse(suppress_fault(
            soft_hold=False, axis_error=True, i_hold_state=0, jog_grace_done=False))
        self.assertTrue(suppress_fault(
            soft_hold=False, axis_error=True, i_hold_state=0, jog_grace_done=True))

    def test_vel_error_drops_execute_to_retrigger(self):
        # 起步失败才撤 Execute；已经 Busy 时撤一侧会把龙门拧成一快一慢
        self.assertFalse(vel_execute(req=True, dir_flip=False, vel_error=True, busy=False))
        self.assertTrue(vel_execute(req=True, dir_flip=False, vel_error=True, busy=True))
        self.assertTrue(vel_execute(req=True, dir_flip=False, vel_error=False))
        self.assertFalse(vel_execute(req=True, dir_flip=True, vel_error=False))

    def test_gantry_error_drops_both_until_paired(self):
        self.assertTrue(gantry_drop_retry(err_m1=True, err_m2=False, busy_m1=False, busy_m2=True))
        self.assertFalse(gantry_drop_retry(err_m1=True, err_m2=False, busy_m1=True, busy_m2=True))
        self.assertFalse(gantry_drop_retry(err_m1=False, err_m2=False, busy_m1=False, busy_m2=False))

    def test_sync_captures_start_and_ignores_old_offset(self):
        # 本段开始把当前 ΔPos 当作期望，不把历史安装差一次拧平
        exp = sync_expect_step(expect=0.0, trim=0.0, dt=0.004, capture=True, pos_diff=0.03)
        self.assertAlmostEqual(exp, 0.03)
        self.assertAlmostEqual(sync_residual(1.03, 1.00, exp), 0.0)
        self.assertEqual(friction_pos_corr(0.0), 0.0)

    def test_sync_corrects_new_lag_when_vision_zero(self):
        # 航向 0：M1 落后新产生的 4cm，应加快 M1、减慢 M2
        exp = 0.0
        resid = sync_residual(0.96, 1.00, exp)
        corr = friction_pos_corr(resid, kp=0.3, deadband=0.01, trim_max=0.08)
        self.assertAlmostEqual(resid, -0.04)
        self.assertAlmostEqual(corr, -0.012)
        v1, v2 = vision_friction_velocities(0.4, 0.0, corr)
        self.assertGreater(v1, v2)
        self.assertAlmostEqual(0.5 * (v1 + v2), 0.4)

    def test_sync_does_not_fight_vision_expect(self):
        # 视觉差速造成的 ΔPos 被期望吃掉，残差为 0，不反拧
        exp = sync_expect_step(expect=0.0, trim=0.05, dt=0.004, capture=False, pos_diff=0.0)
        self.assertAlmostEqual(exp, 0.0004)
        self.assertAlmostEqual(sync_residual(0.0004, 0.0, exp), 0.0)
        self.assertEqual(friction_pos_corr(0.0), 0.0)

    def test_heading_zero_means_zero_trim(self):
        self.assertEqual(heading_trim(kp=0.1, heading=0.0, trim_max=0.08), 0.0)
        self.assertEqual(heading_trim(kp=0.1, heading=0.002, trim_max=0.08), 0.0)
        self.assertAlmostEqual(heading_trim(kp=0.1, heading=0.5, trim_max=0.08), 0.0497)

    def test_heading_deadband_is_subtractive(self):
        self.assertAlmostEqual(heading_trim(kp=0.1, heading=0.013, trim_max=0.08), 0.001)

    def test_trim_lpf_ramps_without_step(self):
        y = trim_lpf(0.0, 0.05, dt=0.004, tc=0.05)
        self.assertGreater(y, 0.0)
        self.assertLess(y, 0.05)
        self.assertAlmostEqual(trim_lpf(0.05, 0.05, dt=0.004, tc=0.0), 0.05)

    def test_axis_ratio_scales_command(self):
        self.assertAlmostEqual(apply_axis_ratio(0.4, 1.003), 0.4012)
        self.assertAlmostEqual(apply_axis_ratio(0.4, 0.0), 0.04)

    def test_halt_level_follows_release(self):
        # 松手短窗且还在动才 Halt；停稳必须撤，禁止 0.42 那种电平保位
        self.assertTrue(need_halt_level(
            power_gate=True, e_mode=0, moving=True, stop=False, stopping=True))
        self.assertFalse(need_halt_level(
            power_gate=True, e_mode=0, moving=False, stop=False, stopping=True))
        self.assertFalse(need_halt_level(power_gate=True, e_mode=1, moving=True, stop=False, stopping=False))
        self.assertFalse(need_halt_level(
            power_gate=True, e_mode=0, moving=True, stop=False, stopping=False))

    def test_vel_waits_for_power_status(self):
        self.assertFalse(vel_request_no_coast(
            e_mode=1, soft_hold=False, power_gate=True, vel_cmd=0.4, power_status=False))
        self.assertTrue(vel_request_no_coast(
            e_mode=1, soft_hold=False, power_gate=True, vel_cmd=0.4, power_status=True))
        self.assertFalse(vel_request_no_coast(
            e_mode=1, soft_hold=False, power_gate=True, vel_cmd=0.4,
            power_status=True, power_settled=False))
        self.assertFalse(x_power_settled(status=True, e_mode=1, reg_on=True, settled_ton=False, was_stopping=False))
        self.assertTrue(x_power_settled(status=True, e_mode=1, reg_on=True, settled_ton=True, was_stopping=False))
        self.assertFalse(x_power_settled(
            status=True, e_mode=1, reg_on=True, settled_ton=True, was_stopping=False, standstill=False))
        self.assertTrue(x_power_settled(
            status=True, e_mode=1, reg_on=True, settled_ton=True, was_stopping=False,
            standstill=False, ready_prev=True))
        self.assertTrue(x_power_settled(status=True, e_mode=1, reg_on=True, settled_ton=False, was_stopping=True))
        self.assertAlmostEqual(vel_fb_hold(0.30, 0.302), 0.30)
        self.assertAlmostEqual(vel_fb_hold(0.30, 0.31), 0.31)

    def test_jog_press_snaps_to_base(self):
        # 0.36：按下当拍就是目标速度，禁止 PLC 再爬 rVelAppl
        self.assertAlmostEqual(applied_base_velocity(e_mode=1, r_base=0.4), 0.4)
        self.assertAlmostEqual(applied_base_velocity(e_mode=1, r_base=-0.4), -0.4)

    def test_jog_release_snaps_to_zero_and_drops_request(self):
        # 松开当拍基速归零；即使上一拍还在 0.4，也不得靠 coast 保持 Execute
        self.assertEqual(applied_base_velocity(e_mode=0, r_base=0.0), 0.0)
        self.assertFalse(vel_request_no_coast(
            e_mode=0, soft_hold=False, power_gate=True, vel_cmd=0.0, vel_appl=0.4))
        self.assertTrue(vel_request_no_coast(
            e_mode=1, soft_hold=False, power_gate=True, vel_cmd=0.4, vel_appl=0.4))
        self.assertTrue(m2_need_halt(power_gate=True, soft_hold=False, stop=False, req_vel=False))

    def test_vision_dual_shared_base(self):
        # 共用基速：平均不变；视觉差速对称；编码器 corr 不得进速度
        v1, v2 = vision_dual_velocities(0.4, 0.05, 0.0)
        self.assertAlmostEqual(0.5 * (v1 + v2), 0.4)
        self.assertAlmostEqual(v1 - v2, 0.1)
        v1, v2 = vision_dual_velocities(0.2, 0.0, 0.08)
        self.assertAlmostEqual(v1, 0.2)
        self.assertAlmostEqual(v2, 0.2)

    def test_position_is_distance_only(self):
        self.assertAlmostEqual(distance_from_avg(1.2, 0.8, 0.0), 1.0)
        self.assertAlmostEqual(distance_from_avg(3.0, 3.0, 1.0), 2.0)

    def test_encoder_sync_yields_to_vision(self):
        self.assertEqual(encoder_sync_gain(heading_trim=0.0), 1.0)
        self.assertEqual(encoder_sync_gain(heading_trim=0.05), 0.25)

    def test_clamp_sync_corr_light(self):
        self.assertEqual(clamp_sync_corr(0.01, r_base=0.4), 0.0)  # deadband
        self.assertAlmostEqual(clamp_sync_corr(0.2, kp=0.1, r_base=0.4), 0.02)
        # 不超过 40% base
        self.assertAlmostEqual(clamp_sync_corr(10.0, kp=1.0, trim_max=1.0, r_base=0.4), 0.16)

    def test_soft_acc_clamps_hmi_100(self):
        self.assertEqual(soft_acc(100.0), 100.0)
        self.assertEqual(soft_acc(0.1), 0.1)
        self.assertEqual(soft_acc(0.01), 0.05)
        self.assertEqual(soft_acc(2.0), 2.0)
        self.assertEqual(soft_acc(100.0, hi=4.0), 4.0)

    def test_startup_trim_locked_until_gate(self):
        self.assertFalse(trim_start_locked(e_mode=1, gate_done=False))
        self.assertFalse(trim_start_locked(e_mode=1, gate_done=True))

    def test_trim_retrigger_is_one_shot(self):
        self.assertFalse(vision_retrigger_ok(
            at_speed=False, gap_ok=True, cmd_m1=0.22, exec_m1=0.2, cmd_m2=0.18, exec_m2=0.2))
        self.assertFalse(vision_retrigger_ok(
            at_speed=True, gap_ok=True, cmd_m1=0.22, exec_m1=0.2, cmd_m2=0.18, exec_m2=0.2))
        self.assertTrue(ramp_lock_fb_vel(
            e_mode=1, straight_edge=True, locked_prev=False,
            vel_act_m1=0.0, vel_act_m2=0.0, vel_appl=0.3))
        self.assertTrue(ramp_lock_fb_vel(
            e_mode=1, straight_edge=False, locked_prev=True,
            vel_act_m1=0.05, vel_act_m2=0.05, vel_appl=0.3))
        self.assertTrue(ramp_lock_fb_vel(
            e_mode=1, straight_edge=False, locked_prev=True,
            vel_act_m1=0.2, vel_act_m2=0.2, vel_appl=0.3))
        self.assertFalse(ramp_lock_fb_vel(
            e_mode=1, straight_edge=False, locked_prev=True,
            vel_act_m1=0.25, vel_act_m2=0.25, vel_appl=0.3))
        self.assertTrue(vel_error_holdoff(err=True, err_prev=False, holdoff_prev=False, holdoff_done=False))
        self.assertTrue(vel_error_holdoff(err=True, err_prev=True, holdoff_prev=True, holdoff_done=False))
        self.assertFalse(vel_error_holdoff(err=False, err_prev=True, holdoff_prev=True, holdoff_done=True))

    def test_corr_cannot_eat_small_jog_vel(self):
        self.assertAlmostEqual(corr_limit_for_base(0.4), 0.08)
        self.assertAlmostEqual(corr_limit_for_base(0.1), 0.025)
        self.assertAlmostEqual(corr_limit_for_base(0.05), 0.0125)

    def test_floor_prevents_one_wheel_stop(self):
        self.assertAlmostEqual(floor_cmd_vs_base(0.0, 0.2, 1.0), 0.1)
        self.assertAlmostEqual(floor_cmd_vs_base(0.18, 0.2, 1.0), 0.18)
        self.assertAlmostEqual(floor_cmd_vs_base(-0.01, -0.2, 1.0), -0.1)

    def test_dual_jog_execute_both_or_neither(self):
        self.assertTrue(dual_jog_vel_request(e_mode=1, power_settled=True, vel_appl=0.2))
        self.assertFalse(dual_jog_vel_request(e_mode=1, power_settled=False, vel_appl=0.2))
        self.assertFalse(dual_jog_vel_request(e_mode=0, power_settled=True, vel_appl=0.2))

    def test_slew_velocity_soft_step(self):
        self.assertAlmostEqual(slew_velocity(0.0, 0.4, 0.016), 0.016)
        self.assertAlmostEqual(slew_velocity(0.39, 0.4, 0.016), 0.4)
        self.assertAlmostEqual(slew_velocity(0.4, -0.4, 0.016), 0.384)
        self.assertEqual(sm3_track_acc(0.3), 10.0)
        self.assertEqual(sm3_track_acc(20.0), 20.0)
        self.assertAlmostEqual(slew_start_nonzero(0.0, 0.3, 0.0012), 0.0012)
        self.assertAlmostEqual(vel_latch_on_exec(
            exec_now=True, exec_prev=False, target=0.3, latched_prev=0.0), 0.3)
        self.assertAlmostEqual(vel_latch_on_exec(
            exec_now=True, exec_prev=True, target=0.31, latched_prev=0.3, in_vel=False), 0.3)
        self.assertAlmostEqual(vel_latch_on_exec(
            exec_now=True, exec_prev=True, target=0.32, latched_prev=0.3, in_vel=True), 0.32)
        self.assertTrue(jog_hold(raw=True, held_prev=False, off_done=False))
        self.assertTrue(jog_hold(raw=False, held_prev=True, off_done=False))
        self.assertFalse(jog_hold(raw=False, held_prev=True, off_done=True))
        self.assertTrue(exec_hold(e_mode=1, req=True, hold_prev=False))
        self.assertTrue(exec_hold(e_mode=1, req=False, hold_prev=True))
        self.assertFalse(exec_hold(e_mode=0, req=False, hold_prev=True))

    def test_sync_scale_ramps_in(self):
        self.assertEqual(sync_scale_at_speed(r_base=0.4, r_vel_act_m1=0.0, r_vel_act_m2=0.0), 0.0)
        self.assertEqual(sync_scale_at_speed(r_base=0.4, r_vel_act_m1=0.3, r_vel_act_m2=0.3), 1.0)
        self.assertAlmostEqual(sync_scale_at_speed(r_base=0.4, r_vel_act_m1=0.14, r_vel_act_m2=0.28), 0.5)

if __name__ == "__main__":
    unittest.main()

class Ramp059Tests(unittest.TestCase):
    # 0.59：单沿起步 + Halt 对称减速（0.58 每步重触发废除）
    def test_eff_ramp_acc_caps_hmi_25(self):
        self.assertEqual(eff_ramp_acc(25.0), 1.0)
        self.assertEqual(eff_ramp_acc(100.0), 1.0)

    def test_eff_ramp_acc_floor_and_passthrough(self):
        self.assertEqual(eff_ramp_acc(0.01), 0.05)
        self.assertEqual(eff_ramp_acc(0.8), 0.8)
        self.assertEqual(eff_ramp_acc(0.4), 0.4)

    def test_trim_want_gates(self):
        # 全条件齐 + 差值达标才 want
        base = dict(exec_hold=True, ramp_lock=False, in_vel_m1=True, in_vel_m2=True,
                    decel_active=False, stop=False,
                    vel_fb_m1=0.41, vel_fb_m2=0.4, latch_m1=0.4, latch_m2=0.4)
        self.assertTrue(trim_want(**base))
        self.assertFalse(trim_want(ramp_lock=True, **base))
        self.assertFalse(trim_want(in_vel_m2=False, **base))
        self.assertFalse(trim_want(decel_active=True, **base))
        # 无视觉/同步漂移：差值 < 0.004 → 永不触发 → 全程单沿
        base.update(vel_fb_m1=0.402, latch_m1=0.4)
        self.assertFalse(trim_want(**base))

    def test_trim_retrigger_pulse_rate_limited_by_ton(self):
        # want 已持续，ton 未到点：不发
        self.assertFalse(trim_retrigger_pulse(want=True, ton_q=False, pulse_prev=False))
        # ton 到点首发一拍
        self.assertTrue(trim_retrigger_pulse(want=True, ton_q=True, pulse_prev=False))
        # 拍后 prev=want 保持：不再发（下一次要 want 掉过再起）
        self.assertFalse(trim_retrigger_pulse(want=True, ton_q=True, pulse_prev=True))
        # want 掉过再起：可再发（≥200ms 限频由 TON 保证）
        self.assertTrue(trim_retrigger_pulse(want=True, ton_q=True, pulse_prev=False))

    def test_moverel_decel_dist_uses_actual_speed(self):
        self.assertAlmostEqual(moverel_decel_dist(0.4, 0.8), 0.1)
        self.assertEqual(moverel_decel_dist(0.0, 0.8), 0.0)
        self.assertAlmostEqual(moverel_decel_dist(0.2, 0.8), 0.025)

    def test_moverel_decel_trigger_remaining_le_dist(self):
        # 剩 0.08 = 减速距离 0.1 之内 → 触发
        self.assertTrue(moverel_decel_trigger(armed=True, moved=0.92, dist=1.0,
                                              decel_dist=0.1))
        self.assertFalse(moverel_decel_trigger(armed=True, moved=0.5, dist=1.0,
                                               decel_dist=0.1))

    def test_moverel_decel_trigger_not_at_standstill(self):
        # 静止 moved=0：短走距不得误触发
        self.assertFalse(moverel_decel_trigger(armed=True, moved=0.0, dist=0.05,
                                               decel_dist=0.1))
        # 未武装不得触发
        self.assertFalse(moverel_decel_trigger(armed=False, moved=0.5, dist=1.0,
                                               decel_dist=0.1))

    def test_req_vel_ramp_blocked_during_decel(self):
        base = dict(e_mode=1, power_gate=True, power_settled=True, vel_appl=0.4)
        self.assertTrue(req_vel_ramp(**base))
        self.assertFalse(req_vel_ramp(decel_active=True, **base))
        self.assertFalse(req_vel_ramp(decel_done=True, **base))

    def test_exec_hold_059_drops_execute_when_halt_takes_over(self):
        # 0.59 与 0.58 相反：减速期必须撤 Execute，Halt 才不被速度指令抢轴
        self.assertFalse(exec_hold_059(e_mode=0, req=False, decel_active=True,
                                       hold_prev=True))
        self.assertFalse(exec_hold_059(e_mode=1, req=False, decel_active=True,
                                       hold_prev=True))
        self.assertTrue(exec_hold_059(e_mode=1, req=True, decel_active=False,
                                      hold_prev=False))
        self.assertFalse(exec_hold_059(e_mode=0, req=False, decel_active=False,
                                       hold_prev=True))

    def test_halt_level_ramp_suppressed_during_decel(self):
        self.assertFalse(halt_level_ramp(stopping=True, e_mode=0, moving=True,
                                         decel_active=True))
        self.assertTrue(halt_level_ramp(stopping=True, e_mode=0, moving=True,
                                        decel_active=False))

    def test_single_edge_startup_no_retrigger_storm(self):
        # 0.59 回归：起步全程（含爬坡）只允许 1 个 Execute 上升沿（无 trim 漂移时）。
        # 0.58 的每步重触发在此仿真下产生 ~125 个沿（4ms 交替一拍）。
        def exec_059(req, decel_active, hold_prev, trim_pulse, exec_prev):
            hold = exec_hold_059(e_mode=1, req=req, decel_active=decel_active,
                                 hold_prev=hold_prev)
            return hold and not trim_pulse

        # 仿真：0.4 m/s 点动，acc=0.8 → SM3 爬坡 0.5s（125 拍）；跑 2s
        dt = 0.004
        edges = 0
        hold = False
        exec_prev = False
        v_act = 0.0
        for i in range(500):
            req = (i >= 20)  # 上使能 80ms 后
            if req and v_act < 0.4:
                v_act = min(v_act + 0.8 * dt, 0.4)
            # 无视觉：trim_want 恒 FALSE → 无脉冲
            exec_now = exec_059(req, False, hold, False, exec_prev)
            if exec_now and not exec_prev:
                edges += 1
            hold = exec_now
            exec_prev = exec_now
        self.assertEqual(edges, 1)

    def test_058_retrigger_storm_reproduced_for_comparison(self):
        # 0.58 对照：爬坡期每拍交替撤/置 Execute → 上升沿数量 ≈ 爬坡拍数的一半。
        # 现场症状（起步冲 2 次 ~1s + M2 慢）与沿风暴强相关，0.59 已删除该机制。
        pulse = False
        edges = 0
        exec_prev = False
        for i in range(125):  # 0.5s 爬坡
            pulse = not pulse  # 0.58：xRampPulse 每拍翻转
            exec_now = pulse
            if exec_now and not exec_prev:
                edges += 1
            exec_prev = exec_now
        self.assertEqual(edges, 63)
