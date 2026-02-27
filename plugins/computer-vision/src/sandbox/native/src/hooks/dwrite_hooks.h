// ==========================================================================
// hooks/dwrite_hooks.h - DirectWrite / Direct2D text rendering hooks
// ==========================================================================
// COM vtable patching for:
//   - ID2D1RenderTarget::DrawText
//   - ID2D1RenderTarget::DrawTextLayout
//   - IDWriteTextLayout::Draw (for text extraction from layouts)
//
// Uses runtime vtable discovery. Gracefully falls back if Direct2D is
// not loaded in the target process.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_DWRITE_HOOKS_H
#define SANDBOX_SHIM_DWRITE_HOOKS_H

#include "hook_engine.h"

namespace sandbox {
namespace dwrite_hooks {

// Register DirectWrite/Direct2D hooks with the engine.
// If d2d1.dll or dwrite.dll are not loaded, this is a no-op.
void register_hooks(HookEngine& engine);

// Attempt late-binding hook installation.
// Called when a D2D render target is first observed.
// Thread-safe; idempotent after first successful call.
void try_late_bind();

} // namespace dwrite_hooks
} // namespace sandbox

#endif // SANDBOX_SHIM_DWRITE_HOOKS_H
