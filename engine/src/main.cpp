#include "engine.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

int main(int /*argc*/, char* /*argv*/[]) {
    agentpredict::Engine::Config cfg;

    // Read gRPC address from environment; fall back to default.
    if (const char* addr = std::getenv("ENGINE_GRPC_ADDRESS"); addr != nullptr) {
        cfg.grpc_address = addr;
    }

    // Optional ring-buffer capacity override (must be a power of 2 in [1, 1<<24]).
    if (const char* cap = std::getenv("ENGINE_RING_CAPACITY"); cap != nullptr) {
        if (!agentpredict::ParseRingCapacity(cap, cfg.ring_capacity)) {
            std::cerr << "[engine] invalid ENGINE_RING_CAPACITY=\"" << cap
                      << "\" — must be a power of 2 in [1, 16777216]\n";
            return 1;
        }
    }

    // TODO: wire a structured logger + ENGINE_LOG_LEVEL (currently cout/cerr only).

    try {
        // Construct inside the try: the EventStore ctor validates ring_capacity
        // and can throw std::invalid_argument.
        agentpredict::Engine engine(cfg);
        engine.Run();  // blocks until shutdown signal
    } catch (const std::exception& ex) {
        std::cerr << "[engine] fatal: " << ex.what() << '\n';
        return 1;
    }

    return 0;
}
