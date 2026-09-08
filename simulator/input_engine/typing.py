"""Realistic typing with error injection, log-normal delays, and shortcuts."""
import random
import time
from typing import List
from simulator.utils import type_text as _xdotool_type, send_key


# Common substitution errors
_SUBSTITUTIONS = {
    't': 'th', 'h': 'ht',
    'e': 'we', 'a': 'sa', 'o': 'oi',
    'n': 'mn', 's': 'sw',
}


class TypingModel:
    """Generates realistic keystroke sequences with errors and corrections."""

    def __init__(self, error_rate: float = 0.025):
        self.error_rate = error_rate
        self._clipboard: str = ""  # Simulated clipboard for copy/paste

    def _delay_between_keys(self, char: str) -> float:
        """Log-normal inter-key delay; slower after punctuation/spaces."""
        mu = -2.2   # ~110ms median
        sigma = 0.35
        delay = random.lognormvariate(mu, sigma)
        if char in ' .,;:!?\n':
            delay *= random.uniform(1.3, 2.2)
        return max(0.02, delay)

    def _make_error(self, intended: str) -> str:
        """Return an erroneous character(s) for intended char."""
        kind = random.choice(['substitution', 'double', 'adjacent'])
        if kind == 'substitution' and intended.lower() in _SUBSTITUTIONS:
            return _SUBSTITUTIONS[intended.lower()]
        if kind == 'double':
            return intended * 2
        # adjacent: just duplicate (simplified)
        return intended * 2

    def type_burst(self, text: str, with_shortcuts: bool = True):
        """Type a burst of text with realistic errors and timing.
        This sends REAL keys via xdotool to the currently focused window.
        The caller must ensure the correct window is focused (e.g., sandbox).
        """
        i = 0
        while i < len(text):
            intended = text[i]
            # Error injection
            if random.random() < self.error_rate:
                error_type = random.choice(['substitution', 'double', 'omit'])
                if error_type == 'omit':
                    i += 1
                    continue
                # Type the error chars one by one
                err_chars = self._make_error(intended)
                for ec in err_chars:
                    _xdotool_type(ec)
                    time.sleep(self._delay_between_keys(ec))
                # Correction behavior
                correction = random.choice(['backspace', 'backspace', 'ctrl_z'])
                if correction == 'backspace':
                    for _ in err_chars:
                        send_key('BackSpace')
                        time.sleep(random.lognormvariate(-2.0, 0.3))
                else:
                    send_key('ctrl+z')
                    time.sleep(0.15)
                # Retype correctly
                _xdotool_type(intended)
            else:
                if intended == '\n':
                    send_key('Return')
                else:
                    _xdotool_type(intended)

            time.sleep(self._delay_between_keys(intended))
            i += 1

        # Occasional post-burst shortcut
        if with_shortcuts and random.random() < 0.06:
            shortcut = random.choice(['ctrl+s', 'ctrl+a', 'ctrl+c', 'ctrl+v'])
            time.sleep(random.uniform(0.2, 0.5))
            send_key(shortcut)
            if shortcut == 'ctrl+c':
                self._clipboard = text  # simulate clipboard

    def generate_prose(self, min_words: int = 3, max_words: int = 12) -> str:
        """Generate a short realistic prose burst."""
        words = [
            "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
            "function", "return", "data", "vector", "index", "query",
            "build", "test", "deploy", "monitor", "alert", "scale",
            "user", "interface", "component", "state", "props", "render",
            "async", "await", "promise", "callback", "middleware",
        ]
        n = random.randint(min_words, max_words)
        return ' '.join(random.choices(words, k=n)) + random.choice([' ', '.', '\n'])

    def generate_code_line(self) -> str:
        """Generate a code-like line."""
        templates = [
            "def {fn}({args}):\n",
            "    {var} = {val}\n",
            "    return {var}\n",
            "for {var} in {iter}:\n",
            "    print({var})\n",
            "if {cond}:\n",
            "    {action}\n",
            "# TODO: fix {issue}\n",
            "import {lib}\n",
        ]
        t = random.choice(templates)
        return t.format(
            fn=random.choice(["process", "fetch", "update", "render", "handle"]),
            args=random.choice(["x", "data", "ctx", "req"]),
            var=random.choice(["result", "data", "item", "response"]),
            val=random.choice(["[]", "0", "None", "True", "{}"]),
            iter=random.choice(["items", "range(10)", "data", "results"]),
            cond=random.choice(["ok", "valid", "x > 0", "not err"]),
            action=random.choice(["pass", "break", "continue", "return"]),
            issue=random.choice(["bug", "edge case", "performance", "naming"]),
            lib=random.choice(["json", "os", "sys", "math", "re"]),
        )

    def generate_shell_command(self) -> str:
        """Generate a terminal-like command."""
        cmds = [
            "ls -la\n",
            "git status\n",
            "git pull\n",
            "docker ps\n",
            "python3 -m pytest\n",
            "npm run dev\n",
            "cd src/\n",
            "cat README.md\n",
            "make build\n",
            "sudo apt update\n",
        ]
        return random.choice(cmds)
