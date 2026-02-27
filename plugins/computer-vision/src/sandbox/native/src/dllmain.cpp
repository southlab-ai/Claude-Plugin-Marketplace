// ==========================================================================
// dllmain.cpp - DLL entry point for the Sandbox Shim
// ==========================================================================
// Initializes all subsystems on DLL_PROCESS_ATTACH:
//   1. Hook engine (registers and attaches all hooks)
//   2. Scene graph (thread-safe aggregation)
//   3. IPC server (TCP communication with host agent)
// Tears down cleanly on DLL_PROCESS_DETACH.
// ==========================================================================

#include <windows.h>

#include "hook_engine.h"
#include "scene_graph.h"
#include "message_injector.h"
#include "ipc/ipc_server.h"
#include "hooks/gdi_hooks.h"
#include "hooks/dwrite_hooks.h"
#include "hooks/dxgi_hooks.h"
#include "hooks/window_hooks.h"

// Output debug string helper - safe for DllMain context
static void shim_log(const char* msg) {
    OutputDebugStringA("[SandboxShim] ");
    OutputDebugStringA(msg);
    OutputDebugStringA("\n");
}

// ---------------------------------------------------------------------------
// DLL initialization
// ---------------------------------------------------------------------------

static bool initialize_shim(HMODULE hModule) {
    shim_log("Initializing sandbox shim...");

    // -----------------------------------------------------------------------
    // 1. Register all hooks with the engine
    // -----------------------------------------------------------------------
    auto& engine = sandbox::HookEngine::instance();

    // GDI text/blit hooks
    sandbox::gdi_hooks::register_hooks(engine);

    // DirectWrite / Direct2D hooks
    sandbox::dwrite_hooks::register_hooks(engine);

    // DXGI swap chain hooks (frame capture)
    sandbox::dxgi_hooks::register_hooks(engine);

    // Window management hooks
    sandbox::window_hooks::register_hooks(engine);

    // -----------------------------------------------------------------------
    // 2. Attach all hooks in a single Detours transaction
    // -----------------------------------------------------------------------
    if (!engine.attach_all()) {
        shim_log("WARNING: No hooks were successfully attached!");
        // We continue anyway — the IPC server can still report status
    }

    // Log hook status
    std::string summary = engine.status_summary();
    shim_log(summary.c_str());

    // -----------------------------------------------------------------------
    // 3. Initialize the scene graph
    // -----------------------------------------------------------------------
    sandbox::SceneGraph::instance(); // Force construction

    // -----------------------------------------------------------------------
    // 4. Initialize the message injector
    // -----------------------------------------------------------------------
    sandbox::MessageInjector::instance(); // Force construction

    // -----------------------------------------------------------------------
    // 5. Start the IPC server on a background thread
    // -----------------------------------------------------------------------
    if (!sandbox::IpcServer::instance().start()) {
        shim_log("WARNING: IPC server failed to start!");
    }

    shim_log("Sandbox shim initialized.");
    return true;
}

// ---------------------------------------------------------------------------
// DLL teardown
// ---------------------------------------------------------------------------

static void shutdown_shim() {
    shim_log("Shutting down sandbox shim...");

    // Stop IPC server first (stops accepting commands)
    sandbox::IpcServer::instance().stop();

    // Detach all hooks
    sandbox::HookEngine::instance().detach_all();

    shim_log("Sandbox shim shut down.");
}

// ---------------------------------------------------------------------------
// DllMain
// ---------------------------------------------------------------------------

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
        case DLL_PROCESS_ATTACH:
            // We don't need thread attach/detach notifications
            DisableThreadLibraryCalls(hModule);
            if (!initialize_shim(hModule)) {
                return FALSE;
            }
            break;

        case DLL_PROCESS_DETACH:
            // lpReserved != NULL means process is terminating — skip cleanup
            // as the OS will reclaim all resources. Only do orderly shutdown
            // when the DLL is being explicitly unloaded.
            if (lpReserved == nullptr) {
                shutdown_shim();
            }
            break;

        case DLL_THREAD_ATTACH:
        case DLL_THREAD_DETACH:
            // Disabled via DisableThreadLibraryCalls
            break;
    }
    return TRUE;
}
