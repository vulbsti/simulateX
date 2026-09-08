"""Hierarchical State Machine with sticky macro states and micro actions."""
import random
import time
from enum import Enum, auto
from typing import Optional, Dict, Any


class MacroState(Enum):
    READING = auto()
    SWITCHING = auto()
    TYPING = auto()
    BREAK = auto()


class MicroAction(Enum):
    TYPE_BURST = auto()
    SCROLL = auto()
    MOUSE_NUDGE = auto()
    SWITCH_TAB = auto()
    SWITCH_WINDOW = auto()
    READING_PAUSE = auto()


# Minimum seconds to stay in a macro state before allowed to transition
STATE_MIN_DURATION: Dict[MacroState, tuple] = {
    MacroState.READING: (20, 180),
    MacroState.SWITCHING: (5, 30),
    MacroState.TYPING: (5, 40),
    MacroState.BREAK: (10, 60),
}

# Action probability tables per state (weights)
STATE_ACTION_WEIGHTS: Dict[MacroState, Dict[MicroAction, int]] = {
    MacroState.READING: {
        MicroAction.SCROLL: 50,
        MicroAction.MOUSE_NUDGE: 20,
        MicroAction.READING_PAUSE: 25,
        MicroAction.SWITCH_TAB: 5,
    },
    MacroState.SWITCHING: {
        MicroAction.SWITCH_WINDOW: 45,
        MicroAction.SWITCH_TAB: 35,
        MicroAction.MOUSE_NUDGE: 15,
        MicroAction.READING_PAUSE: 5,
    },
    MacroState.TYPING: {
        MicroAction.TYPE_BURST: 55,
        MicroAction.READING_PAUSE: 20,
        MicroAction.SCROLL: 15,
        MicroAction.MOUSE_NUDGE: 10,
    },
    MacroState.BREAK: {
        MicroAction.READING_PAUSE: 70,
        MicroAction.MOUSE_NUDGE: 25,
        MicroAction.TYPE_BURST: 5,
    },
}

# Transition matrix: from_state -> {to_state: weight}
STATE_TRANSITIONS: Dict[MacroState, Dict[MacroState, int]] = {
    MacroState.READING: {
        MacroState.SWITCHING: 30,
        MacroState.TYPING: 15,
        MacroState.BREAK: 10,
        MacroState.READING: 45,
    },
    MacroState.SWITCHING: {
        MacroState.READING: 40,
        MacroState.TYPING: 20,
        MacroState.BREAK: 10,
        MacroState.SWITCHING: 30,
    },
    MacroState.TYPING: {
        MacroState.READING: 40,
        MacroState.SWITCHING: 25,
        MacroState.BREAK: 10,
        MacroState.TYPING: 25,
    },
    MacroState.BREAK: {
        MacroState.READING: 40,
        MacroState.SWITCHING: 30,
        MacroState.TYPING: 20,
        MacroState.BREAK: 10,
    },
}


class BehaviorStateMachine:
    """Hierarchical state machine that stays sticky and context-aware."""

    def __init__(self):
        self.state = MacroState.BREAK
        self.state_entry_time = time.time()
        self.action_history: list = []
        self._last_transition_check = 0.0

    def enter_state(self, new_state: MacroState):
        self.state = new_state
        self.state_entry_time = time.time()
        self._last_transition_check = time.time()

    def time_in_state(self) -> float:
        return time.time() - self.state_entry_time

    def can_transition(self) -> bool:
        min_sec, max_sec = STATE_MIN_DURATION[self.state]
        return self.time_in_state() >= min_sec

    def force_transition(self, fatigue_break_prob: float = 0.0) -> bool:
        """Attempt to transition based on transition matrix + fatigue.
        Returns True if a transition occurred.
        """
        if not self.can_transition():
            return False

        probs = dict(STATE_TRANSITIONS[self.state])
        # Fatigue increases chance of BREAK
        if MacroState.BREAK in probs:
            probs[MacroState.BREAK] += int(fatigue_break_prob * 100)

        states = list(probs.keys())
        weights = list(probs.values())
        chosen = random.choices(states, weights=weights, k=1)[0]

        if chosen != self.state:
            self.enter_state(chosen)
            return True
        return False

    def sample_action(self) -> MicroAction:
        """Sample a micro-action appropriate for the current macro state."""
        weights = STATE_ACTION_WEIGHTS.get(self.state, {})
        actions = list(weights.keys())
        wvals = list(weights.values())
        return random.choices(actions, weights=wvals, k=1)[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'state': self.state.name,
            'time_in_state': self.time_in_state(),
            'can_transition': self.can_transition(),
        }
