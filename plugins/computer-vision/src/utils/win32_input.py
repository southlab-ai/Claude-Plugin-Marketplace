"""ctypes wrappers for SendInput — mouse and keyboard input injection."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# --- ctypes struct definitions for SendInput ---

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# Mouse event flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

# Wheel delta constant — one "notch" of scroll
WHEEL_DELTA = 120

# Keyboard event flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# Virtual key codes
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_SPACE = 0x20
VK_UP = 0x26
VK_DOWN = 0x28
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_HOME = 0x24
VK_END = 0x23
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22  # Page Down
VK_INSERT = 0x2D
VK_F1 = 0x70
VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73
VK_F5 = 0x74
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A
VK_F12 = 0x7B

# Key name to VK code mapping
VK_MAP: dict[str, int] = {
    "shift": VK_SHIFT,
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "win": VK_LWIN,
    "meta": VK_LWIN,
    "cmd": VK_LWIN,
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "tab": VK_TAB,
    "escape": VK_ESCAPE,
    "esc": VK_ESCAPE,
    "backspace": VK_BACK,
    "delete": VK_DELETE,
    "del": VK_DELETE,
    "space": VK_SPACE,
    "up": VK_UP,
    "down": VK_DOWN,
    "left": VK_LEFT,
    "right": VK_RIGHT,
    "home": VK_HOME,
    "end": VK_END,
    "pageup": VK_PRIOR,
    "pagedown": VK_NEXT,
    "insert": VK_INSERT,
    "f1": VK_F1, "f2": VK_F2, "f3": VK_F3, "f4": VK_F4,
    "f5": VK_F5, "f6": VK_F6, "f7": VK_F7, "f8": VK_F8,
    "f9": VK_F9, "f10": VK_F10, "f11": VK_F11, "f12": VK_F12,
}

MODIFIER_VKS = {VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN}


def _get_button_flags(button: str) -> tuple[int, int]:
    """Return (down_flag, up_flag) for the given mouse button name."""
    button = button.lower()
    if button == "right":
        return (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    if button == "middle":
        return (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)
    # Default to left
    return (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTunion)]


def send_mouse_click(x: int, y: int, button: str = "left", click_type: str = "single") -> bool:
    """Send a mouse click at normalized coordinates (0-65535 range).

    Args:
        x: Normalized X coordinate (0-65535).
        y: Normalized Y coordinate (0-65535).
        button: "left", "right", or "middle".
        click_type: "single" or "double".

    Returns:
        True if SendInput succeeded.
    """
    button_down, button_up = _get_button_flags(button)
    base_flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

    clicks = 2 if click_type == "double" else 1
    inputs: list[INPUT] = []

    for _ in range(clicks):
        # Move + button down
        inp_down = INPUT(type=INPUT_MOUSE)
        inp_down.union.mi.dx = x
        inp_down.union.mi.dy = y
        inp_down.union.mi.dwFlags = base_flags | MOUSEEVENTF_MOVE | button_down
        inputs.append(inp_down)

        # Button up (same position)
        inp_up = INPUT(type=INPUT_MOUSE)
        inp_up.union.mi.dx = x
        inp_up.union.mi.dy = y
        inp_up.union.mi.dwFlags = base_flags | MOUSEEVENTF_MOVE | button_up
        inputs.append(inp_up)

    sent = _send_inputs(inputs)
    logger.debug("send_mouse_click: sent %d/%d events at (%d, %d)", sent, len(inputs), x, y)
    return sent == len(inputs)


def send_mouse_drag(
    start_x: int, start_y: int, end_x: int, end_y: int,
    button: str = "left", drag_duration_ms: int = 300,
) -> bool:
    """Send a mouse drag from start to end coordinates (0-65535 range).

    Events are sent as separate SendInput calls with time delays between
    phases, and intermediate move events are interpolated along the drag
    path.  This ensures apps with async input pipelines (WebView, UWP,
    Electron, WPF) have time to recognise the gesture as a drag rather
    than an instantaneous click.

    Args:
        start_x: Normalized start X (0-65535).
        start_y: Normalized start Y (0-65535).
        end_x: Normalized end X (0-65535).
        end_y: Normalized end Y (0-65535).
        button: "left", "right", or "middle".
        drag_duration_ms: Total duration of the drag motion in ms (default 300).

    Returns:
        True if all SendInput calls succeeded.
    """
    button_down, button_up = _get_button_flags(button)
    base_flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    total_sent = 0
    total_expected = 0

    def _send_one(dx: int, dy: int, flags: int) -> bool:
        nonlocal total_sent, total_expected
        total_expected += 1
        inp = INPUT(type=INPUT_MOUSE)
        inp.union.mi.dx = dx
        inp.union.mi.dy = dy
        inp.union.mi.dwFlags = flags
        total_sent += _send_inputs([inp])
        return total_sent == total_expected

    # Phase 1: Move cursor to start position
    _send_one(start_x, start_y, base_flags | MOUSEEVENTF_MOVE)
    time.sleep(0.02)  # 20 ms — let cursor settle

    # Phase 2: Button down at start
    _send_one(start_x, start_y, base_flags | MOUSEEVENTF_MOVE | button_down)
    time.sleep(0.05)  # 50 ms — let app register press / begin drag detection

    # Phase 3: Intermediate move events along the drag path
    steps = max(10, drag_duration_ms // 20)  # at least 10 steps
    step_delay = (drag_duration_ms / 1000.0) / steps
    for i in range(1, steps + 1):
        t = i / steps
        ix = int(start_x + (end_x - start_x) * t)
        iy = int(start_y + (end_y - start_y) * t)
        _send_one(ix, iy, base_flags | MOUSEEVENTF_MOVE)
        time.sleep(step_delay)

    # Phase 4: Small settle at destination
    time.sleep(0.02)  # 20 ms

    # Phase 5: Button up at end
    _send_one(end_x, end_y, base_flags | MOUSEEVENTF_MOVE | button_up)

    logger.debug(
        "send_mouse_drag: sent %d/%d events over %dms (%d steps)",
        total_sent, total_expected, drag_duration_ms, steps,
    )
    return total_sent == total_expected


def type_unicode_string(text: str) -> bool:
    """Type a string using KEYEVENTF_UNICODE, batched into a single SendInput call.

    Args:
        text: The text to type. Each character is sent as a Unicode keystroke.

    Returns:
        True if SendInput succeeded.
    """
    if not text:
        return True

    inputs: list[INPUT] = []

    for char in text:
        code = ord(char)

        # Key down
        inp_down = INPUT(type=INPUT_KEYBOARD)
        inp_down.union.ki.wVk = 0
        inp_down.union.ki.wScan = code
        inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
        inputs.append(inp_down)

        # Key up
        inp_up = INPUT(type=INPUT_KEYBOARD)
        inp_up.union.ki.wVk = 0
        inp_up.union.ki.wScan = code
        inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inputs.append(inp_up)

    sent = _send_inputs(inputs)
    logger.debug("type_unicode_string: sent %d/%d events for %d chars", sent, len(inputs), len(text))
    return sent == len(inputs)


def send_key_combo(keys: str) -> bool:
    """Send a key combination (e.g., "ctrl+shift+s", "alt+tab").

    Parses the key string, maps to VK codes, and sends modifier-down + key-down
    + key-up + modifier-up via SendInput.

    Args:
        keys: Key combination string, parts separated by "+".

    Returns:
        True if SendInput succeeded.
    """
    parts = [p.strip().lower() for p in keys.split("+")]
    modifiers: list[int] = []
    regular_keys: list[int] = []

    for part in parts:
        vk = VK_MAP.get(part)
        if vk is None:
            # Single character: use its virtual key code (uppercase ASCII)
            if len(part) == 1 and part.isascii():
                vk = ord(part.upper())
            else:
                logger.warning("Unknown key name: %s", part)
                return False

        if vk in MODIFIER_VKS:
            modifiers.append(vk)
        else:
            regular_keys.append(vk)

    inputs: list[INPUT] = []

    # Modifiers down
    for vk in modifiers:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = 0
        inputs.append(inp)

    # Regular keys down then up
    for vk in regular_keys:
        inp_down = INPUT(type=INPUT_KEYBOARD)
        inp_down.union.ki.wVk = vk
        inp_down.union.ki.dwFlags = 0
        inputs.append(inp_down)

        inp_up = INPUT(type=INPUT_KEYBOARD)
        inp_up.union.ki.wVk = vk
        inp_up.union.ki.dwFlags = KEYEVENTF_KEYUP
        inputs.append(inp_up)

    # Modifiers up (reverse order)
    for vk in reversed(modifiers):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP
        inputs.append(inp)

    sent = _send_inputs(inputs)
    logger.debug("send_key_combo: sent %d/%d events for '%s'", sent, len(inputs), keys)
    return sent == len(inputs)


def send_mouse_scroll(x: int, y: int, direction: str, amount: int = 3) -> bool:
    """Send mouse scroll at normalized coordinates (0-65535 range).

    Args:
        x: Normalized X coordinate (0-65535).
        y: Normalized Y coordinate (0-65535).
        direction: "up", "down", "left", or "right".
        amount: Number of scroll notches (each = WHEEL_DELTA = 120).

    Returns:
        True if SendInput succeeded.
    """
    base_flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | MOUSEEVENTF_MOVE

    if direction in ("up", "down"):
        wheel_flag = MOUSEEVENTF_WHEEL
        # Positive = scroll up, negative = scroll down
        delta = amount * WHEEL_DELTA if direction == "up" else -(amount * WHEEL_DELTA)
    else:
        wheel_flag = MOUSEEVENTF_HWHEEL
        # Positive = scroll right, negative = scroll left
        delta = amount * WHEEL_DELTA if direction == "right" else -(amount * WHEEL_DELTA)

    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi.dx = x
    inp.union.mi.dy = y
    inp.union.mi.mouseData = delta
    inp.union.mi.dwFlags = base_flags | wheel_flag

    sent = _send_inputs([inp])
    logger.debug("send_mouse_scroll: sent %d/1 events at (%d, %d) direction=%s amount=%d", sent, x, y, direction, amount)
    return sent == 1


def _send_inputs(inputs: list[INPUT]) -> int:
    """Send a batch of INPUT structures via SendInput."""
    arr = (INPUT * len(inputs))(*inputs)
    return ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# PostMessage-based input (background mode — no cursor move, no focus steal)
# ---------------------------------------------------------------------------

# Window message constants
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDBLCLK = 0x0206
WM_MBUTTONDBLCLK = 0x0209
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_SYSCOMMAND = 0x0112

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010


def _makelparam(lo: int, hi: int) -> int:
    """Pack two 16-bit values into a single LPARAM."""
    return (hi << 16) | (lo & 0xFFFF)


def _post_button_msgs(button: str) -> tuple[int, int, int, int]:
    """Return (down_msg, up_msg, dblclk_msg, wparam_flag) for a mouse button."""
    if button == "right":
        return (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK, MK_RBUTTON)
    if button == "middle":
        return (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK, MK_MBUTTON)
    return (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK, MK_LBUTTON)


def post_mouse_click(
    hwnd: int, x: int, y: int, button: str = "left", click_type: str = "single"
) -> bool:
    """Send a mouse click to *hwnd* via PostMessage — no cursor move, no focus steal.

    Args:
        hwnd: Target window handle.
        x: X in client coordinates of *hwnd*.
        y: Y in client coordinates of *hwnd*.
        button: "left", "right", or "middle".
        click_type: "single" or "double".

    Returns:
        True if all PostMessage calls succeeded.
    """
    down_msg, up_msg, dbl_msg, wp_flag = _post_button_msgs(button)
    lp = _makelparam(x, y)
    user32 = ctypes.windll.user32

    if click_type == "double":
        # WM_LBUTTONDBLCLK requires CS_DBLCLKS on the window class,
        # so send down+up+dblclk+up for maximum compatibility.
        ok = (
            user32.PostMessageW(hwnd, down_msg, wp_flag, lp)
            and user32.PostMessageW(hwnd, up_msg, 0, lp)
            and user32.PostMessageW(hwnd, dbl_msg, wp_flag, lp)
            and user32.PostMessageW(hwnd, up_msg, 0, lp)
        )
    else:
        ok = (
            user32.PostMessageW(hwnd, down_msg, wp_flag, lp)
            and user32.PostMessageW(hwnd, up_msg, 0, lp)
        )

    logger.debug("post_mouse_click: hwnd=%d pos=(%d,%d) button=%s ok=%s", hwnd, x, y, button, ok)
    return bool(ok)


def post_type_string(hwnd: int, text: str) -> bool:
    """Type a string into *hwnd* via WM_CHAR messages — no focus required.

    Args:
        hwnd: Target window handle.
        text: The text to type.

    Returns:
        True if all PostMessage calls succeeded.
    """
    user32 = ctypes.windll.user32
    for ch in text:
        if not user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0):
            logger.warning("post_type_string: PostMessage WM_CHAR failed for %r", ch)
            return False
    logger.debug("post_type_string: hwnd=%d chars=%d ok=True", hwnd, len(text))
    return True


def post_key_combo(hwnd: int, keys: str) -> bool:
    """Send a key combination to *hwnd* via PostMessage — no focus required.

    Args:
        hwnd: Target window handle.
        keys: Key combination string (e.g. "ctrl+s", "alt+f4").

    Returns:
        True if all PostMessage calls succeeded.
    """
    parts = [p.strip().lower() for p in keys.split("+")]
    modifiers: list[int] = []
    regular_keys: list[int] = []

    for part in parts:
        vk = VK_MAP.get(part)
        if vk is None:
            if len(part) == 1 and part.isascii():
                vk = ord(part.upper())
            else:
                logger.warning("post_key_combo: unknown key %r", part)
                return False
        if vk in MODIFIER_VKS:
            modifiers.append(vk)
        else:
            regular_keys.append(vk)

    user32 = ctypes.windll.user32
    ok = True

    # Modifiers down
    for vk in modifiers:
        ok = ok and bool(user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0))

    # Regular keys down + up
    for vk in regular_keys:
        ok = ok and bool(user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0))
        ok = ok and bool(user32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000001))

    # Modifiers up (reverse)
    for vk in reversed(modifiers):
        ok = ok and bool(user32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000001))

    logger.debug("post_key_combo: hwnd=%d keys=%r ok=%s", hwnd, keys, ok)
    return ok
