#include "engine.hpp"
#include "log.hpp"

#include <cstdlib>
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
            LOG_ERROR("invalid ENGINE_RING_CAPACITY=\"" << cap
                      << "\" — must be a power of 2 in [1, 16777216]");
            return 1;
        }
    }

    try {
        // Construct inside the try: the EventStore ctor validates ring_capacity
        // and can throw std::invalid_argument.
        agentpredict::Engine engine(cfg);
        engine.Run();  // blocks until shutdown signal
    } catch (const std::exception& ex) {
        LOG_ERROR("fatal: " << ex.what());
        return 1;
    }

    return 0;
}
