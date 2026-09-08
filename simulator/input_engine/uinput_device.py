"""Kernel-level input injection via Linux uinput.

This creates virtual keyboard and mouse devices that generate real
EV_KEY / EV_REL events visible to ALL monitoring software including
those that read from /dev/input/event* directly.

Requires write access to /dev/uinput (root or 'input' group).
"""
import os
import struct
import fcntl
import time
import threading
from typing import Optional, Tuple

# ---- uinput constants ----
UI_SET_EVBIT   = 0x40045564
UI_SET_KEYBIT  = 0x40045565
UI_SET_RELBIT  = 0x40045566
UI_DEV_CREATE  = 0x5501
UI_DEV_DESTROY = 0x5502

EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02

REL_X = 0x00
REL_Y = 0x01

SYN_REPORT = 0

# Common keycodes (Linux input event codes)
KEYCODES = {
    'a': 30, 'b': 48, 'c': 46, 'd': 32, 'e': 18, 'f': 33,
    'g': 34, 'h': 35, 'i': 23, 'j': 36, 'k': 37, 'l': 38,
    'm': 50, 'n': 49, 'o': 24, 'p': 25, 'q': 16, 'r': 19,
    's': 31, 't': 20, 'u': 22, 'v': 47, 'w': 17, 'x': 45,
    'y': 21, 'z': 44,
    '0': 11, '1': 2,  '2': 3,  '3': 4,  '4': 5,
    '5': 6,  '6': 7,  '7': 8,  '8': 9,  '9': 10,
    ' ': 57, '\n': 28, '\t': 15,
    'BACKSPACE': 14, 'ENTER': 28, 'ESC': 1, 'TAB': 15,
    'LEFTCTRL': 29, 'LEFTSHIFT': 42, 'LEFTALT': 56,
    'LEFTMETA': 125,
    '-': 12, '=': 13, '[': 26, ']': 27, '\\': 43, ';': 39,
    "'": 40, '`': 41, ',': 51, '.': 52, '/': 53,
}

# struct input_event { struct timeval time; __u16 type; __u16 code; __s32 value; }
# timeval = tv_sec (long), tv_usec (long)
EVENT_FORMAT = 'llHHi'
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


def _make_event(ev_type: int, code: int, value: int) -> bytes:
    """Pack a single input_event struct."""
    ts = time.time()
    sec = int(ts)
    usec = int((ts - sec) * 1_000_000)
    return struct.pack(EVENT_FORMAT, sec, usec, ev_type, code, value)


def _syn_report() -> bytes:
    return _make_event(EV_SYN, SYN_REPORT, 0)


class UInputDevice:
    """Virtual keyboard + mouse via Linux uinput."""

    def __init__(self, name: str = "activity_sim_vinput"):
        self.name = name
        self._fd: Optional[int] = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Check if /dev/uinput is writable without actually creating device."""
        return os.access('/dev/uinput', os.W_OK)

    def open(self) -> bool:
        """Create the virtual input device. Returns True on success."""
        try:
            fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        except (PermissionError, OSError):
            return False

        # Enable event types
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_X)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_Y)

        # Enable all keycodes we might use
        for code in set(KEYCODES.values()):
            try:
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            except OSError:
                pass

        # Also enable common modifier keys
        for mod in (29, 42, 56, 125):
            try:
                fcntl.ioctl(fd, UI_SET_KEYBIT, mod)
            except OSError:
                pass

        # Device setup
        bus = 0x03  # BUS_USB
        vendor = 0x1234
        product = 0x5678
        version = 1

        device_name = self.name.encode('utf-8')[:80]
        device_name += b'\x00' * (80 - len(device_name))

        # struct uinput_setup { struct input_id id; char name[80]; __u32 ff_effects_max; }
        setup = struct.pack('HHHH', bus, vendor, product, version)
        setup += device_name
        setup += struct.pack('I', 0)

        # UI_DEV_SETUP ioctl = 0x40584555 (on newer kernels) or legacy ABS setup
        # For compatibility we use the legacy approach on older kernels
        try:
            UI_DEV_SETUP = 0x40584555
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
        except OSError:
            # Legacy fallback: write abs setup manually
            pass

        try:
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            return False

        self._fd = fd
        # Small delay for device to appear
        time.sleep(0.2)
        return True

    def close(self):
        if self._fd is not None:
            try:
                fcntl.ioctl(self._fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self._fd)
            self._fd = None

    # ---- Mouse ----
    def move_relative(self, dx: int, dy: int):
        """Generate relative mouse motion."""
        if self._fd is None:
            return
        with self._lock:
            if dx != 0:
                os.write(self._fd, _make_event(EV_REL, REL_X, dx))
            if dy != 0:
                os.write(self._fd, _make_event(EV_REL, REL_Y, dy))
            os.write(self._fd, _syn_report())

    # ---- Keyboard ----
    def key_down(self, key: str):
        """Press a key (by character name or single char)."""
        if self._fd is None:
            return
        code = KEYCODES.get(key)
        if code is None:
            return
        with self._lock:
            os.write(self._fd, _make_event(EV_KEY, code, 1))
            os.write(self._fd, _syn_report())

    def key_up(self, key: str):
        """Release a key."""
        if self._fd is None:
            return
        code = KEYCODES.get(key)
        if code is None:
            return
        with self._lock:
            os.write(self._fd, _make_event(EV_KEY, code, 0))
            os.write(self._fd, _syn_report())

    def key_tap(self, key: str, delay_sec: float = 0.01):
        """Press and release a key."""
        self.key_down(key)
        time.sleep(delay_sec)
        self.key_up(key)

    def type_char(self, ch: str, delay_sec: float = 0.08):
        """Type a single printable character."""
        if ch == ' ':
            self.key_tap(' ', delay_sec)
        elif ch == '\n':
            self.key_tap('ENTER', delay_sec)
        elif ch == '\t':
            self.key_tap('TAB', delay_sec)
        elif ch in KEYCODES:
            self.key_tap(ch, delay_sec)
        elif ch.lower() in KEYCODES:
            # Uppercase letter
            self.key_down('LEFTSHIFT')
            self.key_tap(ch.lower(), delay_sec)
            self.key_up('LEFTSHIFT')
        else:
            # Unsupported character — skip silently
            pass

    def type_text(self, text: str, base_delay: float = 0.08):
        """Type a string with per-character delay."""
        import random
        for ch in text:
            self.type_char(ch, delay_sec=base_delay)
            time.sleep(random.lognormvariate(-2.2, 0.35))

    def shortcut(self, modifier: str, key: str, hold: float = 0.08):
        """Send a keyboard shortcut: hold modifier, tap key, release modifier."""
        self.key_down(modifier)
        time.sleep(0.03)
        self.key_tap(key, delay_sec=hold)
        time.sleep(0.03)
        self.key_up(modifier)
