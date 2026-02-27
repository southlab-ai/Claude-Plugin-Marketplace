// ==========================================================================
// scene_graph.cpp - Thread-safe scene graph implementation
// ==========================================================================

#include "scene_graph.h"
#include "hooks/window_hooks.h"
#include "hooks/dxgi_hooks.h"

#include <nlohmann/json.hpp>
#include <sstream>
#include <algorithm>
#include <cstring>

using json = nlohmann::json;

namespace sandbox {

// ---------------------------------------------------------------------------
// Frame boundary interval
// ---------------------------------------------------------------------------
static constexpr UINT64 FRAME_BOUNDARY_MS = 500;
static constexpr UINT64 STALENESS_THRESHOLD_MS = 500;
static constexpr size_t MAX_TEXT_ELEMENTS = 10000;  // safety cap
static constexpr size_t MAX_BLIT_REGIONS  = 1000;

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

SceneGraph& SceneGraph::instance() {
    static SceneGraph s_instance;
    return s_instance;
}

SceneGraph::SceneGraph()
    : m_version(0)
    , m_last_update_ms(GetTickCount64())
    , m_prev_version(0)
    , m_frame_capture_available(false)
    , m_timer_thread(nullptr)
    , m_shutdown(false)
{
    InitializeSRWLock(&m_lock);

    // Start the frame boundary timer thread
    m_timer_thread = CreateThread(
        nullptr, 0, timer_thread_proc, this, 0, nullptr);
}

SceneGraph::~SceneGraph() {
    m_shutdown = true;
    if (m_timer_thread) {
        WaitForSingleObject(m_timer_thread, 2000);
        CloseHandle(m_timer_thread);
    }
}

// ---------------------------------------------------------------------------
// Timer thread
// ---------------------------------------------------------------------------

DWORD WINAPI SceneGraph::timer_thread_proc(LPVOID param) {
    auto* self = static_cast<SceneGraph*>(param);
    while (!self->m_shutdown) {
        Sleep(static_cast<DWORD>(FRAME_BOUNDARY_MS));
        if (!self->m_shutdown) {
            self->frame_boundary();
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Mutation
// ---------------------------------------------------------------------------

void SceneGraph::add_text_element(TextElement&& elem) {
    // Apply password redaction
    redact_passwords(elem);

    AcquireSRWLockExclusive(&m_lock);

    // Safety cap
    if (m_text_elements.size() < MAX_TEXT_ELEMENTS) {
        m_text_elements.push_back(std::move(elem));
    }

    ++m_version;
    m_last_update_ms = GetTickCount64();

    ReleaseSRWLockExclusive(&m_lock);
}

void SceneGraph::note_blit_region(HWND hwnd, const Rect& rect) {
    AcquireSRWLockExclusive(&m_lock);

    if (m_blit_regions.size() < MAX_BLIT_REGIONS) {
        m_blit_regions.push_back({hwnd, rect, GetTickCount64()});
    }

    ++m_version;
    m_last_update_ms = GetTickCount64();

    ReleaseSRWLockExclusive(&m_lock);
}

void SceneGraph::bump_version() {
    AcquireSRWLockExclusive(&m_lock);
    ++m_version;
    m_last_update_ms = GetTickCount64();
    ReleaseSRWLockExclusive(&m_lock);
}

// ---------------------------------------------------------------------------
// Frame boundary
// ---------------------------------------------------------------------------

void SceneGraph::frame_boundary() {
    AcquireSRWLockExclusive(&m_lock);

    // Move current elements to previous (for diff support)
    m_prev_text_elements = std::move(m_text_elements);
    m_prev_version       = m_version;
    m_text_elements.clear();

    // Clear blit regions
    m_blit_regions.clear();

    ++m_version;

    ReleaseSRWLockExclusive(&m_lock);
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

uint64_t SceneGraph::current_version() const {
    AcquireSRWLockShared(const_cast<PSRWLOCK>(&m_lock));
    uint64_t v = m_version;
    ReleaseSRWLockShared(const_cast<PSRWLOCK>(&m_lock));
    return v;
}

bool SceneGraph::is_stale() const {
    AcquireSRWLockShared(const_cast<PSRWLOCK>(&m_lock));
    UINT64 now  = GetTickCount64();
    bool stale = (now - m_last_update_ms) > STALENESS_THRESHOLD_MS;
    ReleaseSRWLockShared(const_cast<PSRWLOCK>(&m_lock));
    return stale;
}

void SceneGraph::set_frame_capture_available(bool available) {
    AcquireSRWLockExclusive(&m_lock);
    m_frame_capture_available = available;
    ReleaseSRWLockExclusive(&m_lock);
}

// ---------------------------------------------------------------------------
// Password redaction
// ---------------------------------------------------------------------------

void SceneGraph::redact_passwords(TextElement& elem) const {
    if (!elem.hwnd) return;

    // Check if the window has ES_PASSWORD style
    LONG_PTR style = GetWindowLongPtrW(elem.hwnd, GWL_STYLE);
    if (style & ES_PASSWORD) {
        // Replace all characters with asterisks
        size_t len = elem.text.length();
        elem.text.assign(len, L'*');
    }
}

// ---------------------------------------------------------------------------
// UTF-8 conversion
// ---------------------------------------------------------------------------

std::string SceneGraph::to_utf8(const std::wstring& wstr) {
    if (wstr.empty()) return "";
    int size = WideCharToMultiByte(
        CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.size()),
        nullptr, 0, nullptr, nullptr);
    if (size <= 0) return "";
    std::string result(size, '\0');
    WideCharToMultiByte(
        CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.size()),
        &result[0], size, nullptr, nullptr);
    return result;
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

static json rect_to_json(const SceneGraph::Rect& r) {
    return {{"x", r.x}, {"y", r.y}, {"w", r.w}, {"h", r.h}};
}

static json text_element_to_json(const TextElement& elem) {
    json j;
    j["text"]         = SceneGraph::to_utf8(elem.text);
    j["font"]         = SceneGraph::to_utf8(elem.font);
    j["rect"]         = rect_to_json(elem.rect);
    j["hwnd"]         = reinterpret_cast<uintptr_t>(elem.hwnd);
    j["source_api"]   = elem.source_api;
    j["timestamp_ms"] = elem.timestamp_ms;
    return j;
}

static json window_node_to_json(const WindowNode& node) {
    json j;
    j["hwnd"]       = reinterpret_cast<uintptr_t>(node.hwnd);
    j["class_name"] = SceneGraph::to_utf8(node.class_name);
    j["title"]      = SceneGraph::to_utf8(node.title);
    j["rect"]       = {
        {"x", node.rect.left},
        {"y", node.rect.top},
        {"w", node.rect.right - node.rect.left},
        {"h", node.rect.bottom - node.rect.top}
    };
    j["parent_hwnd"] = reinterpret_cast<uintptr_t>(node.parent_hwnd);
    j["visible"]     = node.visible;
    j["z_order"]     = node.z_order;

    json children = json::array();
    for (HWND child : node.children_hwnds) {
        children.push_back(reinterpret_cast<uintptr_t>(child));
    }
    j["children_hwnds"] = children;

    return j;
}

std::string SceneGraph::serialize_full() const {
    AcquireSRWLockShared(const_cast<PSRWLOCK>(&m_lock));

    json root;
    root["version"]      = m_version;
    root["timestamp_ms"] = GetTickCount64();
    root["stale"]        = (GetTickCount64() - m_last_update_ms) > STALENESS_THRESHOLD_MS;

    // Windows
    json windows_arr = json::array();
    auto tree = window_hooks::get_window_tree();
    for (const auto& [hwnd, node] : tree) {
        windows_arr.push_back(window_node_to_json(node));
    }
    root["windows"] = windows_arr;

    // Text elements (current frame + previous frame for completeness)
    json text_arr = json::array();
    for (const auto& elem : m_text_elements) {
        text_arr.push_back(text_element_to_json(elem));
    }
    // Also include prev frame elements if current frame is sparse
    if (m_text_elements.empty()) {
        for (const auto& elem : m_prev_text_elements) {
            text_arr.push_back(text_element_to_json(elem));
        }
    }
    root["text_elements"] = text_arr;

    // Frame capture
    if (m_frame_capture_available) {
        root["frame_capture"] = "available";
    } else {
        root["frame_capture"] = nullptr;
    }

    ReleaseSRWLockShared(const_cast<PSRWLOCK>(&m_lock));

    return root.dump();
}

std::string SceneGraph::serialize_diff(uint64_t since_version) const {
    AcquireSRWLockShared(const_cast<PSRWLOCK>(&m_lock));

    // If the requested version is current, return minimal response
    if (since_version >= m_version) {
        json root;
        root["version"]      = m_version;
        root["timestamp_ms"] = GetTickCount64();
        root["stale"]        = (GetTickCount64() - m_last_update_ms) > STALENESS_THRESHOLD_MS;
        root["changed"]      = false;

        ReleaseSRWLockShared(const_cast<PSRWLOCK>(&m_lock));
        return root.dump();
    }

    ReleaseSRWLockShared(const_cast<PSRWLOCK>(&m_lock));

    // Version has changed — return full snapshot for simplicity
    // (a more sophisticated diff could track per-element versions)
    std::string full = serialize_full();

    // Parse and add the "changed" flag
    json parsed = json::parse(full);
    parsed["changed"] = true;
    return parsed.dump();
}

} // namespace sandbox
