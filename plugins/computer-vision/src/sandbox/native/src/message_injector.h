// ==========================================================================
// message_injector.h - Safe Windows message injection
// ==========================================================================
// Provides controlled input injection into target windows:
//   - Mouse clicks (left/right, down/up) with SetCursorPos positioning
//   - Keyboard input with modifier support (Ctrl, Alt, Shift)
//   - Text input via WM_SETTEXT / WM_CHAR sequences
//   - Button clicks via BM_CLICK
//
// SECURITY: Only allowlisted WM_ messages are accepted. All target HWNDs
// must exist in the window shadow tree.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_MESSAGE_INJECTOR_H
#define SANDBOX_SHIM_MESSAGE_INJECTOR_H

#include <windows.h>
#include <string>
#include <cstdint>

namespace sandbox {

// Result of an injection operation
struct InjectResult {
    bool        success;
    std::string error;     // Empty on success
};

class MessageInjector {
public:
    static MessageInjector& instance();

    // Non-copyable
    MessageInjector(const MessageInjector&)            = delete;
    MessageInjector& operator=(const MessageInjector&) = delete;

    // Click at screen coordinates (x, y) on a specific window.
    // button: 0 = left, 1 = right
    InjectResult inject_click(HWND hwnd, int x, int y, int button);

    // Type a sequence of keys with optional modifiers.
    // keys: the character string to type
    // modifiers: bitmask - 1=Shift, 2=Ctrl, 4=Alt
    InjectResult inject_keys(HWND hwnd, const std::wstring& keys, uint32_t modifiers);

    // Send a raw message from the allowlist.
    InjectResult inject_message(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam);

    // Set text on an edit control
    InjectResult inject_set_text(HWND hwnd, const std::wstring& text);

    // Click a button control
    InjectResult inject_button_click(HWND hwnd);

    // Move mouse to screen coordinates
    InjectResult inject_mouse_move(HWND hwnd, int x, int y);

private:
    MessageInjector();
    ~MessageInjector();

    // Validate that the message is in the allowlist
    bool is_message_allowed(UINT msg) const;

    // Validate that the HWND exists in the shadow tree
    bool validate_hwnd(HWND hwnd) const;

    CRITICAL_SECTION m_cs;
};

} // namespace sandbox

#endif // SANDBOX_SHIM_MESSAGE_INJECTOR_H
