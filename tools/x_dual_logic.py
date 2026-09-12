# tools/x_dual_logic.py
from dataclasses import dataclass

@dataclass
class MoveState:
    armed: bool = False
    start: float = 0.0
    prev_move: bool = False

def select_mode(jog_pos, jog_neg, spin_l, spin_r, move_rel, stop, enable, direct=False):
    if stop or not enable:
        return 0
    if spin_l ^ spin_r:
        return 2 if spin_l else 3
    if direct:
        return 4
    if (jog_pos ^ jog_neg) or move_rel:
        return 1
    return 0

def base_vel(mode, jog_pos, jog_neg, jog_vel, move_rel, move_dist, move_vel):
    if mode != 1:
        return 0.0
    if move_rel:
        return (1.0 if move_dist >= 0.0 else -1.0) * abs(move_vel)
    if jog_pos ^ jog_neg:
        return abs(jog_vel) if jog_pos else -abs(jog_vel)
    return 0.0

def move_done_update(state, *, move_rel, stop, enable, pos_m1, pos_m2, move_dist):
    avg = 0.5 * (pos_m1 + pos_m2)
    if stop or not enable or not move_rel:
        return False, MoveState(armed=False, start=0.0, prev_move=False)
    edge = move_rel and not state.prev_move
    armed = state.armed
    start = state.start
    if edge:
        armed = True
        start = avg
    done = armed and abs(avg - start) >= abs(move_dist)
    return done, MoveState(armed=armed, start=start, prev_move=True)


# hold_state: 0=Run, 1=Decel, 2=SoftHold
# latched：一旦进入 SoftHold，静止噪声不得退出（直到运动/急停/失能）
# ton_fallback（0.20）：eMode=0 持续 2s 且双轴低速 < rHoldVelMax 强制进入，
#   治极限环摆动速度噪声 > 0.01 导致静止条件永不满足、SoftHold 进不去。
def hold_state(*, e_mode, x_stop, x_enable, ton_still_m1, ton_still_m2,
               latched=False, ton_fallback=False):
    if x_stop or not x_enable or e_mode != 0:
        return 0, False
    if latched or (ton_still_m1 and ton_still_m2) or ton_fallback:
        return 2, True
    return 1, False


def sync_trim_active(*, e_mode, x_sync_enable, move_rel=False):
    """0.23：直行 Jog/MoveRel 都开位置 trim（线轴防拧架）；不再限 MoveRel。"""
    del move_rel  # 保留参数兼容旧调用
    return e_mode == 1 and bool(x_sync_enable)


def sync_err_linear(pos_m1, pos_m2):
    """0.23 线轴：同步误差直接差分，禁止 ±180/360 旋转折算。"""
    return float(pos_m1) - float(pos_m2)


def m1_vel_execute(*, motion_req, soft_hold, vel_abs, vel_error):
    """M1 MC_MoveVelocity.Execute：仅运动；SoftHold 不占用任何运动 FB。"""
    if vel_error or soft_hold:
        return False
    return bool(motion_req) and abs(vel_abs) > 0.001


def m1_regulator_on(*, soft_hold=False, x_enable=True, x_stop=False, e_mode=0,
                    moving=False, stopping=False):
    """0.45：点动中上调节器；松手后短窗 stopping 仍保持，好让 Halt 刹完再卸。"""
    del soft_hold, moving
    return x_reg_on(enable=x_enable, stop=x_stop, e_mode=e_mode, stopping=stopping)


def x_reg_on(*, enable, stop, e_mode, pos_zeroed=True, set_pos_req=False, stopping=False):
    """调节器：运动中或松手短窗。置零不得钉死。"""
    del pos_zeroed, set_pos_req
    if (not enable) or stop:
        return False
    return int(e_mode) != 0 or bool(stopping)


def x_power_fb_enable(*, enable=True):
    """MC_Power.Enable 恒 TRUE（对齐 FB_Servo）。卸使能只走 bRegulatorOn。"""
    del enable
    return True


def x_power_settled(*, status, e_mode, reg_on, settled_ton=False, was_stopping=False,
                    standstill=True, ready_prev=False):
    """冷启动：80ms+standstill 闭锁一次。运动中不得因离开 standstill 掉 Execute。"""
    if (not status) or int(e_mode) == 0 or (not reg_on):
        return False
    if was_stopping or ready_prev:
        return True
    return bool(settled_ton) and bool(standstill)


