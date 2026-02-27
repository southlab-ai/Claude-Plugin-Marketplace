// ==========================================================================
// hooks/window_hooks.h - Window management API hooks
// ==========================================================================
// Intercepts window lifecycle and geometry APIs to maintain a shadow tree:
//   - CreateWindowExW, DestroyWindow
//   - SetWindowPos, ShowWindow, MoveWindow
//
// The shadow tree (std::unordered_map<HWND, WindowNode>) tracks parent/child
// relationships, class name, title, rect, z-order, and visibility.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_WINDOW_HOOKS_H
#define SANDBOX_SHIM_WINDOW_HOOKS_H

#include "hook_engine.h"
#include <windows.h>
#include <string>
#include <vector>
#include <unordered_map>

namespace sandbox {

// Represents a single window in the shadow tree
struct WindowNode {
    HWND                hwnd;
    HWND                parent_hwnd;
    std::wstring        class_name;
    std::wstring        title;
    RECT                rect;           // Screen coordinates
    int                 z_order;
    bool                visible;
    std::vector<HWND>   children_hwnds;
};

namespace window_hooks {

// Register window hooks with the engine
void register_hooks(HookEngine& engine);

// Query the shadow tree (thread-safe)
// Returns a snapshot of all tracked windows
std::unordered_map<HWND, WindowNode> get_window_tree();

// Check if an HWND exists in the shadow tree
bool hwnd_exists(HWND hwnd);

// Get a single window node (returns false if not found)
bool get_window_node(HWND hwnd, WindowNode& out);

} // namespace window_hooks
} // namespace sandbox

#endif // SANDBOX_SHIM_WINDOW_HOOKS_H
