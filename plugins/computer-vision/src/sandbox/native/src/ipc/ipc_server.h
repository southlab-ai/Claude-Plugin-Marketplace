// ==========================================================================
// ipc/ipc_server.h - TCP IPC server for host-agent communication
// ==========================================================================
// Winsock2 TCP server on 0.0.0.0 with ephemeral port.
// Writes the assigned port to a shared folder file for the host to discover.
// Single-connection model with token-based authentication.
// Heartbeat every 5 seconds. Uses select() for I/O multiplexing.
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_IPC_SERVER_H
#define SANDBOX_SHIM_IPC_SERVER_H

#include <winsock2.h>
#include <windows.h>
#include <cstdint>
#include <string>
#include <atomic>

namespace sandbox {

class IpcServer {
public:
    static IpcServer& instance();

    // Non-copyable
    IpcServer(const IpcServer&)            = delete;
    IpcServer& operator=(const IpcServer&) = delete;

    // Start the IPC server on a background thread.
    // Returns false if startup fails.
    bool start();

    // Stop the server and close all connections.
    void stop();

    // Check if the server is running
    bool is_running() const;

    // Get the port the server is listening on (0 if not started)
    uint16_t port() const;

private:
    IpcServer();
    ~IpcServer();

    // Background thread entry points
    static DWORD WINAPI server_thread_proc(LPVOID param);
    void run_server();

    // Connection handling
    void handle_connection(SOCKET client_sock);
    bool authenticate_client(SOCKET client_sock);
    void dispatch_request(SOCKET client_sock, const std::string& payload);

    // Send a framed JSON message
    bool send_frame(SOCKET sock, const std::string& json_str);
    bool send_frame_bytes(SOCKET sock, const uint8_t* data, size_t len);

    // Receive a complete framed message (blocking with timeout)
    bool recv_frame(SOCKET sock, std::string& out_payload);

    // Read the auth token from shim_token.txt
    std::string read_auth_token();

    // Write the listening port to the shared folder
    void write_port_file(uint16_t port);

    // Heartbeat sender
    void send_heartbeat(SOCKET sock);

    HANDLE           m_thread;
    std::atomic<bool> m_running;
    std::atomic<bool> m_shutdown;
    SOCKET           m_listen_sock;
    uint16_t         m_port;
    std::string      m_auth_token;
    CRITICAL_SECTION m_cs;
};

} // namespace sandbox

#endif // SANDBOX_SHIM_IPC_SERVER_H