def vel_fb_hold(prev, target, *, eps=0.004):
    """FB Velocity 死区：小于 eps 的 trim/残差噪声不改目标，避免 Acc 反复重爬。"""
    if abs(float(target) - float(prev)) < abs(float(eps)):
        return float(prev)
    return float(target)


def can_drop_regulator(*, standstill_m1, standstill_m2):
    """只有双轴 standstill 才能卸调节器。超时也不得在运动中卸使能。"""
    return bool(standstill_m1) and bool(standstill_m2)


def stop_fallback(*, stopping, timeout, standstill_m1, standstill_m2):
    """Halt 迟迟不到静止才改发 Stop；仍然等到 standstill 再卸使能。"""
    if (not stopping) or (not timeout):
        return False
    return not (bool(standstill_m1) and bool(standstill_m2))


def suppress_fault(*, soft_hold, axis_error, i_hold_state=0, jog_grace_done=True):
    """0.23 SoftHold/Decel 抑 Fault；0.37 再按起步宽限内也抑，避免残留 bError→StopAll。"""
    hold_idle = bool(soft_hold) or int(i_hold_state) == 1 or (not bool(jog_grace_done))
    return bool(axis_error) and not hold_idle


def vel_execute(*, req, dir_flip, vel_error, busy=False):
    """起步失败才撤 Execute；已经 Busy 时再撤会单边掉速、龙门拉扯。"""
    if (not req) or dir_flip:
        return False
    if vel_error and not busy:
        return False
    return True


def gantry_drop_retry(*, err_m1, err_m2, busy_m1, busy_m2):
    """任一侧起步 Error 则两侧一起撤；两侧都 Busy 则不撤。"""
    if not (err_m1 or err_m2):
        return False
    return not (busy_m1 and busy_m2)


def sync_expect_step(*, expect, trim, dt, capture, pos_diff):
    """本段开始锁定当前 ΔPos；之后只把视觉差速积进期望。"""
    if capture:
        return float(pos_diff)
    return float(expect) + 2.0 * float(trim) * float(dt)


def sync_residual(pos_m1, pos_m2, expect):
    return (float(pos_m1) - float(pos_m2)) - float(expect)


def friction_pos_corr(resid, *, kp=0.3, deadband=0.01, trim_max=0.08):
    """只纠残差（摩擦/安装），不纠视觉故意造出的 ΔPos。"""
    if abs(float(resid)) <= abs(float(deadband)):
        return 0.0
    raw = float(kp) * float(resid)
    lim = abs(float(trim_max))
    if raw > lim:
        return lim
    if raw < -lim:
        return -lim
    return raw


def vision_friction_velocities(v_appl, trim, pos_corr, vel_corr1=0.0, vel_corr2=0.0):
    v1 = float(v_appl) + float(trim) - 0.5 * float(pos_corr) + float(vel_corr1)
    v2 = float(v_appl) - float(trim) + 0.5 * float(pos_corr) + float(vel_corr2)
    return v1, v2


def heading_trim(*, kp, heading, trim_max, deadband=0.003):
    """0.40：减去死区再乘 Kp，过边界连续。"""
    h = float(heading)
    db = abs(float(deadband))
    if abs(h) <= db:
        return 0.0
    if h > 0.0:
        raw = (h - db) * float(kp)
    else:
        raw = (h + db) * float(kp)
    lim = abs(float(trim_max))
    if raw > lim:
        return lim
    if raw < -lim:
        return -lim
    return raw


def trim_lpf(prev, raw, *, dt, tc):
    """只滤视觉 trim，不滤残差。"""
    if abs(float(tc)) <= 0.001:
        return float(raw)
    alpha = float(dt) / (float(tc) + float(dt))
    return float(prev) + alpha * (float(raw) - float(prev))


def apply_axis_ratio(vel, ratio):
    r = float(ratio)
    if r < 0.1:
        r = 0.1
    return float(vel) * r


