// ==========================================================================
// hooks/gdi_hooks.cpp - GDI text and blit API hook implementations
// ==========================================================================

#include "hooks/gdi_hooks.h"
#include "scene_graph.h"
#include <windows.h>
#include <cstring>
#include <algorithm>
#include <string>

// Maximum text length we capture per call (64 KB of wchar_t = 32K chars)
static constexpr size_t MAX_TEXT_CHARS = 32768;

namespace sandbox {
namespace gdi_hooks {

// ---------------------------------------------------------------------------
// Trampoline pointers — these hold the original function addresses
// ---------------------------------------------------------------------------

static decltype(&DrawTextW)    Real_DrawTextW    = DrawTextW;
static decltype(&DrawTextExW)  Real_DrawTextExW  = DrawTextExW;
static decltype(&TextOutW)     Real_TextOutW     = TextOutW;
static decltype(&ExtTextOutW)  Real_ExtTextOutW  = ExtTextOutW;
static decltype(&BitBlt)       Real_BitBlt       = BitBlt;
static decltype(&StretchBlt)   Real_StretchBlt   = StretchBlt;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Safely extract font face name from a device context
static std::wstring get_font_face(HDC hdc) {
    wchar_t face[LF_FACESIZE] = {};
    HGDIOBJ font = GetCurrentObject(hdc, OBJ_FONT);
    if (font) {
        LOGFONTW lf = {};
        if (GetObjectW(font, sizeof(lf), &lf) > 0) {
            return std::wstring(lf.lfFaceName);
        }
    }
    // Fallback: use GetTextFace
    int len = GetTextFaceW(hdc, LF_FACESIZE, face);
    if (len > 0) {
        return std::wstring(face, static_cast<size_t>(len - 1)); // exclude null
    }
    return L"";
}

// Get the HWND associated with a device context
static HWND get_hwnd_from_dc(HDC hdc) {
    return WindowFromDC(hdc);
}

// Build a TextElement and push it to the scene graph
static void push_text_element(
    HDC hdc,
    const wchar_t* text,
    int text_len,
    const RECT* rect,
    const char* source_api
) {
    if (!text || text_len == 0) return;

    // Cap text length
    size_t safe_len = (text_len < 0)
        ? wcsnlen(text, MAX_TEXT_CHARS)
        : static_cast<size_t>((std::min)(static_cast<size_t>(text_len), MAX_TEXT_CHARS));

    if (safe_len == 0) return;

    // Convert text to UTF-8
    std::wstring wtext(text, safe_len);

    // Get font info
    std::wstring font_face = get_font_face(hdc);

    // Get HWND
    HWND hwnd = get_hwnd_from_dc(hdc);

    // Build rect info
    SceneGraph::Rect sg_rect = {};
    if (rect) {
        sg_rect.x = rect->left;
        sg_rect.y = rect->top;
        sg_rect.w = rect->right - rect->left;
        sg_rect.h = rect->bottom - rect->top;
    }

    TextElement elem;
    elem.text       = std::move(wtext);
    elem.font       = std::move(font_face);
    elem.rect       = sg_rect;
    elem.hwnd       = hwnd;
    elem.source_api = source_api;
    elem.timestamp_ms = GetTickCount64();

    SceneGraph::instance().add_text_element(std::move(elem));
}

// ---------------------------------------------------------------------------
// Detour callbacks (SEH-protected)
// ---------------------------------------------------------------------------

static int WINAPI Detour_DrawTextW(
    HDC     hdc,
    LPCWSTR lpchText,
    int     cchText,
    LPRECT  lprc,
    UINT    format
) {
    __try {
        push_text_element(hdc, lpchText, cchText, lprc, "gdi_DrawTextW");
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow exception — never crash the host process
    }
    return Real_DrawTextW(hdc, lpchText, cchText, lprc, format);
}

static int WINAPI Detour_DrawTextExW(
    HDC              hdc,
    LPWSTR           lpchText,
    int              cchText,
    LPRECT           lprc,
    UINT             format,
    LPDRAWTEXTPARAMS lpdtp
) {
    __try {
        push_text_element(hdc, lpchText, cchText, lprc, "gdi_DrawTextExW");
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }
    return Real_DrawTextExW(hdc, lpchText, cchText, lprc, format, lpdtp);
}

static BOOL WINAPI Detour_TextOutW(
    HDC     hdc,
    int     x,
    int     y,
    LPCWSTR lpString,
    int     c
) {
    __try {
        // TextOutW doesn't provide a rect; we synthesize one using text metrics
        RECT rect = {};
        if (lpString && c > 0) {
            SIZE sz = {};
            if (GetTextExtentPoint32W(hdc, lpString, c, &sz)) {
                rect.left   = x;
                rect.top    = y;
                rect.right  = x + sz.cx;
                rect.bottom = y + sz.cy;
            }
        }
        push_text_element(hdc, lpString, c, &rect, "gdi_TextOutW");
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }
    return Real_TextOutW(hdc, x, y, lpString, c);
}

static BOOL WINAPI Detour_ExtTextOutW(
    HDC        hdc,
    int        x,
    int        y,
    UINT       options,
    const RECT* lprect,
    LPCWSTR    lpString,
    UINT       c,
    const INT* lpDx
) {
    __try {
        RECT rect = {};
        if (lprect) {
            rect = *lprect;
        } else if (lpString && c > 0) {
            SIZE sz = {};
            if (GetTextExtentPoint32W(hdc, lpString, static_cast<int>(c), &sz)) {
                rect.left   = x;
                rect.top    = y;
                rect.right  = x + sz.cx;
                rect.bottom = y + sz.cy;
            }
        }
        push_text_element(hdc, lpString, static_cast<int>(c), &rect, "gdi_ExtTextOutW");
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }
    return Real_ExtTextOutW(hdc, x, y, options, lprect, lpString, c, lpDx);
}

static BOOL WINAPI Detour_BitBlt(
    HDC   hdc,
    int   x,
    int   y,
    int   cx,
    int   cy,
    HDC   hdcSrc,
    int   x1,
    int   y1,
    DWORD rop
) {
    // BitBlt tracking: we note the blit region for the scene graph.
    // This is primarily used to detect content invalidation regions.
    __try {
        HWND hwnd = get_hwnd_from_dc(hdc);
        if (hwnd) {
            SceneGraph::Rect blit_rect = {x, y, cx, cy};
            SceneGraph::instance().note_blit_region(hwnd, blit_rect);
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }
    return Real_BitBlt(hdc, x, y, cx, cy, hdcSrc, x1, y1, rop);
}

static BOOL WINAPI Detour_StretchBlt(
    HDC   hdcDest,
    int   xDest,
    int   yDest,
    int   wDest,
    int   hDest,
    HDC   hdcSrc,
    int   xSrc,
    int   ySrc,
    int   wSrc,
    int   hSrc,
    DWORD rop
) {
    __try {
        HWND hwnd = get_hwnd_from_dc(hdcDest);
        if (hwnd) {
            SceneGraph::Rect blit_rect = {xDest, yDest, wDest, hDest};
            SceneGraph::instance().note_blit_region(hwnd, blit_rect);
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }
    return Real_StretchBlt(hdcDest, xDest, yDest, wDest, hDest,
                           hdcSrc, xSrc, ySrc, wSrc, hSrc, rop);
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

void register_hooks(HookEngine& engine) {
    engine.register_hooks({
        {"DrawTextW",    reinterpret_cast<PVOID*>(&Real_DrawTextW),    reinterpret_cast<PVOID>(Detour_DrawTextW)},
        {"DrawTextExW",  reinterpret_cast<PVOID*>(&Real_DrawTextExW),  reinterpret_cast<PVOID>(Detour_DrawTextExW)},
        {"TextOutW",     reinterpret_cast<PVOID*>(&Real_TextOutW),     reinterpret_cast<PVOID>(Detour_TextOutW)},
        {"ExtTextOutW",  reinterpret_cast<PVOID*>(&Real_ExtTextOutW),  reinterpret_cast<PVOID>(Detour_ExtTextOutW)},
        {"BitBlt",       reinterpret_cast<PVOID*>(&Real_BitBlt),       reinterpret_cast<PVOID>(Detour_BitBlt)},
        {"StretchBlt",   reinterpret_cast<PVOID*>(&Real_StretchBlt),   reinterpret_cast<PVOID>(Detour_StretchBlt)},
    });
}

} // namespace gdi_hooks
} // namespace sandbox
