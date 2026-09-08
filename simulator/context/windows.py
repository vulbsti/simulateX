"""Window detection and classification with normalized integer IDs."""
from enum import Enum, auto
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from simulator.utils import get_window_list, get_active_window_id


class WindowType(Enum):
    BROWSER = auto()
    TERMINAL = auto()
    EDITOR = auto()
    FILE_MANAGER = auto()
    CHAT = auto()
    OTHER = auto()


_BROWSER_KEYS = ['chrome', 'chromium', 'firefox', 'brave', 'opera', 'vivaldi', 'edge']
_TERMINAL_KEYS = ['gnome-terminal', 'terminator', 'xterm', 'konsole', 'tilix', 'alacritty', 'kitty', 'urxvt']
_EDITOR_KEYS = ['code', 'sublime', 'atom', 'gedit', 'vim', 'emacs', 'jetbrains', 'idea', 'pycharm', 'cursor']
_FILE_KEYS = ['nautilus', 'thunar', 'dolphin', 'nemo', 'pcmanfm', 'files']
_CHAT_KEYS = ['slack', 'discord', 'telegram', 'whatsapp', 'signal', 'teams', 'element']


@dataclass
class WindowInfo:
    id: int
    hex_id: str
    window_class: str
    title: str
    window_type: WindowType = WindowType.OTHER
    geometry: Optional[Dict] = field(default=None, repr=False)

    @property
    def is_browser(self) -> bool:
        return self.window_type == WindowType.BROWSER

    @property
    def is_terminal(self) -> bool:
        return self.window_type == WindowType.TERMINAL

    @property
    def is_editor(self) -> bool:
        return self.window_type == WindowType.EDITOR


class WindowManager:
    """Robust window list with caching and normalized IDs."""

    def __init__(self, cache_ttl: float = 2.0):
        self._cache_ttl = cache_ttl
        self._last_refresh = 0.0
        self._windows: List[WindowInfo] = []
        self._active: Optional[WindowInfo] = None

    def _classify(self, window_class: str, title: str) -> WindowType:
        wc = window_class.lower()
        tl = title.lower()
        combined = wc + ' ' + tl
        for k in _BROWSER_KEYS:
            if k in combined:
                return WindowType.BROWSER
        for k in _TERMINAL_KEYS:
            if k in combined:
                return WindowType.TERMINAL
        for k in _EDITOR_KEYS:
            if k in combined:
                return WindowType.EDITOR
        for k in _FILE_KEYS:
            if k in combined:
                return WindowType.FILE_MANAGER
        for k in _CHAT_KEYS:
            if k in combined:
                return WindowType.CHAT
        return WindowType.OTHER

    def refresh(self) -> List[WindowInfo]:
        """Refresh window list from X11. Returns cached copy if recent."""
        now = __import__('time').time()
        if now - self._last_refresh < self._cache_ttl and self._windows:
            return self._windows

        raw = get_window_list()
        self._windows = []
        active_id = get_active_window_id()

        for r in raw:
            wtype = self._classify(r['class'], r['title'])
            info = WindowInfo(
                id=r['id'],
                hex_id=r['hex_id'],
                window_class=r['class'],
                title=r['title'],
                window_type=wtype,
            )
            self._windows.append(info)
            if r['id'] == active_id:
                self._active = info

        self._last_refresh = now
        return self._windows

    @property
    def windows(self) -> List[WindowInfo]:
        return self._windows

    @property
    def active(self) -> Optional[WindowInfo]:
        return self._active

    def by_type(self, wtype: WindowType) -> List[WindowInfo]:
        return [w for w in self._windows if w.window_type == wtype]

    def find_by_title_substring(self, substring: str) -> Optional[WindowInfo]:
        sub = substring.lower()
        for w in self._windows:
            if sub in w.title.lower():
                return w
        return None