def need_halt_level(*, power_gate, e_mode, moving, stop, still_done=False, stopping=False):
    """0.45：仅松手短窗且还在动时 Halt；停稳即撤，禁止电平保位（0.42 对打根因）。"""
    del power_gate, still_done
    if stop or int(e_mode) != 0 or (not stopping):
        return False
    return bool(moving)


def m1_track_execute(*, soft_hold, tick, abs_error=False):
    """0.16 AbsTrack 已废：恒不执行，避免占轴挡 Jog。"""
    return False


def m2_dir_flip(*, req_vel, vel_run_prev, vel_cmd, vel_cmd_prev):
    """0.24：与 FB_Servo 一致——运行中换向先撤 Execute 一拍再重触发。"""
    if not (req_vel and vel_run_prev):
        return False
    return (vel_cmd >= 0.0) != (vel_cmd_prev >= 0.0)


def m2_vel_same_sign(vel_m1, vel_m2, *, eps=0.001):
    """0.24：M1 有明确方向时，禁止 trim 把 M2 拧成反号（否则拧架+跟随误差）。"""
    if abs(vel_m1) <= eps:
        return float(vel_m2)
    if vel_m1 > 0.0:
        return max(0.0, float(vel_m2))
    return min(0.0, float(vel_m2))


def m2_vel_request(*, raw, vel_cmd, req_prev=False, vel_error=False, eps=0.001):
    """0.25：指令≈0 或 raw=False 立即撤 Execute。

    旧 0.20a「零速保持 Execute」无效：本机 SoftMotion 在 Execute 保持时
    不刷新 Velocity，松手后 M2 会继续原速跟随。停靠 MC_Halt。
    """
    if vel_error:
        return False
    if (not raw) or abs(vel_cmd) <= eps:
        return False
    return True


def m2_need_halt(*, power_gate, soft_hold, stop, req_vel):
    """0.25/0.26：无速度请求即 Halt；不再被 m2_decel 窗口挡住。"""
    return bool(power_gate) and (not soft_hold) and (not stop) and (not req_vel)


def applied_base_velocity(*, e_mode, r_base, stop=False, enable=True):
    """0.36：按下即目标速度，松开即 0。禁止 PLC 再爬 rVelAppl。"""
    if stop or (not enable) or e_mode == 0:
        return 0.0
    if e_mode == 1:
        return float(r_base)
    return 0.0


def vel_request_no_coast(*, e_mode, soft_hold, power_gate, vel_cmd, vel_appl=0.0,
                         vel_error=False, eps=0.001, power_status=True, power_settled=True):
    """Status 为真且已 settle 才出速度，避免上使能当拍 Execute 连冲。"""
    del vel_appl, soft_hold
    if vel_error or (not power_gate) or e_mode == 0 or (not power_status) or (not power_settled):
        return False
    return abs(vel_cmd) > eps


def one_shot_trim_retrigger(*, gate_apply, already_applied, cmd_m1, exec_m1, cmd_m2, exec_m2, eps=0.005):
    """幅值变化不撤 Execute。"""
    del gate_apply, already_applied, cmd_m1, exec_m1, cmd_m2, exec_m2, eps
    return False


def vision_retrigger_ok(*, at_speed, gap_ok, cmd_m1, exec_m1, cmd_m2, exec_m2, eps=0.008):
    """幅值变化不撤 Execute。与 FB_Servo 力跟随相同：Execute 保持，每拍写 Velocity。"""
    del at_speed, gap_ok, cmd_m1, exec_m1, cmd_m2, exec_m2, eps
    return False


def trim_start_locked(*, e_mode, gate_done):
    """幅值差速不单独等待。"""
    del e_mode, gate_done
    return False


def ramp_lock_fb_vel(*, e_mode, straight_edge, locked_prev, vel_act_m1, vel_act_m2, vel_appl, timeout=False):
    """爬坡期间 FB 只吃基速，避免每拍 trim 改 Velocity 把加速曲线打成多次过冲。"""
    if int(e_mode) != 1:
        return False
    if straight_edge:
        return True
    if timeout:
        return False
    if not locked_prev:
        return False
    need = 0.8 * abs(float(vel_appl))
    if need <= 0.001:
        return False
    if abs(float(vel_act_m1)) >= need and abs(float(vel_act_m2)) >= need:
        return False
    return True


