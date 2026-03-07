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

    // TODO: parse additional config (ring capacity, log level) from env/flags.

    agentpredict::Engine engine(cfg);

    try {
        engine.Run();  // blocks until shutdown signal
    } catch (const std::exception& ex) {
        std::cerr << "[engine] fatal: " << ex.what() << '\n';
        return 1;
    }

    return 0;
}
