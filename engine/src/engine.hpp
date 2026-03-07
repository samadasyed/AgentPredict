#pragma once

#include <memory>
#include <string>
#include "event_store.hpp"
#include "normalizer.hpp"

namespace agentpredict {

// Top-level engine object — wires together EventStore, Normalizer, gRPC server.
// Owned by main(); exposed here so tests can construct a headless engine.
class Engine {
public:
    struct Config {
        std::string grpc_address = "0.0.0.0:50051";
        size_t      ring_capacity = 4096;
    };

    explicit Engine(Config cfg = {});
    ~Engine() = default;

    // Non-copyable, non-movable.
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;

    // Start the gRPC server (blocks until shutdown).
    void Run();

    // Accessors for testing / integration.
    [[nodiscard]] std::shared_ptr<EventStore> store() const { return store_; }
    [[nodiscard]] std::shared_ptr<Normalizer> normalizer() const { return normalizer_; }

private:
    Config                       cfg_;
    std::shared_ptr<EventStore>  store_;
    std::shared_ptr<Normalizer>  normalizer_;
};

}  // namespace agentpredict