def vel_error_holdoff(*, err, err_prev=False, holdoff_prev=False, holdoff_done=False):
    """Error 上升沿锁 150ms 再允许 Execute，禁止 4ms 连打。"""
    if holdoff_done:
        return False
    if bool(err) and not bool(err_prev):
        return True
    return bool(holdoff_prev)


def corr_limit_for_base(r_base, *, frac=0.25, abs_max=0.08):
    """残差修正不得超过基速的 frac，否则小 JogVel 会被纠成爬行。"""
    lim = abs(float(abs_max))
    b = abs(float(r_base))
    if b > 0.001:
        cap = abs(float(frac)) * b
        if cap < lim:
            lim = cap
    return lim


def floor_cmd_vs_base(cmd, vel_appl, ratio, *, frac=0.5):
    """点动时任一侧不得被 trim/corr 拧到接近 0（单边停、对侧走 = 摇摆）。"""
    r = float(ratio)
    if r < 0.1:
        r = 0.1
    scaled = float(vel_appl) * r
    if abs(scaled) <= 0.001:
        return 0.0
    lo = abs(float(frac)) * abs(scaled)
    c = float(cmd)
    if scaled > 0.0:
        if c < 0.0:
            c = 0.0
        if c < lo:
            c = lo
        return c
    if c > 0.0:
        c = 0.0
    if c > -lo:
        c = -lo
    return c


def dual_jog_vel_request(*, e_mode, power_settled, vel_appl, eps=0.001):
    """直行点动两侧同起同停，不得因单侧 cmd≈0 只撤一侧 Execute。"""
    return int(e_mode) == 1 and bool(power_settled) and abs(float(vel_appl)) > eps


def dual_vel_request(*, e_mode, soft_hold, soft_hold_exit, power_gate, vel_cmd, vel_error=False, eps=0.001):
    """0.27 双速度：Jog 可立刻再触发；SoftHoldExit 不再挡运动。

    0.26 在 SoftHoldExit 同拍 Reset+挡运动，易与 MoveVelocity 抢轴导致 Error
    卡死（表现为：第一次 Jog 正常，再次按住不动，很久/松开后才动）。
    """
    del soft_hold_exit  # 0.27：退出 SoftHold 不再阻塞启动
    if vel_error or soft_hold or (not power_gate) or e_mode == 0:
        return False
    return abs(vel_cmd) > eps


def softhold_exit_should_reset():
    """0.27：SoftHold 已保持调节器，退出不必自动 Reset。"""
    return False


def dual_sync_velocities(r_base, r_heading_trim, r_sync_corr):
    """0.29 双 CSV 对称差速（已弃：两侧互拧导致前进摇晃）。"""
    v1 = float(r_base) + float(r_heading_trim) - 0.5 * float(r_sync_corr)
    v2 = float(r_base) - float(r_heading_trim) + 0.5 * float(r_sync_corr)
    return v1, v2


def hybrid_follow_velocities(r_base, r_heading_trim, r_sync_corr):
    """0.32 混架（已弃：用户要求双速度以配合视觉走直）。"""
    v1 = float(r_base)
    v2 = float(r_base) - 2.0 * float(r_heading_trim) + float(r_sync_corr)
    return v1, v2


def vision_dual_velocities(r_base_appl, r_heading_trim, r_sync_corr=0.0):
    """0.35：视觉角度→差速走直；编码器位置不参与速度（只用于走距）。"""
    del r_sync_corr
    v1 = float(r_base_appl) + float(r_heading_trim)
    v2 = float(r_base_appl) - float(r_heading_trim)
    return v1, v2


def distance_from_avg(pos_m1, pos_m2, start):
    """位置仅作里程：平均位移相对起点。"""
    return 0.5 * (float(pos_m1) + float(pos_m2)) - float(start)


def encoder_sync_gain(*, heading_trim, vis_gate=0.02):
    """视觉已在纠偏时压低编码器同步，避免两套差速抢方向。"""
    if abs(heading_trim) >= vis_gate:
        return 0.25
    return 1.0


