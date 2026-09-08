"""Action validation and safety enforcement."""
import re
from typing import List


class SafetyGovernor:
    """Validates all planned actions before execution."""

    # Forbidden key combinations that could close/logout/destroy things
    FORBIDDEN_KEYS = [
        'alt+f4', 'ctrl+w', 'ctrl+q', 'ctrl+alt+del',
        'ctrl+alt+backspace', 'super+l', 'alt+tab',
    ]

    # Allowed printable characters for typing
    ALLOWED_CHARS_RE = re.compile(r'^[\x20-\x7E\n\t]+$')

    def __init__(self, safe_mode: bool = False):
        self.safe_mode = safe_mode
        self._log: List[str] = []

    def log(self, action: str):
        self._log.append(action)

    def check_key(self, keyspec: str) -> bool:
        """Return True if keyspec is allowed."""
        ks = keyspec.lower().replace(' ', '')
        for forbidden in self.FORBIDDEN_KEYS:
            if forbidden.replace(' ', '') == ks:
                return False
        return True

    def check_type_text(self, text: str) -> bool:
        """Return True if text only contains safe characters."""
        return bool(self.ALLOWED_CHARS_RE.match(text))

    def check_click(self, x: int, y: int, danger_zones: List) -> bool:
        """Return True if coordinate is outside danger zones."""
        for zx, zy, zw, zh in danger_zones:
            if zx <= x < zx + zw and zy <= y < zy + zh:
                return False
        return True

    def get_logs(self) -> List[str]:
        return self._log.copy()
