"""Pure unit tests requiring no X11 display."""
import unittest
import math
import random

from simulator.state_machine import (
    BehaviorStateMachine, MacroState, MicroAction,
    STATE_MIN_DURATION, STATE_ACTION_WEIGHTS, STATE_TRANSITIONS
)
from simulator.behavior.fatigue import TemporalModel
from simulator.safety.governor import SafetyGovernor
from simulator.input_engine.typing import TypingModel
from simulator.context.screen import ScreenManager
from simulator.input_engine.watchdog import InputWatchdog


class TestStateMachineUnit(unittest.TestCase):
    """Verify state machine logic without any X11 calls."""

    def test_initial_state_is_break(self):
        hsm = BehaviorStateMachine()
        self.assertEqual(hsm.state, MacroState.BREAK)

    def test_time_in_state_increases(self):
        hsm = BehaviorStateMachine()
        hsm.enter_state(MacroState.READING)
        import time
        time.sleep(0.05)
        self.assertGreater(hsm.time_in_state(), 0.04)

    def test_cannot_transition_before_min_duration(self):
        hsm = BehaviorStateMachine()
        hsm.enter_state(MacroState.READING)
        # READING min is 20s, so immediate transition should fail
        self.assertFalse(hsm.can_transition())
        transitioned = hsm.force_transition(fatigue_break_prob=0.0)
        self.assertFalse(transitioned)
        self.assertEqual(hsm.state, MacroState.READING)

    def test_all_states_have_min_duration(self):
        for state in MacroState:
            self.assertIn(state, STATE_MIN_DURATION)
            min_d, max_d = STATE_MIN_DURATION[state]
            self.assertGreater(max_d, min_d)
            self.assertGreater(min_d, 0)

    def test_all_states_have_action_weights(self):
        for state in MacroState:
            self.assertIn(state, STATE_ACTION_WEIGHTS)
            weights = STATE_ACTION_WEIGHTS[state]
            self.assertGreater(len(weights), 0)
            self.assertGreater(sum(weights.values()), 0)

    def test_all_states_have_transitions(self):
        for state in MacroState:
            self.assertIn(state, STATE_TRANSITIONS)
            transitions = STATE_TRANSITIONS[state]
            self.assertIn(state, transitions)  # self-loop must exist
            self.assertGreater(sum(transitions.values()), 0)

    def test_sample_action_returns_valid_action(self):
        hsm = BehaviorStateMachine()
        for _ in range(100):
            action = hsm.sample_action()
            self.assertIsInstance(action, MicroAction)

    def test_action_distribution_roughly_matches_weights(self):
        """Sample many actions and verify frequencies roughly match weights."""
        hsm = BehaviorStateMachine()
        hsm.enter_state(MacroState.READING)
        weights = STATE_ACTION_WEIGHTS[MacroState.READING]
        total_weight = sum(weights.values())
        expected = {a: w / total_weight for a, w in weights.items()}

        counts = {a: 0 for a in weights}
        n = 2000
        for _ in range(n):
            counts[hsm.sample_action()] += 1

        for action, exp in expected.items():
            obs = counts[action] / n
            # Allow ±10 percentage points tolerance
            self.assertAlmostEqual(obs, exp, delta=0.10,
                msg=f"Action {action.name}: expected {exp:.2f}, got {obs:.2f}")

    def test_transition_matrix_observables(self):
        """Force many transitions and verify we see expected targets."""
        hsm = BehaviorStateMachine()
        # Patch time so we can transition immediately
        hsm.state_entry_time = 0
        hsm._last_transition_check = 0

        from_state = MacroState.READING
        hsm.state = from_state
        targets = {s: 0 for s in MacroState}
        n = 1000
        for _ in range(n):
            hsm.state_entry_time = 0
            hsm.force_transition(fatigue_break_prob=0.0)
            targets[hsm.state] += 1
            hsm.state = from_state

        expected = STATE_TRANSITIONS[from_state]
        total = sum(expected.values())
        for s, w in expected.items():
            exp_prob = w / total
            obs_prob = targets[s] / n
            self.assertAlmostEqual(obs_prob, exp_prob, delta=0.08,
                msg=f"Transition {from_state.name} -> {s.name}: expected {exp_prob:.2f}, got {obs_prob:.2f}")


class TestTemporalModelUnit(unittest.TestCase):
    def test_circadian_factor_range(self):
        tm = TemporalModel()
        val = tm.circadian_factor()
        self.assertGreaterEqual(val, 0.5)
        self.assertLessEqual(val, 1.0)

    def test_fatigue_factor_zero_at_start(self):
        tm = TemporalModel()
        self.assertLess(tm.fatigue_factor(), 0.02)

    def test_fatigue_factor_increases_over_time(self):
        tm = TemporalModel()
        tm._start_time -= 3600  # Pretend we started 1 hour ago
        fat = tm.fatigue_factor()
        self.assertGreater(fat, 0.3)
        self.assertLess(fat, 1.0)

    def test_focus_duration_range_bounds(self):
        tm = TemporalModel()
        mn, mx = tm.focus_duration_range()
        self.assertGreater(mx, mn)
        self.assertGreater(mn, 20)

    def test_break_probability_positive(self):
        tm = TemporalModel()
        self.assertGreater(tm.break_probability(), 0)

    def test_reading_pause_duration_positive(self):
        tm = TemporalModel()
        self.assertGreater(tm.reading_pause_duration(), 0)

    def test_pause_between_actions_positive(self):
        tm = TemporalModel()
        self.assertGreater(tm.pause_between_actions(), 0)