def clamp_sync_corr(r_sync_err, *, kp=0.1, deadband=0.05, trim_max=0.15, r_base=0.0):
    """轻 P 同步；修正幅值不超过 |r_base| 的 40%，防拉扯。"""
    if abs(r_sync_err) <= deadband:
        return 0.0
    corr = kp * float(r_sync_err)
    lim = abs(trim_max)
    if abs(r_base) > 0.001:
        lim = min(lim, 0.4 * abs(r_base))
    if corr > lim:
        return lim
    if corr < -lim:
        return -lim
    return corr


def soft_acc(r_acc, *, lo=0.05, hi=None):
    """仅把未填/近零抬到下限；与点动速度同量级的 Acc 必须原样生效。"""
    a = abs(float(r_acc))
    if a < lo:
        return lo
    if hi is not None and a > hi:
        return hi
    return a


def slew_velocity(prev, target, step_max):
    """每周期限速逼近目标：柔和且双侧同斜坡（快≠阶跃）。"""
    step = abs(float(step_max))
    d = float(target) - float(prev)
    if abs(d) <= step:
        return float(target)
    return float(prev) + step if d > 0.0 else float(prev) - step


def sm3_track_acc(user_acc, *, floor=10.0):
    """用户 Acc 只用于 PLC 爬速；送给 SM3 的 Acc 不得低于 floor，避免慢梯形拐点过冲。"""
    a = abs(float(user_acc))
    f = abs(float(floor))
    if a > f:
        return a
    return f


def slew_start_nonzero(prev, target, step_max, *, eps=0.001):
    """0.53 实验：第一拍非零。0.54 不再用爬速，改上升沿锁目标。"""
    v = slew_velocity(prev, target, step_max)
    if abs(v) < abs(float(eps)) and abs(float(target)) > abs(float(eps)):
        step = abs(float(step_max))
        if step < abs(float(eps)):
            step = abs(float(eps))
        return step if float(target) >= 0.0 else -step
    return v


def exec_hold(*, e_mode, req, hold_prev, stop=False, enable=True):
    """点动期间 Execute 闭锁：Status/请求闪一下不得撤 Execute。"""
    if (not enable) or stop or int(e_mode) == 0:
        return False
    if req:
        return True
    return bool(hold_prev)


def jog_hold(*, raw, held_prev, off_done):
    """点动 GVL 空窗：raw 掉了但去抖未满，继续视为按住。"""
    if raw:
        return True
    if off_done:
        return False
    return bool(held_prev)


def vel_latch_on_exec(*, exec_now, exec_prev, target, latched_prev, in_vel=False, eps=0.004):
    """Execute 上升沿锁死目标速度。爬坡中不改；到速后才允许死区更新。"""
    if exec_now and not exec_prev:
        return abs(float(target))
    if not exec_now:
        return 0.0
    if in_vel and abs(abs(float(target)) - float(latched_prev)) >= abs(float(eps)):
        return abs(float(target))
    return float(latched_prev)


def sync_scale_at_speed(*, r_base, r_vel_act_m1, r_vel_act_m2, ratio=0.7):
    """爬升未到速时减弱同步，避免加速超调阶段来回拧。"""
    if abs(r_base) <= 0.001:
        return 0.0
    need = abs(r_base) * ratio
    if abs(r_vel_act_m1) >= need and abs(r_vel_act_m2) >= need:
        return 1.0
    # 按较慢侧进度比例放开同步
    prog = min(abs(r_vel_act_m1), abs(r_vel_act_m2)) / need
    if prog < 0.0:
        return 0.0
    if prog > 1.0:
        return 1.0
    return prog

# ---------------- 0.59 单沿起步 + Halt 对称减速（0.58 每步重触发废除） ----------------
# 0.58 教训（现场 acc=0.8）：每 4ms 重触发 Execute（250Hz 沿风暴）反复踢起龙门
#   1Hz 共振（起步快速冲 2 次 ~1s + 第三次慢 + 停死）；两侧 FB/驱动接受沿的时刻
#   不一致 → M2 漏沿 → 爬速落后（M2 明显慢于 M1）。
# 0.59：起步只发一个上升沿（最终目标 + 钳制用户 Acc/Dec，SM3 自带斜坡 0→目标）；
#   稳态 trim/sync 更新走限频重触发（≥200ms 一次，差值≥0.004）；减速统一 Halt。

