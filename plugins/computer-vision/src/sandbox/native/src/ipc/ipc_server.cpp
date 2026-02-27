// ==========================================================================
// ipc/ipc_server.cpp - TCP IPC server implementation
// ==========================================================================

#include "ipc/ipc_server.h"
#include "ipc/json_helpers.h"
#include "scene_graph.h"
#include "message_injector.h"
#include "hooks/dxgi_hooks.h"

#include <winsock2.h>
#include <ws2tcpip.h>
#include <nlohmann/json.hpp>

#include <fstream>
#include <sstream>
#include <vector>
#include <algorithm>
#include <cstring>

#pragma comment(lib, "ws2_32.lib")

using json = nlohmann::json;

namespace sandbox {

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

static constexpr int    BACKLOG            = 1;      // single-connection model
static constexpr UINT64 HEARTBEAT_INTERVAL_MS = 5000;
static constexpr int    RECV_TIMEOUT_MS    = 100;    // select() poll interval
static constexpr size_t RECV_BUF_SIZE      = 65536;

// Shared folder path (inside Windows Sandbox mapped folder)
static const char* PORT_FILE_PATH  = "C:\\SharedFolder\\shim_port.txt";
static const char* TOKEN_FILE_PATH = "C:\\SharedFolder\\shim_token.txt";

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

IpcServer& IpcServer::instance() {
    static IpcServer s_instance;
    return s_instance;
}

IpcServer::IpcServer()
    : m_thread(nullptr)
    , m_running(false)
    , m_shutdown(false)
    , m_listen_sock(INVALID_SOCKET)
    , m_port(0)
{
    InitializeCriticalSectionAndSpinCount(&m_cs, 4000);

    // Initialize Winsock
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
}

IpcServer::~IpcServer() {
    stop();
    WSACleanup();
    DeleteCriticalSection(&m_cs);
}

// ---------------------------------------------------------------------------
// Start / Stop
// ---------------------------------------------------------------------------

bool IpcServer::start() {
    if (m_running.load()) return true;

    // Read auth token
    m_auth_token = read_auth_token();

    // Create listening socket
    m_listen_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (m_listen_sock == INVALID_SOCKET) {
        OutputDebugStringA("[SandboxShim] IPC: Failed to create socket\n");
        return false;
    }

    // Bind to 0.0.0.0 with ephemeral port
    struct sockaddr_in addr = {};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = 0; // OS assigns port

    if (bind(m_listen_sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) == SOCKET_ERROR) {
        OutputDebugStringA("[SandboxShim] IPC: bind() failed\n");
        closesocket(m_listen_sock);
        m_listen_sock = INVALID_SOCKET;
        return false;
    }

    // Get assigned port
    int addrlen = sizeof(addr);
    getsockname(m_listen_sock, reinterpret_cast<struct sockaddr*>(&addr), &addrlen);
    m_port = ntohs(addr.sin_port);

    // Listen
    if (listen(m_listen_sock, BACKLOG) == SOCKET_ERROR) {
        OutputDebugStringA("[SandboxShim] IPC: listen() failed\n");
        closesocket(m_listen_sock);
        m_listen_sock = INVALID_SOCKET;
        return false;
    }

    // Write port file
    write_port_file(m_port);

    // Log
    char msg[128];
    wsprintfA(msg, "[SandboxShim] IPC: Listening on port %u\n", m_port);
    OutputDebugStringA(msg);

    // Start server thread
    m_shutdown.store(false);
    m_thread = CreateThread(nullptr, 0, server_thread_proc, this, 0, nullptr);
    if (!m_thread) {
        closesocket(m_listen_sock);
        m_listen_sock = INVALID_SOCKET;
        return false;
    }

    m_running.store(true);
    return true;
}

void IpcServer::stop() {
    m_shutdown.store(true);

    // Close listening socket to unblock accept()
    if (m_listen_sock != INVALID_SOCKET) {
        closesocket(m_listen_sock);
        m_listen_sock = INVALID_SOCKET;
    }

    // Wait for thread
    if (m_thread) {
        WaitForSingleObject(m_thread, 5000);
        CloseHandle(m_thread);
        m_thread = nullptr;
    }

    m_running.store(false);
}

bool IpcServer::is_running() const {
    return m_running.load();
}

uint16_t IpcServer::port() const {
    return m_port;
}

// ---------------------------------------------------------------------------
// Server thread
// ---------------------------------------------------------------------------

DWORD WINAPI IpcServer::server_thread_proc(LPVOID param) {
    auto* self = static_cast<IpcServer*>(param);
    self->run_server();
    return 0;
}

void IpcServer::run_server() {
    while (!m_shutdown.load()) {
        // Use select() to wait for an incoming connection with a timeout
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(m_listen_sock, &readfds);

        struct timeval tv;
        tv.tv_sec  = 1;
        tv.tv_usec = 0;

        int sel = select(0, &readfds, nullptr, nullptr, &tv);
        if (sel == SOCKET_ERROR || m_shutdown.load()) break;
        if (sel == 0) continue; // timeout, loop again

        // Accept connection
        struct sockaddr_in client_addr = {};
        int client_len = sizeof(client_addr);
        SOCKET client_sock = accept(m_listen_sock,
            reinterpret_cast<struct sockaddr*>(&client_addr), &client_len);

        if (client_sock == INVALID_SOCKET) continue;

        OutputDebugStringA("[SandboxShim] IPC: Client connected\n");

        // Handle the single connection (blocks until disconnect)
        handle_connection(client_sock);

        closesocket(client_sock);
        OutputDebugStringA("[SandboxShim] IPC: Client disconnected\n");
    }
}

// ---------------------------------------------------------------------------
// Connection handling
// ---------------------------------------------------------------------------

void IpcServer::handle_connection(SOCKET client_sock) {
    // Step 1: Authenticate
    if (!authenticate_client(client_sock)) {
        OutputDebugStringA("[SandboxShim] IPC: Authentication failed\n");
        return;
    }

    OutputDebugStringA("[SandboxShim] IPC: Client authenticated\n");

    // Step 2: Main loop — receive requests, send responses, heartbeat
    UINT64 last_heartbeat = GetTickCount64();
    std::vector<uint8_t> recv_buf;
    recv_buf.reserve(RECV_BUF_SIZE);

    while (!m_shutdown.load()) {
        // Use select() for I/O multiplexing
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(client_sock, &readfds);

        struct timeval tv;
        tv.tv_sec  = 0;
        tv.tv_usec = RECV_TIMEOUT_MS * 1000;

        int sel = select(0, &readfds, nullptr, nullptr, &tv);
        if (sel == SOCKET_ERROR) break;

        if (sel > 0 && FD_ISSET(client_sock, &readfds)) {
            // Data available — receive a frame
            std::string payload;
            if (!recv_frame(client_sock, payload)) {
                break; // Connection lost
            }

            // Dispatch
            dispatch_request(client_sock, payload);
        }

        // Send heartbeat if interval elapsed
        UINT64 now = GetTickCount64();
        if (now - last_heartbeat >= HEARTBEAT_INTERVAL_MS) {
            send_heartbeat(client_sock);
            last_heartbeat = now;
        }
    }
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

bool IpcServer::authenticate_client(SOCKET client_sock) {
    // If no auth token configured, accept any connection
    if (m_auth_token.empty()) {
        auto frame = ipc::encode_frame(ipc::make_auth_ok());
        send_frame_bytes(client_sock, frame.data(), frame.size());
        return true;
    }

    // Receive the auth frame
    std::string payload;
    if (!recv_frame(client_sock, payload)) return false;

    try {
        json msg = json::parse(payload);
        if (msg.value("type", "") != "auth") return false;

        std::string token = msg.value("token", "");
        if (token == m_auth_token) {
            auto frame = ipc::encode_frame(ipc::make_auth_ok());
            send_frame_bytes(client_sock, frame.data(), frame.size());
            return true;
        }
    }
    catch (const json::exception&) {
        // Malformed JSON
    }

    // Auth failed
    auto frame = ipc::encode_frame(ipc::make_auth_fail());
    send_frame_bytes(client_sock, frame.data(), frame.size());
    return false;
}

// ---------------------------------------------------------------------------
// Request dispatch
// ---------------------------------------------------------------------------

void IpcServer::dispatch_request(SOCKET client_sock, const std::string& payload) {
    json response;

    try {
        json req = json::parse(payload);
        uint64_t id     = req.value("id", static_cast<uint64_t>(0));
        std::string method = req.value("method", "");
        json params     = req.value("params", json::object());

        if (method == "get_scene_graph") {
            // Optional: since_version for diff
            uint64_t since = params.value("since_version", static_cast<uint64_t>(0));
            std::string sg_json;
            if (since > 0) {
                sg_json = SceneGraph::instance().serialize_diff(since);
            } else {
                sg_json = SceneGraph::instance().serialize_full();
            }
            json result = json::parse(sg_json);
            response = ipc::make_response(id, result);
        }
        else if (method == "inject_click") {
            uintptr_t hwnd_val = params.value("hwnd", static_cast<uintptr_t>(0));
            int x      = params.value("x", 0);
            int y      = params.value("y", 0);
            int button = params.value("button", 0);

            HWND hwnd = reinterpret_cast<HWND>(hwnd_val);
            auto result = MessageInjector::instance().inject_click(hwnd, x, y, button);

            if (result.success) {
                response = ipc::make_response(id, {{"ok", true}});
            } else {
                response = ipc::make_error_response(id, result.error);
            }
        }
        else if (method == "inject_keys") {
            uintptr_t hwnd_val = params.value("hwnd", static_cast<uintptr_t>(0));
            std::string keys_utf8 = params.value("keys", "");
            uint32_t modifiers    = params.value("modifiers", static_cast<uint32_t>(0));

            HWND hwnd = reinterpret_cast<HWND>(hwnd_val);

            // Convert UTF-8 keys to wide string
            int wlen = MultiByteToWideChar(CP_UTF8, 0, keys_utf8.c_str(),
                                           static_cast<int>(keys_utf8.size()), nullptr, 0);
            std::wstring wkeys(wlen, L'\0');
            MultiByteToWideChar(CP_UTF8, 0, keys_utf8.c_str(),
                                static_cast<int>(keys_utf8.size()), &wkeys[0], wlen);

            auto result = MessageInjector::instance().inject_keys(hwnd, wkeys, modifiers);

            if (result.success) {
                response = ipc::make_response(id, {{"ok", true}});
            } else {
                response = ipc::make_error_response(id, result.error);
            }
        }
        else if (method == "inject_message") {
            uintptr_t hwnd_val = params.value("hwnd", static_cast<uintptr_t>(0));
            UINT msg     = params.value("msg", static_cast<UINT>(0));
            WPARAM wp    = params.value("wparam", static_cast<WPARAM>(0));
            LPARAM lp    = params.value("lparam", static_cast<LPARAM>(0));

            HWND hwnd = reinterpret_cast<HWND>(hwnd_val);
            auto result = MessageInjector::instance().inject_message(hwnd, msg, wp, lp);

            if (result.success) {
                response = ipc::make_response(id, {{"ok", true}});
            } else {
                response = ipc::make_error_response(id, result.error);
            }
        }
        else if (method == "capture_frame") {
            auto frame = dxgi_hooks::get_latest_frame();
            if (frame.valid) {
                // Encode BGRA pixels as base64 would be huge;
                // instead return metadata and provide raw data on request
                json result;
                result["width"]        = frame.width;
                result["height"]       = frame.height;
                result["timestamp_ms"] = frame.timestamp_ms;
                result["format"]       = "bgra8888";
                result["size_bytes"]   = frame.bgra_pixels.size();
                // For actual pixel transfer we'd use a binary channel;
                // here we indicate the frame is available
                result["available"]    = true;
                response = ipc::make_response(id, result);
            } else {
                response = ipc::make_response(id, {{"available", false}});
            }
        }
        else if (method == "ping") {
            json result;
            result["pong"]         = true;
            result["timestamp_ms"] = GetTickCount64();
            result["version"]      = SceneGraph::instance().current_version();
            response = ipc::make_response(id, result);
        }
        else {
            response = ipc::make_error_response(id, "Unknown method: " + method);
        }
    }
    catch (const json::exception& e) {
        response = ipc::make_error_response(0, std::string("JSON parse error: ") + e.what());
    }

    auto frame = ipc::encode_frame(response);
    send_frame_bytes(client_sock, frame.data(), frame.size());
}

// ---------------------------------------------------------------------------
// Heartbeat
// ---------------------------------------------------------------------------

void IpcServer::send_heartbeat(SOCKET sock) {
    json hb = ipc::make_heartbeat(
        GetTickCount64(),
        SceneGraph::instance().current_version()
    );
    auto frame = ipc::encode_frame(hb);
    send_frame_bytes(sock, frame.data(), frame.size());
}

// ---------------------------------------------------------------------------
// Framed I/O
// ---------------------------------------------------------------------------

bool IpcServer::send_frame(SOCKET sock, const std::string& json_str) {
    json j = json::parse(json_str);
    auto frame = ipc::encode_frame(j);
    return send_frame_bytes(sock, frame.data(), frame.size());
}

bool IpcServer::send_frame_bytes(SOCKET sock, const uint8_t* data, size_t len) {
    size_t sent = 0;
    while (sent < len) {
        int n = ::send(sock, reinterpret_cast<const char*>(data + sent),
                       static_cast<int>(len - sent), 0);
        if (n == SOCKET_ERROR) return false;
        sent += static_cast<size_t>(n);
    }
    return true;
}

bool IpcServer::recv_frame(SOCKET sock, std::string& out_payload) {
    // Read 4-byte length header
    uint8_t header[4];
    size_t got = 0;
    while (got < 4) {
        int n = ::recv(sock, reinterpret_cast<char*>(header + got),
                       static_cast<int>(4 - got), 0);
        if (n <= 0) return false; // Connection closed or error
        got += static_cast<size_t>(n);
    }

    uint32_t payload_len = ipc::decode_frame_length(header);

    // Validate frame size
    if (payload_len > ipc::MAX_FRAME_SIZE) {
        OutputDebugStringA("[SandboxShim] IPC: Frame too large, rejecting\n");
        return false;
    }

    if (payload_len == 0) {
        out_payload.clear();
        return true;
    }

    // Read payload
    out_payload.resize(payload_len);
    got = 0;
    while (got < payload_len) {
        int n = ::recv(sock, &out_payload[got],
                       static_cast<int>(payload_len - got), 0);
        if (n <= 0) return false;
        got += static_cast<size_t>(n);
    }

    return true;
}

// ---------------------------------------------------------------------------
// File I/O helpers
// ---------------------------------------------------------------------------

std::string IpcServer::read_auth_token() {
    std::ifstream f(TOKEN_FILE_PATH);
    if (!f.is_open()) {
        OutputDebugStringA("[SandboxShim] IPC: No auth token file found, running without auth\n");
        return "";
    }

    std::string token;
    std::getline(f, token);

    // Trim whitespace
    while (!token.empty() && (token.back() == '\r' || token.back() == '\n' || token.back() == ' ')) {
        token.pop_back();
    }

    return token;
}

void IpcServer::write_port_file(uint16_t port) {
    std::ofstream f(PORT_FILE_PATH, std::ios::trunc);
    if (f.is_open()) {
        f << port;
        f.flush();
    } else {
        OutputDebugStringA("[SandboxShim] IPC: WARNING - Could not write port file\n");
    }
}

} // namespace sandbox
