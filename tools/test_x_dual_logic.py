# tools/test_x_dual_logic.py
import unittest
from tools.x_dual_logic import select_mode, base_vel, move_done_update, MoveState

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

if __name__ == "__main__":
    unittest.main()
