// ==========================================================================
// hooks/dxgi_hooks.h - DXGI SwapChain Present hook for frame capture
// ==========================================================================
// Hooks IDXGISwapChain::Present to capture rendered frames via GPU readback.
// Uses a staging texture (D3D11_USAGE_STAGING) and ring buffer.
// Throttled to max 10 FPS. Bitmap capped at 8192x8192.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_DXGI_HOOKS_H
#define SANDBOX_SHIM_DXGI_HOOKS_H

#include "hook_engine.h"
#include <cstdint>
#include <vector>

namespace sandbox {
namespace dxgi_hooks {

// Register DXGI hooks with the engine.
void register_hooks(HookEngine& engine);

// Attempt late-binding if DXGI is loaded after our DLL.
void try_late_bind();

// Frame data from the most recent capture
struct FrameData {
    uint32_t              width;
    uint32_t              height;
    uint64_t              timestamp_ms;
    std::vector<uint8_t>  bgra_pixels;  // BGRA8888 format
    bool                  valid;
};

// Get the most recently captured frame. Returns empty/invalid if none.
FrameData get_latest_frame();

} // namespace dxgi_hooks
} // namespace sandbox

#endif // SANDBOX_SHIM_DXGI_HOOKS_H
