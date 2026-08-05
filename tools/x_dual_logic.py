# tools/x_dual_logic.py
from dataclasses import dataclass

@dataclass
class MoveState:
    armed: bool = False
    start: float = 0.0
    prev_move: bool = False

def select_mode(jog_pos, jog_neg, spin_l, spin_r, move_rel, stop, enable):
    if stop or not enable:
        return 0
    if spin_l ^ spin_r:
        return 2 if spin_l else 3
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


def m1_regulator_on(*, soft_hold, x_enable=True, x_stop=False):
    """0.23 SoftHold：线轴保持调节器，禁止松调节器造成「丢使能」。"""
    del soft_hold
    return bool(x_enable) and not bool(x_stop)


def suppress_fault(*, soft_hold, axis_error, i_hold_state=0):
    """0.23：SoftHold 与 Decel（iHoldState=1）都抑制 Fault，避免松手→StopAll→掉使能。"""
    hold_idle = bool(soft_hold) or int(i_hold_state) == 1
    return bool(axis_error) and not hold_idle


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
    """0.29 双 CSV 对称差速：平均≈r_base，视觉/同步成对作用，避免只拧 M2 拉扯。

    视觉：M1=+trim, M2=-trim（与旧式 M2=M1-2*trim 差速等价）
    同步：M1 超前(sync>0) → M1 减速、M2 加速各一半
    """
    v1 = float(r_base) + float(r_heading_trim) - 0.5 * float(r_sync_corr)
    v2 = float(r_base) - float(r_heading_trim) + 0.5 * float(r_sync_corr)
    return v1, v2


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


def soft_acc(r_acc, *, lo=0.8, hi=None):
    """0.31：仅保底下限；上限交给 HMI rAcc（0.30 的 hi=4 会钳死现场调参）。"""
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
