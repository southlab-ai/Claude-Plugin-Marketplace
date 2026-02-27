// ==========================================================================
// hooks/dxgi_hooks.cpp - DXGI SwapChain::Present hook implementation
// ==========================================================================
// Hooks IDXGISwapChain::Present by discovering the vtable from a temporary
// swap chain. Captures frames to a ring buffer via staging texture readback.
//
// Throttling: max 10 FPS (100ms between captures).
// Resolution cap: 8192x8192 pixels.
// Ring buffer: 3 frames deep.
// ==========================================================================

#include "hooks/dxgi_hooks.h"
#include "scene_graph.h"

#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <detours.h>
#include <atomic>
#include <array>

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")

namespace sandbox {
namespace dxgi_hooks {

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

static constexpr UINT   MAX_FRAME_WIDTH   = 8192;
static constexpr UINT   MAX_FRAME_HEIGHT  = 8192;
static constexpr UINT64 MIN_CAPTURE_INTERVAL_MS = 100; // 10 FPS max
static constexpr int    RING_BUFFER_SIZE  = 3;

// IDXGISwapChain vtable: IUnknown(3) + IDXGIObject(4) + IDXGIDeviceSubObject(1) + IDXGISwapChain(Present=8th method = slot 8)
static constexpr int VTABLE_SLOT_PRESENT = 8;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

static std::atomic<bool> s_hooks_installed{false};
static CRITICAL_SECTION  s_init_cs;
static bool              s_cs_initialized = false;

// Ring buffer for captured frames
struct RingEntry {
    FrameData data;
    bool      occupied = false;
};

static SRWLOCK          s_ring_lock = SRWLOCK_INIT;
static std::array<RingEntry, RING_BUFFER_SIZE> s_ring;
static int              s_ring_write_idx = 0;
static int              s_ring_read_idx  = 0;

// Throttle
static UINT64 s_last_capture_ms = 0;

// Staging texture (lazily created per swap chain backbuffer format)
static ID3D11Texture2D*   s_staging_texture   = nullptr;
static ID3D11Device*      s_cached_device     = nullptr;
static UINT               s_staging_width     = 0;
static UINT               s_staging_height    = 0;

// Trampoline
using FnPresent = HRESULT(STDMETHODCALLTYPE*)(
    IDXGISwapChain* pThis, UINT SyncInterval, UINT Flags);

static FnPresent Real_Present = nullptr;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static void ensure_staging_texture(
    ID3D11Device* device,
    UINT width, UINT height, DXGI_FORMAT format
) {
    // Clamp dimensions
    width  = (width  > MAX_FRAME_WIDTH)  ? MAX_FRAME_WIDTH  : width;
    height = (height > MAX_FRAME_HEIGHT) ? MAX_FRAME_HEIGHT : height;

    if (s_staging_texture && s_cached_device == device &&
        s_staging_width == width && s_staging_height == height) {
        return; // Already have a matching staging texture
    }

    // Release old
    if (s_staging_texture) {
        s_staging_texture->Release();
        s_staging_texture = nullptr;
    }

    D3D11_TEXTURE2D_DESC desc = {};
    desc.Width              = width;
    desc.Height             = height;
    desc.MipLevels          = 1;
    desc.ArraySize          = 1;
    desc.Format             = format;
    desc.SampleDesc.Count   = 1;
    desc.SampleDesc.Quality = 0;
    desc.Usage              = D3D11_USAGE_STAGING;
    desc.BindFlags          = 0;
    desc.CPUAccessFlags     = D3D11_CPU_ACCESS_READ;
    desc.MiscFlags          = 0;

    HRESULT hr = device->CreateTexture2D(&desc, nullptr, &s_staging_texture);
    if (SUCCEEDED(hr)) {
        s_cached_device  = device;
        s_staging_width  = width;
        s_staging_height = height;
    } else {
        s_staging_texture = nullptr;
    }
}

static void capture_frame(IDXGISwapChain* pSwapChain) {
    // Get the back buffer
    ID3D11Texture2D* backbuffer = nullptr;
    HRESULT hr = pSwapChain->GetBuffer(0, __uuidof(ID3D11Texture2D),
                                       reinterpret_cast<void**>(&backbuffer));
    if (FAILED(hr) || !backbuffer) return;

    // Get device and context
    ID3D11Device* device = nullptr;
    backbuffer->GetDevice(&device);
    if (!device) {
        backbuffer->Release();
        return;
    }

    ID3D11DeviceContext* ctx = nullptr;
    device->GetImmediateContext(&ctx);
    if (!ctx) {
        device->Release();
        backbuffer->Release();
        return;
    }

    // Get backbuffer desc
    D3D11_TEXTURE2D_DESC bbDesc;
    backbuffer->GetDesc(&bbDesc);

    UINT w = bbDesc.Width;
    UINT h = bbDesc.Height;

    // Enforce caps
    if (w > MAX_FRAME_WIDTH || h > MAX_FRAME_HEIGHT) {
        ctx->Release();
        device->Release();
        backbuffer->Release();
        return;
    }

    // Ensure we have a staging texture
    ensure_staging_texture(device, w, h, bbDesc.Format);
    if (!s_staging_texture) {
        ctx->Release();
        device->Release();
        backbuffer->Release();
        return;
    }

    // Copy backbuffer to staging
    ctx->CopyResource(s_staging_texture, backbuffer);

    // Map the staging texture for CPU read
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    hr = ctx->Map(s_staging_texture, 0, D3D11_MAP_READ, 0, &mapped);
    if (FAILED(hr)) {
        ctx->Release();
        device->Release();
        backbuffer->Release();
        return;
    }

    // Copy pixel data (BGRA)
    FrameData frame;
    frame.width        = w;
    frame.height       = h;
    frame.timestamp_ms = GetTickCount64();
    frame.valid        = true;
    frame.bgra_pixels.resize(static_cast<size_t>(w) * h * 4);

    const uint8_t* src = static_cast<const uint8_t*>(mapped.pData);
    uint8_t*       dst = frame.bgra_pixels.data();
    for (UINT row = 0; row < h; ++row) {
        memcpy(dst + row * w * 4, src + row * mapped.RowPitch, w * 4);
    }

    ctx->Unmap(s_staging_texture, 0);

    // Store in ring buffer
    AcquireSRWLockExclusive(&s_ring_lock);
    s_ring[s_ring_write_idx].data     = std::move(frame);
    s_ring[s_ring_write_idx].occupied = true;
    s_ring_read_idx  = s_ring_write_idx;
    s_ring_write_idx = (s_ring_write_idx + 1) % RING_BUFFER_SIZE;
    ReleaseSRWLockExclusive(&s_ring_lock);

    // Cleanup
    ctx->Release();
    device->Release();
    backbuffer->Release();
}

// ---------------------------------------------------------------------------
// Detour
// ---------------------------------------------------------------------------

static HRESULT STDMETHODCALLTYPE Detour_Present(
    IDXGISwapChain* pThis,
    UINT            SyncInterval,
    UINT            Flags
) {
    __try {
        UINT64 now = GetTickCount64();
        if (now - s_last_capture_ms >= MIN_CAPTURE_INTERVAL_MS) {
            s_last_capture_ms = now;
            capture_frame(pThis);
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        // Never crash the host
    }

    return Real_Present(pThis, SyncInterval, Flags);
}

// ---------------------------------------------------------------------------
// Vtable discovery
// ---------------------------------------------------------------------------

static bool discover_and_hook_vtable() {
    HMODULE hDXGI = GetModuleHandleW(L"dxgi.dll");
    if (!hDXGI) return false;

    HMODULE hD3D11 = GetModuleHandleW(L"d3d11.dll");
    if (!hD3D11) return false;

    // Create a temporary D3D11 device and swap chain to read the vtable
    using PFN_D3D11CreateDeviceAndSwapChain = HRESULT(WINAPI*)(
        IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT,
        const D3D_FEATURE_LEVEL*, UINT, UINT,
        const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**,
        ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

    auto pfnCreate = reinterpret_cast<PFN_D3D11CreateDeviceAndSwapChain>(
        GetProcAddress(hD3D11, "D3D11CreateDeviceAndSwapChain"));
    if (!pfnCreate) return false;

    // We need a temporary window for the swap chain
    WNDCLASSEXW wc = {};
    wc.cbSize        = sizeof(wc);
    wc.lpfnWndProc   = DefWindowProcW;
    wc.hInstance      = GetModuleHandleW(nullptr);
    wc.lpszClassName  = L"SandboxShimDXGIProbe";
    RegisterClassExW(&wc);

    HWND hWnd = CreateWindowExW(
        0, L"SandboxShimDXGIProbe", L"", WS_OVERLAPPEDWINDOW,
        0, 0, 1, 1, nullptr, nullptr, wc.hInstance, nullptr);
    if (!hWnd) return false;

    DXGI_SWAP_CHAIN_DESC scd = {};
    scd.BufferCount       = 1;
    scd.BufferDesc.Width  = 1;
    scd.BufferDesc.Height = 1;
    scd.BufferDesc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    scd.BufferUsage       = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow      = hWnd;
    scd.SampleDesc.Count  = 1;
    scd.Windowed          = TRUE;

    D3D_FEATURE_LEVEL featureLevel = D3D_FEATURE_LEVEL_11_0;
    D3D_FEATURE_LEVEL obtainedLevel;
    IDXGISwapChain*     pSwapChain = nullptr;
    ID3D11Device*       pDevice    = nullptr;
    ID3D11DeviceContext* pCtx      = nullptr;

    HRESULT hr = pfnCreate(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
        0, &featureLevel, 1, D3D11_SDK_VERSION,
        &scd, &pSwapChain, &pDevice, &obtainedLevel, &pCtx);

    if (FAILED(hr) || !pSwapChain) {
        // Try WARP driver as fallback
        hr = pfnCreate(
            nullptr, D3D_DRIVER_TYPE_WARP, nullptr,
            0, &featureLevel, 1, D3D11_SDK_VERSION,
            &scd, &pSwapChain, &pDevice, &obtainedLevel, &pCtx);
    }

    bool result = false;

    if (SUCCEEDED(hr) && pSwapChain) {
        // Read the vtable
        void** vtable = *reinterpret_cast<void***>(pSwapChain);
        Real_Present = reinterpret_cast<FnPresent>(vtable[VTABLE_SLOT_PRESENT]);

        // Hook via Detours
        LONG err = DetourTransactionBegin();
        if (err == NO_ERROR) {
            DetourUpdateThread(GetCurrentThread());
            err = DetourAttach(
                reinterpret_cast<PVOID*>(&Real_Present),
                reinterpret_cast<PVOID>(Detour_Present));
            if (err == NO_ERROR) {
                err = DetourTransactionCommit();
                result = (err == NO_ERROR);
            } else {
                DetourTransactionAbort();
            }
        }
    }

    // Cleanup temporary objects
    if (pCtx)       pCtx->Release();
    if (pDevice)    pDevice->Release();
    if (pSwapChain) pSwapChain->Release();
    DestroyWindow(hWnd);
    UnregisterClassW(L"SandboxShimDXGIProbe", wc.hInstance);

    return result;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void register_hooks(HookEngine& engine) {
    if (!s_cs_initialized) {
        InitializeCriticalSectionAndSpinCount(&s_init_cs, 4000);
        s_cs_initialized = true;
    }

    // D2D hooks are not registered via HookEngine descriptors —
    // they use direct vtable patching with their own Detours transaction.
    (void)engine;

    try_late_bind();
}

void try_late_bind() {
    if (s_hooks_installed.load(std::memory_order_acquire)) return;

    EnterCriticalSection(&s_init_cs);
    if (!s_hooks_installed.load(std::memory_order_relaxed)) {
        if (discover_and_hook_vtable()) {
            s_hooks_installed.store(true, std::memory_order_release);
            OutputDebugStringA("[SandboxShim] DXGI Present hook installed\n");
        }
    }
    LeaveCriticalSection(&s_init_cs);
}

FrameData get_latest_frame() {
    FrameData result;
    result.valid = false;

    AcquireSRWLockShared(&s_ring_lock);
    if (s_ring[s_ring_read_idx].occupied) {
        result = s_ring[s_ring_read_idx].data; // copy
    }
    ReleaseSRWLockShared(&s_ring_lock);

    return result;
}

} // namespace dxgi_hooks
} // namespace sandbox
