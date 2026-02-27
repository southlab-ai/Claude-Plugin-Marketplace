// ==========================================================================
// message_injector.cpp - Safe Windows message injection implementation
// ==========================================================================

#include "message_injector.h"
#include "hooks/window_hooks.h"
#include <unordered_set>

namespace sandbox {

// ---------------------------------------------------------------------------
// Message allowlist
// ---------------------------------------------------------------------------

static const std::unordered_set<UINT> ALLOWED_MESSAGES = {
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_CHAR,
    WM_SETTEXT,
    WM_COMMAND,
    BM_CLICK,
    WM_MOUSEMOVE,
    WM_SETFOCUS,
};

// Modifier key virtual key codes
static constexpr BYTE MOD_SHIFT_BIT = 1;
static constexpr BYTE MOD_CTRL_BIT  = 2;
static constexpr BYTE MOD_ALT_BIT   = 4;

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

MessageInjector& MessageInjector::instance() {
    static MessageInjector s_instance;
    return s_instance;
}

MessageInjector::MessageInjector() {
    InitializeCriticalSectionAndSpinCount(&m_cs, 4000);
}

MessageInjector::~MessageInjector() {
    DeleteCriticalSection(&m_cs);
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

bool MessageInjector::is_message_allowed(UINT msg) const {
    return ALLOWED_MESSAGES.count(msg) > 0;
}

bool MessageInjector::validate_hwnd(HWND hwnd) const {
    if (!hwnd) return false;
    // Must exist in the shadow tree (known window)
    if (!window_hooks::hwnd_exists(hwnd)) {
        // Fallback: check if the window actually exists at the OS level
        // (it may have been created before our hooks were installed)
        return IsWindow(hwnd) != FALSE;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Helper: build lParam for mouse messages
// ---------------------------------------------------------------------------

static LPARAM make_mouse_lparam(int x, int y, HWND hwnd) {
    // Convert screen coordinates to client coordinates
    POINT pt = {x, y};
    ScreenToClient(hwnd, &pt);
    return MAKELPARAM(static_cast<WORD>(pt.x), static_cast<WORD>(pt.y));
}

// Helper: build lParam for WM_KEYDOWN/WM_KEYUP
static LPARAM make_key_lparam(UINT vk, bool keyup) {
    UINT scancode = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC);
    LPARAM lp = 1;                           // repeat count = 1
    lp |= (static_cast<LPARAM>(scancode) << 16);  // scan code
    if (keyup) {
        lp |= (1LL << 30);  // previous key state
        lp |= (1LL << 31);  // transition state
    }
    return lp;
}

// ---------------------------------------------------------------------------
// Click injection
// ---------------------------------------------------------------------------

InjectResult MessageInjector::inject_click(HWND hwnd, int x, int y, int button) {
    EnterCriticalSection(&m_cs);

    InjectResult result = {false, ""};

    if (!validate_hwnd(hwnd)) {
        result.error = "Invalid or unknown HWND";
        LeaveCriticalSection(&m_cs);
        return result;
    }

    // Position the cursor at the target location
    SetCursorPos(x, y);

    LPARAM lp = make_mouse_lparam(x, y, hwnd);

    UINT msg_down, msg_up;
    if (button == 1) {
        msg_down = WM_RBUTTONDOWN;
        msg_up   = WM_RBUTTONUP;
    } else {
        msg_down = WM_LBUTTONDOWN;
        msg_up   = WM_LBUTTONUP;
    }

    // Use SendMessage for focused interaction
    // SetForegroundWindow to ensure the window is active
    SetForegroundWindow(hwnd);

    // Small delay is handled by the caller if needed; we inject synchronously
    SendMessageW(hwnd, msg_down, (button == 1) ? MK_RBUTTON : MK_LBUTTON, lp);
    SendMessageW(hwnd, msg_up, 0, lp);

    result.success = true;
    LeaveCriticalSection(&m_cs);
    return result;
}

// ---------------------------------------------------------------------------
// Key injection
// ---------------------------------------------------------------------------

InjectResult MessageInjector::inject_keys(HWND hwnd, const std::wstring& keys, uint32_t modifiers) {
    EnterCriticalSection(&m_cs);

    InjectResult result = {false, ""};

    if (!validate_hwnd(hwnd)) {
        result.error = "Invalid or unknown HWND";
        LeaveCriticalSection(&m_cs);
        return result;
    }

    // Focus the window
    SetForegroundWindow(hwnd);
    SendMessageW(hwnd, WM_SETFOCUS, 0, 0);

    // Press modifier keys down
    if (modifiers & MOD_SHIFT_BIT) {
        PostMessageW(hwnd, WM_KEYDOWN, VK_SHIFT, make_key_lparam(VK_SHIFT, false));
    }
    if (modifiers & MOD_CTRL_BIT) {
        PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, make_key_lparam(VK_CONTROL, false));
    }
    if (modifiers & MOD_ALT_BIT) {
        PostMessageW(hwnd, WM_KEYDOWN, VK_MENU, make_key_lparam(VK_MENU, false));
    }

    // Send each character
    for (wchar_t ch : keys) {
        // WM_KEYDOWN with the virtual key
        SHORT vk_result = VkKeyScanW(ch);
        if (vk_result != -1) {
            BYTE vk = LOBYTE(vk_result);
            PostMessageW(hwnd, WM_KEYDOWN, vk, make_key_lparam(vk, false));
            PostMessageW(hwnd, WM_CHAR, static_cast<WPARAM>(ch), make_key_lparam(vk, false));
            PostMessageW(hwnd, WM_KEYUP, vk, make_key_lparam(vk, true));
        } else {
            // Unicode character without a VK mapping — send as WM_CHAR directly
            PostMessageW(hwnd, WM_CHAR, static_cast<WPARAM>(ch), 0);
        }
    }

    // Release modifier keys (in reverse order)
    if (modifiers & MOD_ALT_BIT) {
        PostMessageW(hwnd, WM_KEYUP, VK_MENU, make_key_lparam(VK_MENU, true));
    }
    if (modifiers & MOD_CTRL_BIT) {
        PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, make_key_lparam(VK_CONTROL, true));
    }
    if (modifiers & MOD_SHIFT_BIT) {
        PostMessageW(hwnd, WM_KEYUP, VK_SHIFT, make_key_lparam(VK_SHIFT, true));
    }

    result.success = true;
    LeaveCriticalSection(&m_cs);
    return result;
}

// ---------------------------------------------------------------------------
// Raw message injection
// ---------------------------------------------------------------------------

InjectResult MessageInjector::inject_message(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    EnterCriticalSection(&m_cs);

    InjectResult result = {false, ""};

    if (!validate_hwnd(hwnd)) {
        result.error = "Invalid or unknown HWND";
        LeaveCriticalSection(&m_cs);
        return result;
    }

    if (!is_message_allowed(msg)) {
        result.error = "Message not in allowlist: " + std::to_string(msg);
        LeaveCriticalSection(&m_cs);
        return result;
    }

    SendMessageW(hwnd, msg, wParam, lParam);

    result.success = true;
    LeaveCriticalSection(&m_cs);
    return result;
}

// ---------------------------------------------------------------------------
// Set text on edit control
// ---------------------------------------------------------------------------

InjectResult MessageInjector::inject_set_text(HWND hwnd, const std::wstring& text) {
    EnterCriticalSection(&m_cs);

    InjectResult result = {false, ""};

    if (!validate_hwnd(hwnd)) {
        result.error = "Invalid or unknown HWND";
        LeaveCriticalSection(&m_cs);
        return result;
    }

    SendMessageW(hwnd, WM_SETTEXT, 0, reinterpret_cast<LPARAM>(text.c_str()));

    result.success = true;
    LeaveCriticalSection(&m_cs);
    return result;
}

// ---------------------------------------------------------------------------
// Button click
// ---------------------------------------------------------------------------

InjectResult MessageInjector::inject_button_click(HWND hwnd) {
    EnterCriticalSection(&m_cs);

    InjectResult result = {false, ""};

    if (!validate_hwnd(hwnd)) {
        result.error = "Invalid or unknown HWND";
        LeaveCriticalSection(&m_cs);
        return result;
    }

    SendMessageW(hwnd, BM_CLICK, 0, 0);

    result.success = true;
    LeaveCriticalSection(&m_cs);
    return result;
}

// ---------------------------------------------------------------------------
// Mouse move
// ---------------------------------------------------------------------------

InjectResult MessageInjector::inject_mouse_move(HWND hwnd, int x, int y) {
    EnterCriticalSection(&m_cs);

    InjectResult result = {false, ""};

    if (!validate_hwnd(hwnd)) {
        result.error = "Invalid or unknown HWND";
        LeaveCriticalSection(&m_cs);
        return result;
    }

    SetCursorPos(x, y);

    LPARAM lp = make_mouse_lparam(x, y, hwnd);
    PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp);

    result.success = true;
    LeaveCriticalSection(&m_cs);
    return result;
}

} // namespace sandbox
