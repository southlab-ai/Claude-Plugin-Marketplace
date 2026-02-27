// ==========================================================================
// hook_engine.cpp - Centralized Detours hook management implementation
// ==========================================================================

#include "hook_engine.h"
#include <detours.h>
#include <sstream>

namespace sandbox {

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

HookEngine& HookEngine::instance() {
    static HookEngine s_instance;
    return s_instance;
}

HookEngine::HookEngine()
    : m_attached(false)
    , m_attached_count(0)
{
    InitializeCriticalSectionAndSpinCount(&m_cs, 4000);
}

HookEngine::~HookEngine() {
    if (m_attached) {
        detach_all();
    }
    DeleteCriticalSection(&m_cs);
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

void HookEngine::register_hook(const HookDescriptor& desc) {
    EnterCriticalSection(&m_cs);
    m_descriptors.push_back(desc);
    LeaveCriticalSection(&m_cs);
}

void HookEngine::register_hooks(const std::vector<HookDescriptor>& descs) {
    EnterCriticalSection(&m_cs);
    m_descriptors.insert(m_descriptors.end(), descs.begin(), descs.end());
    LeaveCriticalSection(&m_cs);
}

// ---------------------------------------------------------------------------
// Attach
// ---------------------------------------------------------------------------

bool HookEngine::attach_all() {
    EnterCriticalSection(&m_cs);

    if (m_attached) {
        LeaveCriticalSection(&m_cs);
        return true; // Already attached
    }

    m_results.clear();
    m_attached_count = 0;

    // Begin a single Detours transaction for all hooks
    LONG error = DetourTransactionBegin();
    if (error != NO_ERROR) {
        // Cannot even start transaction
        for (const auto& desc : m_descriptors) {
            m_results.push_back({desc.name, false, error});
        }
        LeaveCriticalSection(&m_cs);
        return false;
    }

    // Update the current thread so Detours can safely modify code
    error = DetourUpdateThread(GetCurrentThread());
    if (error != NO_ERROR) {
        DetourTransactionAbort();
        for (const auto& desc : m_descriptors) {
            m_results.push_back({desc.name, false, error});
        }
        LeaveCriticalSection(&m_cs);
        return false;
    }

    // Attach each hook individually, recording per-hook results.
    // A failure on one hook does not abort the transaction — we continue
    // attaching the remaining hooks.
    std::vector<bool> per_hook_ok(m_descriptors.size(), false);

    for (size_t i = 0; i < m_descriptors.size(); ++i) {
        const auto& desc = m_descriptors[i];
        LONG attach_err = DetourAttach(desc.ppPointer, desc.pDetour);
        if (attach_err == NO_ERROR) {
            per_hook_ok[i] = true;
        }
        m_results.push_back({desc.name, attach_err == NO_ERROR, attach_err});
    }

    // Commit the transaction — this applies all successful attaches
    error = DetourTransactionCommit();
    if (error != NO_ERROR) {
        // Transaction commit failed; mark all hooks as failed
        for (auto& r : m_results) {
            r.success    = false;
            r.error_code = error;
        }
        LeaveCriticalSection(&m_cs);
        return false;
    }

    // Count successful hooks
    for (const auto& r : m_results) {
        if (r.success) {
            ++m_attached_count;
        }
    }

    m_attached = (m_attached_count > 0);
    LeaveCriticalSection(&m_cs);
    return m_attached;
}

// ---------------------------------------------------------------------------
// Detach
// ---------------------------------------------------------------------------

bool HookEngine::detach_all() {
    EnterCriticalSection(&m_cs);

    if (!m_attached) {
        LeaveCriticalSection(&m_cs);
        return true;
    }

    m_results.clear();

    LONG error = DetourTransactionBegin();
    if (error != NO_ERROR) {
        LeaveCriticalSection(&m_cs);
        return false;
    }

    error = DetourUpdateThread(GetCurrentThread());
    if (error != NO_ERROR) {
        DetourTransactionAbort();
        LeaveCriticalSection(&m_cs);
        return false;
    }

    for (const auto& desc : m_descriptors) {
        LONG detach_err = DetourDetach(desc.ppPointer, desc.pDetour);
        m_results.push_back({desc.name, detach_err == NO_ERROR, detach_err});
    }

    error = DetourTransactionCommit();
    if (error != NO_ERROR) {
        for (auto& r : m_results) {
            r.success    = false;
            r.error_code = error;
        }
        LeaveCriticalSection(&m_cs);
        return false;
    }

    m_attached       = false;
    m_attached_count = 0;
    LeaveCriticalSection(&m_cs);
    return true;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const std::vector<HookResult>& HookEngine::last_results() const {
    return m_results;
}

bool HookEngine::is_attached() const {
    return m_attached;
}

size_t HookEngine::attached_count() const {
    return m_attached_count;
}

std::string HookEngine::status_summary() const {
    std::ostringstream oss;
    oss << "HookEngine: " << m_attached_count << "/" << m_descriptors.size()
        << " hooks attached";
    for (const auto& r : m_results) {
        oss << "\n  " << r.name << ": "
            << (r.success ? "OK" : "FAIL (error=" + std::to_string(r.error_code) + ")");
    }
    return oss.str();
}

} // namespace sandbox
