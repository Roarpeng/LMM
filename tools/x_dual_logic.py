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