class TestSafetyGovernorUnit(unittest.TestCase):
    def test_forbidden_keys_blocked(self):
        gov = SafetyGovernor()
        self.assertFalse(gov.check_key('alt+f4'))
        self.assertFalse(gov.check_key('ctrl+w'))
        self.assertFalse(gov.check_key('ctrl+q'))

    def test_safe_keys_allowed(self):
        gov = SafetyGovernor()
        self.assertTrue(gov.check_key('a'))
        self.assertTrue(gov.check_key('ctrl+s'))
        self.assertTrue(gov.check_key('BackSpace'))

    def test_unsafe_text_blocked(self):
        gov = SafetyGovernor()
        self.assertFalse(gov.check_type_text("hello\x00world"))
        self.assertFalse(gov.check_type_text("test\x01"))

    def test_safe_text_allowed(self):
        gov = SafetyGovernor()
        self.assertTrue(gov.check_type_text("hello world"))
        self.assertTrue(gov.check_type_text("def foo():\n    pass"))

    def test_click_in_danger_zone_blocked(self):
        gov = SafetyGovernor()
        zones = [(0, 0, 1920, 40), (0, 1040, 1920, 40)]
        self.assertFalse(gov.check_click(100, 20, zones))
        self.assertFalse(gov.check_click(1800, 10, zones))
        self.assertTrue(gov.check_click(500, 500, zones))


class TestTypingModelUnit(unittest.TestCase):
    def test_generate_prose_length(self):
        tm = TypingModel()
        text = tm.generate_prose(min_words=5, max_words=5)
        words = text.strip().split()
        self.assertEqual(len(words), 5)

    def test_generate_code_line_has_newline(self):
        tm = TypingModel()
        line = tm.generate_code_line()
        self.assertIn('\n', line)

    def test_generate_shell_command_ends_with_newline(self):
        tm = TypingModel()
        cmd = tm.generate_shell_command()
        self.assertTrue(cmd.endswith('\n'))

    def test_delay_between_keys_positive(self):
        tm = TypingModel()
        d = tm._delay_between_keys('a')
        self.assertGreater(d, 0)

    def test_make_error_returns_non_empty(self):
        tm = TypingModel()
        err = tm._make_error('a')
        self.assertTrue(len(err) > 0)


class TestScreenManagerUnit(unittest.TestCase):
    def test_fallback_monitor_exists(self):
        sm = ScreenManager()
        self.assertGreater(len(sm.monitors), 0)

    def test_primary_has_required_keys(self):
        sm = ScreenManager()
        p = sm.primary
        for k in ('name', 'primary', 'width', 'height', 'x', 'y'):
            self.assertIn(k, p)

    def test_danger_zones_non_empty(self):
        sm = ScreenManager()
        zones = sm.danger_zones()
        self.assertGreater(len(zones), 0)
        for z in zones:
            self.assertEqual(len(z), 4)

    def test_safe_coordinate_center(self):
        sm = ScreenManager()
        p = sm.primary
        cx = p['x'] + p['width'] // 2
        cy = p['y'] + p['height'] // 2
        self.assertTrue(sm.is_safe_coordinate(cx, cy))

    def test_safe_point_in_window_returns_none_for_tiny_window(self):
        sm = ScreenManager()
        # A 10x10 window with padding=60 should have no safe points
        result = sm.safe_point_in_window(0, 0, 10, 10, padding=60)
        self.assertIsNone(result)


class TestBezierMathUnit(unittest.TestCase):
    def test_cubic_bezier_endpoints(self):
        from simulator.input_engine.motion import _cubic_bezier
        self.assertAlmostEqual(_cubic_bezier(0, 10, 20, 30, 40), 10)
        self.assertAlmostEqual(_cubic_bezier(1, 10, 20, 30, 40), 40)

    def test_ease_in_out_sine_bounds(self):
        from simulator.input_engine.motion import _ease_in_out_sine
        self.assertAlmostEqual(_ease_in_out_sine(0), 0)
        self.assertAlmostEqual(_ease_in_out_sine(1), 1)
        self.assertGreater(_ease_in_out_sine(0.5), 0.4)
        self.assertLess(_ease_in_out_sine(0.5), 0.6)


class TestInputWatchdogUnit(unittest.TestCase):
    def test_initially_considers_user_active(self):
        # Watchdog starts with last_activity = now, so user is "active"
        # until idle_timeout passes without input.
        wd = InputWatchdog(idle_timeout_sec=0.1)
        self.assertTrue(wd.is_user_active)
        import time
        time.sleep(0.15)
        self.assertFalse(wd.is_user_active)

    def test_poke_marks_active(self):
        wd = InputWatchdog()
        wd.poke()
        self.assertTrue(wd.is_user_active)

    def test_activity_expires(self):
        wd = InputWatchdog(idle_timeout_sec=0.05)
        wd.poke()
        self.assertTrue(wd.is_user_active)
        import time
        time.sleep(0.08)
        self.assertFalse(wd.is_user_active)

    def test_seconds_since_activity_increases(self):
        wd = InputWatchdog()
        import time
        time.sleep(0.05)
        self.assertGreater(wd.seconds_since_activity, 0.04)


if __name__ == '__main__':
    unittest.main()
