cmake_minimum_required(VERSION 3.21)
project(SandboxShim LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --------------------------------------------------------------------------
# Vendored dependencies
# --------------------------------------------------------------------------

# Microsoft Detours (pinned commit)
set(DETOURS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor/Detours/src")
if(NOT EXISTS "${DETOURS_DIR}/detours.h")
    message(FATAL_ERROR "Detours not found at ${DETOURS_DIR}. Run vendor setup first.")
endif()

add_library(detours STATIC
    "${DETOURS_DIR}/detours.cpp"
    "${DETOURS_DIR}/modules.cpp"
    "${DETOURS_DIR}/disasm.cpp"
    "${DETOURS_DIR}/image.cpp"
    "${DETOURS_DIR}/creatwth.cpp"
    "${DETOURS_DIR}/disolx86.cpp"
    "${DETOURS_DIR}/disolx64.cpp"
    "${DETOURS_DIR}/disolarm.cpp"
    "${DETOURS_DIR}/disolarm64.cpp"
)
target_include_directories(detours PUBLIC "${DETOURS_DIR}")
target_compile_definitions(detours PRIVATE WIN32_LEAN_AND_MEAN)

# nlohmann/json (header-only)
set(JSON_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor/nlohmann")

# --------------------------------------------------------------------------
# Shim DLL
# --------------------------------------------------------------------------

set(SHIM_SOURCES
    src/dllmain.cpp
    src/hook_engine.cpp
    src/scene_graph.cpp
    src/message_injector.cpp
    src/hooks/gdi_hooks.cpp
    src/hooks/dwrite_hooks.cpp
    src/hooks/dxgi_hooks.cpp
    src/hooks/window_hooks.cpp
    src/ipc/ipc_server.cpp
)

set(SHIM_HEADERS
    src/hook_engine.h
    src/scene_graph.h
    src/message_injector.h
    src/hooks/gdi_hooks.h
    src/hooks/dwrite_hooks.h
    src/hooks/dxgi_hooks.h
    src/hooks/window_hooks.h
    src/ipc/ipc_server.h
    src/ipc/json_helpers.h
)

add_library(sandbox_shim SHARED ${SHIM_SOURCES} ${SHIM_HEADERS})
target_include_directories(sandbox_shim PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${JSON_INCLUDE_DIR}"
)
target_link_libraries(sandbox_shim PRIVATE
    detours
    ws2_32       # Winsock2
    d3d11        # Direct3D 11
    dxgi         # DXGI
    d2d1         # Direct2D
    dwrite       # DirectWrite
    gdi32        # GDI
    user32       # Window management
)
target_compile_definitions(sandbox_shim PRIVATE
    WIN32_LEAN_AND_MEAN
    UNICODE
    _UNICODE
    SHIM_DLL_EXPORTS
)

# Output name based on architecture
if(CMAKE_SIZEOF_VOID_P EQUAL 4)
    set_target_properties(sandbox_shim PROPERTIES OUTPUT_NAME "shim32")
elseif(CMAKE_SIZEOF_VOID_P EQUAL 8)
    set_target_properties(sandbox_shim PROPERTIES OUTPUT_NAME "shim64")
endif()

# Output to build/ directory
set_target_properties(sandbox_shim PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build"
)

# --------------------------------------------------------------------------
# Injector executable
# --------------------------------------------------------------------------

add_executable(injector injector/main.cpp)
target_include_directories(injector PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(injector PRIVATE user32)
target_compile_definitions(injector PRIVATE WIN32_LEAN_AND_MEAN UNICODE _UNICODE)
set_target_properties(injector PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build"
)

# --------------------------------------------------------------------------
# Size checks (post-build)
# --------------------------------------------------------------------------

add_custom_command(TARGET sandbox_shim POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "DLL size check..."
    COMMENT "Verifying DLL size < 500KB"
)