def eff_ramp_acc(user_acc, *, cap=1.0, floor=0.05):
    """0.59：SM3 斜坡 Acc/Dec = 用户值钳制 [floor, cap]。25/100 兜底不再等于阶跃。
    0.58 曾把它用于 PLC 爬速步长；0.59 直接作 SM3 剖面斜率。"""
    a = abs(float(user_acc))
    if a < float(floor):
        return float(floor)
    if a > float(cap):
        return float(cap)
    return a


def trim_retrigger_pulse(*, want, ton_q, pulse_prev):
    """0.59：稳态 trim/sync 更新走限频重触发。want 持续 ≥ton(200ms) 首次到点发一拍
    （撤 Execute 一拍，下一拍上升沿重采样）；之后 want 保持不再发，直到 want 掉过再起。
    无视觉/同步漂移时 want 恒 FALSE → 全程单沿。"""
    return bool(want) and bool(ton_q) and not bool(pulse_prev)


def trim_want(*, exec_hold, ramp_lock, in_vel_m1, in_vel_m2, decel_active, stop,
              vel_fb_m1, vel_fb_m2, latch_m1, latch_m2, eps=0.004):
    """0.59：重触发条件——非爬坡期、两侧到速、目标与锁存差 ≥ eps。"""
    if (not exec_hold) or ramp_lock or decel_active or stop:
        return False
    if not (in_vel_m1 and in_vel_m2):
        return False
    return (abs(abs(float(vel_fb_m1)) - abs(float(latch_m1))) >= abs(float(eps))
            or abs(abs(float(vel_fb_m2)) - abs(float(latch_m2))) >= abs(float(eps)))


def moverel_decel_dist(v_act, dec, *, eps=0.001):
    """0.59：提前减速距离 v²/(2·dec)，取实际速度（越保守越早触发）。"""
    if abs(float(v_act)) <= eps or abs(float(dec)) <= 1e-6:
        return 0.0
    return (abs(float(v_act)) ** 2) / (2.0 * abs(float(dec)))


def moverel_decel_trigger(*, armed, moved, dist, decel_dist, eps=0.001):
    """0.59：剩余 ≤ 减速距离且已起步才触发。静止时 moved=0 不得误触发短走距。"""
    if not bool(armed) or abs(float(dist)) <= eps or abs(float(moved)) <= eps:
        return False
    return float(moved) >= abs(float(dist)) - float(decel_dist)


def req_vel_ramp(*, e_mode, power_gate, power_settled, vel_appl, halt_busy=False,
                 decel_active=False, decel_done=False, eps=0.001):
    """0.58→0.59 不变：减速/到位锁期间禁新请求，防止停稳后又爬目标。"""
    if int(e_mode) != 1:
        return False
    if decel_active or decel_done:
        return False
    if halt_busy:
        return False
    return bool(power_gate) and bool(power_settled) and abs(float(vel_appl)) > float(eps)


def exec_hold_059(*, e_mode, req, decel_active, hold_prev, stop=False, enable=True):
    """0.59：减速期撤 Execute（Halt 接管，禁止速度指令抢轴）；点动闭锁同 0.56。
    0.58 在减速期持 Execute 是配合 PLC 爬速；单沿方案下必须撤。"""
    if stop or (not enable):
        return False
    if decel_active:
        return False
    if req:
        return True
    if int(e_mode) in (0, 4):
        return False
    return bool(hold_prev)


def halt_level_ramp(*, stopping, e_mode, moving, decel_active, stop=False):
    """0.58→0.59 不变：减速期间禁 Halt 抢占；松手短窗仍动才发。"""
    if stop or int(e_mode) != 0 or (not stopping):
        return False
    if decel_active:
        return False
    return bool(moving)



def direct_velocities(vel_m1_direct, vel_m2_direct):
    """0.60 外部直控：M1/M2 速度直接来自视觉，不做 trim/sync。"""
    return float(vel_m1_direct), float(vel_m2_direct)


def direct_halt_demand(*, e_mode, req_m1, req_m2, moving_m1, moving_m2):
    """0.60：直控中任一侧目标为 0 且在动 -> 双轴 Halt。"""
    if int(e_mode) != 4:
        return False
    return ((not req_m1) and bool(moving_m1)) or ((not req_m2) and bool(moving_m2))
