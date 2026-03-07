#include "engine.hpp"
#include "grpc_server.hpp"

#include <iostream>

namespace agentpredict {

Engine::Engine(Config cfg)
    : cfg_(std::move(cfg)),
      store_(std::make_shared<EventStore>(cfg_.ring_capacity)),
      normalizer_(std::make_shared<Normalizer>()) {
    std::cout << "[engine] initialized — ring_capacity=" << cfg_.ring_capacity
              << " grpc=" << cfg_.grpc_address << '\n';
}

void Engine::Run() {
    // TODO: read config from environment / config file before production.
    RunGrpcServer(cfg_.grpc_address, store_, normalizer_);
}

}  // namespace agentpredict
