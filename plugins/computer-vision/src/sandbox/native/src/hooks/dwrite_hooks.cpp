// ==========================================================================
// hooks/dwrite_hooks.cpp - DirectWrite / Direct2D COM vtable hook impl
// ==========================================================================
// Strategy:
//   Direct2D and DirectWrite use COM interfaces. We cannot use Detours
//   on COM methods directly because they are vtable-dispatched. Instead,
//   we create dummy D2D/DWrite objects at hook registration time to
//   discover the vtable layout, then use Detours to hook the vtable
//   function pointers.
//
//   If Direct2D is not loaded (pure GDI app), we skip gracefully.
// ==========================================================================

#include "hooks/dwrite_hooks.h"
#include "scene_graph.h"

#include <windows.h>
#include <d2d1.h>
#include <dwrite.h>
#include <detours.h>
#include <atomic>
#include <string>
#include <mutex>

#pragma comment(lib, "d2d1.lib")
#pragma comment(lib, "dwrite.lib")

namespace sandbox {
namespace dwrite_hooks {

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

static std::atomic<bool> s_hooks_installed{false};
static CRITICAL_SECTION  s_init_cs;
static bool              s_cs_initialized = false;

// Vtable slot indices for ID2D1RenderTarget
// These are fixed by the COM interface definition
// ID2D1RenderTarget inherits from ID2D1Resource -> IUnknown
// IUnknown: 0=QueryInterface, 1=AddRef, 2=Release
// ID2D1Resource: 3=GetFactory
// ID2D1RenderTarget: ... DrawText is slot 27, DrawTextLayout is slot 28
// (counted from the IDWriteTextFormat-parameterized overloads)
static constexpr int VTABLE_SLOT_DRAWTEXT       = 27;
static constexpr int VTABLE_SLOT_DRAWTEXTLAYOUT  = 28;

// Trampoline pointers
using FnDrawText = HRESULT(STDMETHODCALLTYPE*)(
    ID2D1RenderTarget* pThis,
    const WCHAR*       string,
    UINT32             stringLength,
    IDWriteTextFormat* textFormat,
    const D2D1_RECT_F* layoutRect,
    ID2D1Brush*        defaultFillBrush,
    D2D1_DRAW_TEXT_OPTIONS options,
    DWRITE_MEASURING_MODE  measuringMode
);

using FnDrawTextLayout = HRESULT(STDMETHODCALLTYPE*)(
    ID2D1RenderTarget*   pThis,
    D2D1_POINT_2F        origin,
    IDWriteTextLayout*   textLayout,
    ID2D1Brush*          defaultFillBrush,
    D2D1_DRAW_TEXT_OPTIONS options
);

static FnDrawText       Real_DrawText       = nullptr;
static FnDrawTextLayout Real_DrawTextLayout = nullptr;

// Max text capture
static constexpr UINT32 MAX_TEXT_CHARS = 32768;

// ---------------------------------------------------------------------------
// Helper: extract font family from IDWriteTextFormat
// ---------------------------------------------------------------------------

static std::wstring get_font_family(IDWriteTextFormat* fmt) {
    if (!fmt) return L"";
    UINT32 name_len = fmt->GetFontFamilyNameLength();
    if (name_len == 0 || name_len > 1024) return L"";
    std::wstring name(name_len + 1, L'\0');
    HRESULT hr = fmt->GetFontFamilyName(&name[0], name_len + 1);
    if (FAILED(hr)) return L"";
    name.resize(name_len);
    return name;
}

// ---------------------------------------------------------------------------
// Detour: ID2D1RenderTarget::DrawText
// ---------------------------------------------------------------------------

static HRESULT STDMETHODCALLTYPE Detour_DrawText(
    ID2D1RenderTarget*     pThis,
    const WCHAR*           string,
    UINT32                 stringLength,
    IDWriteTextFormat*     textFormat,
    const D2D1_RECT_F*    layoutRect,
    ID2D1Brush*            defaultFillBrush,
    D2D1_DRAW_TEXT_OPTIONS options,
    DWRITE_MEASURING_MODE  measuringMode
) {
    __try {
        if (string && stringLength > 0) {
            UINT32 safe_len = (stringLength < MAX_TEXT_CHARS) ? stringLength : MAX_TEXT_CHARS;
            std::wstring text(string, safe_len);
            std::wstring font = get_font_family(textFormat);

            SceneGraph::Rect rect = {};
            if (layoutRect) {
                rect.x = static_cast<int>(layoutRect->left);
                rect.y = static_cast<int>(layoutRect->top);
                rect.w = static_cast<int>(layoutRect->right - layoutRect->left);
                rect.h = static_cast<int>(layoutRect->bottom - layoutRect->top);
            }

            TextElement elem;
            elem.text         = std::move(text);
            elem.font         = std::move(font);
            elem.rect         = rect;
            elem.hwnd         = nullptr; // D2D doesn't directly associate with HWND
            elem.source_api   = "d2d_DrawText";
            elem.timestamp_ms = GetTickCount64();

            SceneGraph::instance().add_text_element(std::move(elem));
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }

    return Real_DrawText(pThis, string, stringLength, textFormat,
                         layoutRect, defaultFillBrush, options, measuringMode);
}

// ---------------------------------------------------------------------------
// Detour: ID2D1RenderTarget::DrawTextLayout
// ---------------------------------------------------------------------------

static HRESULT STDMETHODCALLTYPE Detour_DrawTextLayout(
    ID2D1RenderTarget*     pThis,
    D2D1_POINT_2F          origin,
    IDWriteTextLayout*     textLayout,
    ID2D1Brush*            defaultFillBrush,
    D2D1_DRAW_TEXT_OPTIONS options
) {
    __try {
        if (textLayout) {
            // Extract text content from the layout
            UINT32 text_len = 0;
            // IDWriteTextLayout inherits from IDWriteTextFormat
            // We can get the text by querying the layout metrics
            // Unfortunately there's no direct GetText, so we use
            // the fact that IDWriteTextLayout stores the original string.
            // We get metrics to determine rect.
            DWRITE_TEXT_METRICS metrics = {};
            HRESULT hr = textLayout->GetMetrics(&metrics);

            SceneGraph::Rect rect = {};
            if (SUCCEEDED(hr)) {
                rect.x = static_cast<int>(origin.x + metrics.left);
                rect.y = static_cast<int>(origin.y + metrics.top);
                rect.w = static_cast<int>(metrics.widthIncludingTrailingWhitespace);
                rect.h = static_cast<int>(metrics.height);
            }

            // Extract font family from the layout (it is an IDWriteTextFormat)
            std::wstring font = get_font_family(textLayout);

            // We cannot directly extract text from IDWriteTextLayout without
            // the original string. We record the layout metrics and font.
            TextElement elem;
            elem.text         = L"[DirectWrite TextLayout]";
            elem.font         = std::move(font);
            elem.rect         = rect;
            elem.hwnd         = nullptr;
            elem.source_api   = "d2d_DrawTextLayout";
            elem.timestamp_ms = GetTickCount64();

            SceneGraph::instance().add_text_element(std::move(elem));
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Swallow
    }

    return Real_DrawTextLayout(pThis, origin, textLayout,
                               defaultFillBrush, options);
}

// ---------------------------------------------------------------------------
// Late-binding: create a temporary D2D factory + render target to get vtable
// ---------------------------------------------------------------------------

static bool discover_and_hook_vtable() {
    // Try to load d2d1.dll
    HMODULE hD2D1 = GetModuleHandleW(L"d2d1.dll");
    if (!hD2D1) {
        // Direct2D not loaded — nothing to hook
        return false;
    }

    // Create a D2D1 factory
    typedef HRESULT(WINAPI* PFN_D2D1CreateFactory)(
        D2D1_FACTORY_TYPE, REFIID, const D2D1_FACTORY_OPTIONS*, void**);

    auto pfnCreate = reinterpret_cast<PFN_D2D1CreateFactory>(
        GetProcAddress(hD2D1, "D2D1CreateFactory"));
    if (!pfnCreate) return false;

    ID2D1Factory* pFactory = nullptr;
    D2D1_FACTORY_OPTIONS opts = {};
    HRESULT hr = pfnCreate(
        D2D1_FACTORY_TYPE_SINGLE_THREADED,
        __uuidof(ID2D1Factory),
        &opts,
        reinterpret_cast<void**>(&pFactory)
    );
    if (FAILED(hr) || !pFactory) return false;

    // Create a dummy DC render target to obtain the vtable
    D2D1_RENDER_TARGET_PROPERTIES rtProps = D2D1::RenderTargetProperties(
        D2D1_RENDER_TARGET_TYPE_DEFAULT,
        D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED),
        0, 0,
        D2D1_RENDER_TARGET_USAGE_NONE,
        D2D1_FEATURE_LEVEL_DEFAULT
    );

    ID2D1DCRenderTarget* pDCRT = nullptr;
    hr = pFactory->CreateDCRenderTarget(&rtProps, &pDCRT);
    if (FAILED(hr) || !pDCRT) {
        pFactory->Release();
        return false;
    }

    // Read vtable pointers
    void** vtable = *reinterpret_cast<void***>(pDCRT);
    Real_DrawText       = reinterpret_cast<FnDrawText>(vtable[VTABLE_SLOT_DRAWTEXT]);
    Real_DrawTextLayout = reinterpret_cast<FnDrawTextLayout>(vtable[VTABLE_SLOT_DRAWTEXTLAYOUT]);

    // Use Detours to hook these specific function pointers
    LONG err;
    bool ok = true;

    err = DetourTransactionBegin();
    if (err != NO_ERROR) { ok = false; goto cleanup; }

    err = DetourUpdateThread(GetCurrentThread());
    if (err != NO_ERROR) { DetourTransactionAbort(); ok = false; goto cleanup; }

    err = DetourAttach(
        reinterpret_cast<PVOID*>(&Real_DrawText),
        reinterpret_cast<PVOID>(Detour_DrawText));
    if (err != NO_ERROR) { ok = false; }

    err = DetourAttach(
        reinterpret_cast<PVOID*>(&Real_DrawTextLayout),
        reinterpret_cast<PVOID>(Detour_DrawTextLayout));
    if (err != NO_ERROR) { ok = false; }

    err = DetourTransactionCommit();
    if (err != NO_ERROR) { ok = false; }

cleanup:
    pDCRT->Release();
    pFactory->Release();
    return ok;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void register_hooks(HookEngine& engine) {
    // Initialize the critical section for late binding
    if (!s_cs_initialized) {
        InitializeCriticalSectionAndSpinCount(&s_init_cs, 4000);
        s_cs_initialized = true;
    }

    // Attempt immediate discovery.
    // If d2d1.dll is already loaded, we can hook now.
    // Otherwise, try_late_bind() can be called later.
    try_late_bind();

    // Note: D2D hooks are installed via direct vtable patching,
    // not through the HookEngine descriptor system. The engine
    // parameter is accepted for API consistency but D2D hooks
    // manage their own Detours transactions.
    (void)engine;
}

void try_late_bind() {
    if (s_hooks_installed.load(std::memory_order_acquire)) return;

    EnterCriticalSection(&s_init_cs);
    if (!s_hooks_installed.load(std::memory_order_relaxed)) {
        if (discover_and_hook_vtable()) {
            s_hooks_installed.store(true, std::memory_order_release);
            OutputDebugStringA("[SandboxShim] D2D/DWrite vtable hooks installed\n");
        }
    }
    LeaveCriticalSection(&s_init_cs);
}

} // namespace dwrite_hooks
} // namespace sandbox
