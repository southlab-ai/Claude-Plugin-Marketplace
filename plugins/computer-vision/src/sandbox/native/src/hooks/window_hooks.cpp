// ==========================================================================
// hooks/window_hooks.cpp - Window management hook implementations
// ==========================================================================

#include "hooks/window_hooks.h"
#include "scene_graph.h"
#include <windows.h>
#include <algorithm>

namespace sandbox {
namespace window_hooks {

// ---------------------------------------------------------------------------
// Shadow tree state (protected by SRWLOCK)
// ---------------------------------------------------------------------------

static SRWLOCK s_tree_lock = SRWLOCK_INIT;
static std::unordered_map<HWND, WindowNode> s_tree;
static int s_next_z_order = 0;

// ---------------------------------------------------------------------------
// Trampoline pointers
// ---------------------------------------------------------------------------

static decltype(&CreateWindowExW) Real_CreateWindowExW = CreateWindowExW;
static decltype(&DestroyWindow)   Real_DestroyWindow   = DestroyWindow;
static decltype(&SetWindowPos)    Real_SetWindowPos    = SetWindowPos;
static decltype(&ShowWindow)      Real_ShowWindow      = ShowWindow;
static decltype(&MoveWindow)      Real_MoveWindow      = MoveWindow;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static std::wstring safe_get_class_name(HWND hwnd) {
    wchar_t buf[256] = {};
    int len = GetClassNameW(hwnd, buf, 256);
    return (len > 0) ? std::wstring(buf, len) : L"";
}

static std::wstring safe_get_window_title(HWND hwnd) {
    int len = GetWindowTextLengthW(hwnd);
    if (len <= 0) return L"";
    // Cap title length
    if (len > 4096) len = 4096;
    std::wstring title(len + 1, L'\0');
    int got = GetWindowTextW(hwnd, &title[0], len + 1);
    title.resize(got > 0 ? got : 0);
    return title;
}

static RECT safe_get_window_rect(HWND hwnd) {
    RECT r = {};
    GetWindowRect(hwnd, &r);
    return r;
}

// Update a node in the shadow tree (caller must hold exclusive lock)
static void update_node_unlocked(HWND hwnd) {
    auto it = s_tree.find(hwnd);
    if (it == s_tree.end()) return;

    auto& node = it->second;
    node.title   = safe_get_window_title(hwnd);
    node.rect    = safe_get_window_rect(hwnd);
    node.visible = (IsWindowVisible(hwnd) != FALSE);
}

// Remove a child HWND from its parent's children list
static void remove_child_from_parent(HWND parent, HWND child) {
    auto it = s_tree.find(parent);
    if (it != s_tree.end()) {
        auto& children = it->second.children_hwnds;
        children.erase(
            std::remove(children.begin(), children.end(), child),
            children.end());
    }
}

// Add a child HWND to its parent's children list
static void add_child_to_parent(HWND parent, HWND child) {
    auto it = s_tree.find(parent);
    if (it != s_tree.end()) {
        auto& children = it->second.children_hwnds;
        // Avoid duplicates
        if (std::find(children.begin(), children.end(), child) == children.end()) {
            children.push_back(child);
        }
    }
}

// Notify scene graph that the window tree changed
static void notify_scene_graph() {
    SceneGraph::instance().bump_version();
}

// ---------------------------------------------------------------------------
// Detour callbacks
// ---------------------------------------------------------------------------

static HWND WINAPI Detour_CreateWindowExW(
    DWORD     dwExStyle,
    LPCWSTR   lpClassName,
    LPCWSTR   lpWindowName,
    DWORD     dwStyle,
    int       X,
    int       Y,
    int       nWidth,
    int       nHeight,
    HWND      hWndParent,
    HMENU     hMenu,
    HINSTANCE hInstance,
    LPVOID    lpParam
) {
    // Call the real function first
    HWND hwnd = Real_CreateWindowExW(
        dwExStyle, lpClassName, lpWindowName, dwStyle,
        X, Y, nWidth, nHeight, hWndParent, hMenu, hInstance, lpParam);

    if (hwnd) {
        try {
            WindowNode node;
            node.hwnd        = hwnd;
            node.parent_hwnd = hWndParent;
            node.class_name  = safe_get_class_name(hwnd);
            node.title       = lpWindowName ? lpWindowName : L"";
            node.rect        = safe_get_window_rect(hwnd);
            node.z_order     = s_next_z_order++;
            node.visible     = (dwStyle & WS_VISIBLE) != 0;

            AcquireSRWLockExclusive(&s_tree_lock);
            s_tree[hwnd] = std::move(node);
            if (hWndParent) {
                add_child_to_parent(hWndParent, hwnd);
            }
            ReleaseSRWLockExclusive(&s_tree_lock);

            notify_scene_graph();
        }
        catch (...) {
            // Swallow
        }
    }

    return hwnd;
}

static BOOL WINAPI Detour_DestroyWindow(HWND hWnd) {
    try {
        AcquireSRWLockExclusive(&s_tree_lock);
        auto it = s_tree.find(hWnd);
        if (it != s_tree.end()) {
            // Remove from parent
            if (it->second.parent_hwnd) {
                remove_child_from_parent(it->second.parent_hwnd, hWnd);
            }
            // Remove all children references that point to this as parent
            for (HWND child : it->second.children_hwnds) {
                auto cit = s_tree.find(child);
                if (cit != s_tree.end()) {
                    cit->second.parent_hwnd = nullptr;
                }
            }
            s_tree.erase(it);
        }
        ReleaseSRWLockExclusive(&s_tree_lock);

        notify_scene_graph();
    }
    catch (...) {
        // Swallow
    }

    return Real_DestroyWindow(hWnd);
}

static BOOL WINAPI Detour_SetWindowPos(
    HWND hWnd,
    HWND hWndInsertAfter,
    int  X,
    int  Y,
    int  cx,
    int  cy,
    UINT uFlags
) {
    BOOL result = Real_SetWindowPos(hWnd, hWndInsertAfter, X, Y, cx, cy, uFlags);

    if (result) {
        try {
            AcquireSRWLockExclusive(&s_tree_lock);
            auto it = s_tree.find(hWnd);
            if (it != s_tree.end()) {
                it->second.rect = safe_get_window_rect(hWnd);
                it->second.visible = (IsWindowVisible(hWnd) != FALSE);
                // Update z-order if positioning changed
                if (!(uFlags & SWP_NOZORDER)) {
                    it->second.z_order = s_next_z_order++;
                }
            }
            ReleaseSRWLockExclusive(&s_tree_lock);

            notify_scene_graph();
        }
        catch (...) {
            // Swallow
        }
    }

    return result;
}

static BOOL WINAPI Detour_ShowWindow(HWND hWnd, int nCmdShow) {
    BOOL result = Real_ShowWindow(hWnd, nCmdShow);

    try {
        AcquireSRWLockExclusive(&s_tree_lock);
        auto it = s_tree.find(hWnd);
        if (it != s_tree.end()) {
            it->second.visible = (IsWindowVisible(hWnd) != FALSE);
            it->second.rect    = safe_get_window_rect(hWnd);
        }
        ReleaseSRWLockExclusive(&s_tree_lock);

        notify_scene_graph();
    }
    catch (...) {
        // Swallow
    }

    return result;
}

static BOOL WINAPI Detour_MoveWindow(
    HWND hWnd,
    int  X,
    int  Y,
    int  nWidth,
    int  nHeight,
    BOOL bRepaint
) {
    BOOL result = Real_MoveWindow(hWnd, X, Y, nWidth, nHeight, bRepaint);

    if (result) {
        try {
            AcquireSRWLockExclusive(&s_tree_lock);
            auto it = s_tree.find(hWnd);
            if (it != s_tree.end()) {
                it->second.rect = safe_get_window_rect(hWnd);
            }
            ReleaseSRWLockExclusive(&s_tree_lock);

            notify_scene_graph();
        }
        catch (...) {
            // Swallow
        }
    }

    return result;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

void register_hooks(HookEngine& engine) {
    engine.register_hooks({
        {"CreateWindowExW", reinterpret_cast<PVOID*>(&Real_CreateWindowExW), reinterpret_cast<PVOID>(Detour_CreateWindowExW)},
        {"DestroyWindow",   reinterpret_cast<PVOID*>(&Real_DestroyWindow),   reinterpret_cast<PVOID>(Detour_DestroyWindow)},
        {"SetWindowPos",    reinterpret_cast<PVOID*>(&Real_SetWindowPos),    reinterpret_cast<PVOID>(Detour_SetWindowPos)},
        {"ShowWindow",      reinterpret_cast<PVOID*>(&Real_ShowWindow),      reinterpret_cast<PVOID>(Detour_ShowWindow)},
        {"MoveWindow",      reinterpret_cast<PVOID*>(&Real_MoveWindow),      reinterpret_cast<PVOID>(Detour_MoveWindow)},
    });
}

// ---------------------------------------------------------------------------
// Query API (thread-safe)
// ---------------------------------------------------------------------------

std::unordered_map<HWND, WindowNode> get_window_tree() {
    AcquireSRWLockShared(&s_tree_lock);
    auto copy = s_tree;
    ReleaseSRWLockShared(&s_tree_lock);
    return copy;
}

bool hwnd_exists(HWND hwnd) {
    AcquireSRWLockShared(&s_tree_lock);
    bool found = (s_tree.find(hwnd) != s_tree.end());
    ReleaseSRWLockShared(&s_tree_lock);
    return found;
}

bool get_window_node(HWND hwnd, WindowNode& out) {
    AcquireSRWLockShared(&s_tree_lock);
    auto it = s_tree.find(hwnd);
    bool found = (it != s_tree.end());
    if (found) out = it->second;
    ReleaseSRWLockShared(&s_tree_lock);
    return found;
}

} // namespace window_hooks
} // namespace sandbox
