// ==========================================================================
// scene_graph.h - Thread-safe scene graph aggregation
// ==========================================================================
// Central data structure that aggregates all hook output:
//   - Window tree (from window_hooks)
//   - Text elements (from gdi_hooks, dwrite_hooks)
//   - Frame captures (from dxgi_hooks)
//
// Thread safety: SRWLOCK (readers-writer lock)
// Versioning: monotonic uint64_t, incremented on every mutation
// Staleness: elements older than 500ms are flagged stale
// Password redaction: ES_PASSWORD styled controls -> asterisks
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_SCENE_GRAPH_H
#define SANDBOX_SHIM_SCENE_GRAPH_H

#include <windows.h>
#include <cstdint>
#include <string>
#include <vector>

// Forward declare nlohmann::json
namespace nlohmann { class json; }
// We use the actual json in the .cpp; header only needs the forward decl
// for the serialize methods.

namespace sandbox {

// Rect used throughout the scene graph
struct SceneGraphRect {
    int x = 0;
    int y = 0;
    int w = 0;
    int h = 0;
};

// A text element captured by GDI or DirectWrite hooks
struct TextElement {
    std::wstring     text;
    std::wstring     font;
    SceneGraphRect   rect;
    HWND             hwnd;
    std::string      source_api;   // e.g., "gdi_DrawTextW", "d2d_DrawText"
    uint64_t         timestamp_ms;
};

class SceneGraph {
public:
    // Type alias for the rect
    using Rect = SceneGraphRect;

    static SceneGraph& instance();

    // Non-copyable
    SceneGraph(const SceneGraph&)            = delete;
    SceneGraph& operator=(const SceneGraph&) = delete;

    // --- Mutation (called from hook callbacks) ---

    // Add a text element (from GDI/DWrite hooks)
    void add_text_element(TextElement&& elem);

    // Note a blit region (from GDI BitBlt/StretchBlt hooks)
    void note_blit_region(HWND hwnd, const Rect& rect);

    // Bump the version counter (called on window tree changes)
    void bump_version();

    // --- Snapshot ---

    // Get the current version number
    uint64_t current_version() const;

    // Serialize the full scene graph to JSON string
    std::string serialize_full() const;

    // Serialize only changes since a given version (diff)
    std::string serialize_diff(uint64_t since_version) const;

    // --- Frame boundary ---

    // Called periodically (500ms timer) to mark a frame boundary.
    // Clears transient text elements and increments version.
    void frame_boundary();

    // Check if the scene graph is stale (no updates for >500ms)
    bool is_stale() const;

    // --- Frame capture passthrough ---

    // Store a frame capture reference (called from IPC dispatch)
    void set_frame_capture_available(bool available);

private:
    SceneGraph();
    ~SceneGraph();

    // Apply password redaction to a text element
    void redact_passwords(TextElement& elem) const;

    // Convert wstring to UTF-8
    static std::string to_utf8(const std::wstring& wstr);

    mutable SRWLOCK          m_lock;
    uint64_t                 m_version;
    uint64_t                 m_last_update_ms;

    // Text elements collected since the last frame boundary
    std::vector<TextElement> m_text_elements;

    // Text elements from the previous frame (for diff)
    std::vector<TextElement> m_prev_text_elements;
    uint64_t                 m_prev_version;

    // Blit regions (for invalidation tracking)
    struct BlitRecord {
        HWND     hwnd;
        Rect     rect;
        uint64_t timestamp_ms;
    };
    std::vector<BlitRecord>  m_blit_regions;

    // Frame capture available
    bool m_frame_capture_available;

    // Frame boundary timer thread
    HANDLE m_timer_thread;
    volatile bool m_shutdown;

    static DWORD WINAPI timer_thread_proc(LPVOID param);
};

} // namespace sandbox

#endif // SANDBOX_SHIM_SCENE_GRAPH_H
