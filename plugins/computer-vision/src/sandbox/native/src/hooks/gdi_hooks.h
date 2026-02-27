// ==========================================================================
// hooks/gdi_hooks.h - GDI text and blit API hooks
// ==========================================================================
// Intercepts GDI drawing calls to extract rendered text and blit regions:
//   - DrawTextW / DrawTextExW
//   - TextOutW / ExtTextOutW
//   - BitBlt / StretchBlt
//
// Text elements are pushed to the SceneGraph with font, rect, and HWND info.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_GDI_HOOKS_H
#define SANDBOX_SHIM_GDI_HOOKS_H

#include "hook_engine.h"

namespace sandbox {
namespace gdi_hooks {

// Register all GDI hook descriptors with the engine.
// Must be called before HookEngine::attach_all().
void register_hooks(HookEngine& engine);

} // namespace gdi_hooks
} // namespace sandbox

#endif // SANDBOX_SHIM_GDI_HOOKS_H
