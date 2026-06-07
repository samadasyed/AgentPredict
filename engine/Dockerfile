# C++ engine image.
#
# Single-stage by design: it bundles the exact gRPC/Protobuf runtime the binary was
# built against, avoiding the fragile "copy the right .so files into a slim runtime"
# dance. Image size is traded for build reliability; a slim multi-stage runtime is a
# future optimization.
#
# Build context MUST be the repo root (see docker-compose.yml: context "."), because
# engine/CMakeLists.txt resolves the proto at ${CMAKE_SOURCE_DIR}/../proto — so /app
# needs both proto/ and engine/ side-by-side.
FROM ubuntu:24.04

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# Build toolchain + gRPC/Protobuf/JSON/GTest dev packages. libgrpc++-dev provides
# the gRPCConfig.cmake used by find_package(gRPC) and the grpc_cpp_plugin target;
# if a future base image drops that config, build gRPC from source instead.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        protobuf-compiler \
        protobuf-compiler-grpc \
        libprotobuf-dev \
        libgrpc++-dev \
        nlohmann-json3-dev \
        libgtest-dev \
    && rm -rf /var/lib/apt/lists/*

# proto/ and engine/ must sit side-by-side (../proto resolution in CMakeLists).
COPY proto/ proto/
COPY engine/ engine/

RUN cmake -S engine -B engine/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build engine/build -j "$(nproc)"

EXPOSE 50051

ENV ENGINE_GRPC_ADDRESS=0.0.0.0:50051

# Absolute path so it resolves regardless of the runtime working directory.
CMD ["/app/engine/build/engine"]
