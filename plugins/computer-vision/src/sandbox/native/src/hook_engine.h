// ==========================================================================
// hook_engine.h - Centralized Detours hook management
// ==========================================================================
// Singleton that manages all API hook attach/detach operations using
// Microsoft Detours. Owns all trampoline pointers and provides
// per-hook success/failure reporting.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_HOOK_ENGINE_H
#define SANDBOX_SHIM_HOOK_ENGINE_H

#include <windows.h>
#include <cstdint>
#include <string>
#include <vector>
#include <functional>

// Forward declare detours; actual header included in .cpp
// We only need the types in the implementation.

namespace sandbox {

// Result of a single hook attach/detach operation
struct HookResult {
    std::string name;       // Human-readable hook name (e.g., "DrawTextW")
    bool        success;    // true if Detours operation succeeded
    LONG        error_code; // Detours error code (NO_ERROR on success)
};

// Descriptor for a single hook to be installed
struct HookDescriptor {
    const char* name;       // Name for logging
    PVOID*      ppPointer;  // Pointer to the trampoline (real function pointer)
    PVOID       pDetour;    // Our detour function
};

class HookEngine {
public:
    // Get the singleton instance
    static HookEngine& instance();

    // Non-copyable, non-movable
    HookEngine(const HookEngine&)            = delete;
    HookEngine& operator=(const HookEngine&) = delete;
    HookEngine(HookEngine&&)                 = delete;
    HookEngine& operator=(HookEngine&&)      = delete;

    // Attach all registered hooks. Returns true if at least one hook succeeded.
    // Individual failures are logged but do not prevent other hooks from attaching.
    bool attach_all();

    // Detach all currently attached hooks. Returns true if transaction succeeded.
    bool detach_all();

    // Register a hook descriptor. Must be called before attach_all().
    void register_hook(const HookDescriptor& desc);

    // Register multiple hooks at once
    void register_hooks(const std::vector<HookDescriptor>& descs);

    // Get results from the last attach/detach operation
    const std::vector<HookResult>& last_results() const;

    // Check if hooks are currently attached
    bool is_attached() const;

    // Get count of successfully attached hooks
    size_t attached_count() const;

    // Get summary string of hook status for logging
    std::string status_summary() const;

private:
    HookEngine();
    ~HookEngine();

    CRITICAL_SECTION                m_cs;
    std::vector<HookDescriptor>     m_descriptors;
    std::vector<HookResult>         m_results;
    bool                            m_attached;
    size_t                          m_attached_count;
};

} // namespace sandbox

#endif // SANDBOX_SHIM_HOOK_ENGINE_H
