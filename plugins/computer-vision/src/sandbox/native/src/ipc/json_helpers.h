// ==========================================================================
// ipc/json_helpers.h - JSON construction helpers for IPC protocol
// ==========================================================================
// Provides helper functions for building the length-prefixed JSON wire
// protocol used between the shim DLL and the Python host agent.
//
// Wire format: [4-byte LE uint32 length][UTF-8 JSON payload]
// Max frame: 16 MB
//
// Protocol messages:
//   Request:   {"id": N, "method": "name", "params": {...}}
//   Response:  {"id": N, "result": {...}, "error": null|"msg"}
//   Auth:      {"type": "auth", "token": "hex"}
//   Auth OK:   {"type": "auth_ok"}
//   Auth Fail: {"type": "auth_fail"}
//   Heartbeat: {"type": "heartbeat", "ts": ms, "version": N}
// ==========================================================================

#pragma once

#ifndef SANDBOX_SHIM_JSON_HELPERS_H
#define SANDBOX_SHIM_JSON_HELPERS_H

#include <nlohmann/json.hpp>
#include <string>
#include <vector>
#include <cstdint>
#include <cstring>

namespace sandbox {
namespace ipc {

using json = nlohmann::json;

// Maximum frame size: 16 MB
static constexpr uint32_t MAX_FRAME_SIZE = 16 * 1024 * 1024;

// ---------------------------------------------------------------------------
// Wire encoding / decoding
// ---------------------------------------------------------------------------

// Encode a JSON value into a length-prefixed frame (4-byte LE + UTF-8)
inline std::vector<uint8_t> encode_frame(const json& j) {
    std::string payload = j.dump();
    uint32_t len = static_cast<uint32_t>(payload.size());

    std::vector<uint8_t> frame(4 + payload.size());
    // Little-endian uint32
    frame[0] = static_cast<uint8_t>(len & 0xFF);
    frame[1] = static_cast<uint8_t>((len >> 8) & 0xFF);
    frame[2] = static_cast<uint8_t>((len >> 16) & 0xFF);
    frame[3] = static_cast<uint8_t>((len >> 24) & 0xFF);
    std::memcpy(frame.data() + 4, payload.data(), payload.size());

    return frame;
}

// Decode a 4-byte LE length prefix from a buffer
inline uint32_t decode_frame_length(const uint8_t* buf) {
    return static_cast<uint32_t>(buf[0])
         | (static_cast<uint32_t>(buf[1]) << 8)
         | (static_cast<uint32_t>(buf[2]) << 16)
         | (static_cast<uint32_t>(buf[3]) << 24);
}

// ---------------------------------------------------------------------------
// Response builders
// ---------------------------------------------------------------------------

// Build a successful response
inline json make_response(uint64_t id, const json& result) {
    json resp;
    resp["id"]     = id;
    resp["result"] = result;
    resp["error"]  = nullptr;
    return resp;
}

// Build an error response
inline json make_error_response(uint64_t id, const std::string& error) {
    json resp;
    resp["id"]     = id;
    resp["result"] = nullptr;
    resp["error"]  = error;
    return resp;
}

// Build auth_ok
inline json make_auth_ok() {
    return {{"type", "auth_ok"}};
}

// Build auth_fail
inline json make_auth_fail() {
    return {{"type", "auth_fail"}};
}

// Build heartbeat
inline json make_heartbeat(uint64_t timestamp_ms, uint64_t version) {
    json hb;
    hb["type"]    = "heartbeat";
    hb["ts"]      = timestamp_ms;
    hb["version"] = version;
    return hb;
}

} // namespace ipc
} // namespace sandbox

#endif // SANDBOX_SHIM_JSON_HELPERS_H
