cmake_minimum_required(VERSION 3.22)
project(agentpredict_engine VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ─── Dependencies ─────────────────────────────────────────────────────────────

find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(GTest REQUIRED)
find_package(Threads REQUIRED)

# ─── Proto codegen ────────────────────────────────────────────────────────────

set(PROTO_FILE "${CMAKE_SOURCE_DIR}/../proto/events.proto")
set(PROTO_GENERATED_DIR "${CMAKE_BINARY_DIR}/generated")
file(MAKE_DIRECTORY ${PROTO_GENERATED_DIR})

# Generate C++ proto stubs
add_custom_command(
  OUTPUT
    "${PROTO_GENERATED_DIR}/events.pb.cc"
    "${PROTO_GENERATED_DIR}/events.pb.h"
    "${PROTO_GENERATED_DIR}/events.grpc.pb.cc"
    "${PROTO_GENERATED_DIR}/events.grpc.pb.h"
  COMMAND ${Protobuf_PROTOC_EXECUTABLE}
    --proto_path "${CMAKE_SOURCE_DIR}/../proto"
    --cpp_out "${PROTO_GENERATED_DIR}"
    --grpc_out "${PROTO_GENERATED_DIR}"
    --plugin=protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>
    "${PROTO_FILE}"
  DEPENDS "${PROTO_FILE}"
  COMMENT "Generating protobuf/gRPC C++ stubs"
)

add_library(proto_gen STATIC
  "${PROTO_GENERATED_DIR}/events.pb.cc"
  "${PROTO_GENERATED_DIR}/events.grpc.pb.cc"
)
target_include_directories(proto_gen PUBLIC "${PROTO_GENERATED_DIR}")
target_link_libraries(proto_gen PUBLIC
  protobuf::libprotobuf
  gRPC::grpc++
)

# ─── Engine library (shared between main binary and tests) ───────────────────

add_library(engine_lib STATIC
  src/normalizer.cpp
  src/event_store.cpp
  src/grpc_server.cpp
  src/engine.cpp
)
target_include_directories(engine_lib PUBLIC src "${PROTO_GENERATED_DIR}")
target_link_libraries(engine_lib PUBLIC
  proto_gen
  nlohmann_json::nlohmann_json
  Threads::Threads
)

# ─── Main executable ──────────────────────────────────────────────────────────

add_executable(engine src/main.cpp)
target_link_libraries(engine PRIVATE engine_lib)

# ─── Unit tests ───────────────────────────────────────────────────────────────

enable_testing()
add_subdirectory(tests/unit)
