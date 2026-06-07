#pragma once

#include <memory>
#include <string>
#include "event_store.hpp"
#include "normalizer.hpp"

namespace agentpredict {

// Parse & validate a ring-buffer capacity from a config string (e.g. the
// ENGINE_RING_CAPACITY env var). Accepts a bare non-negative decimal integer
// that is a power of 2 within [1, 1<<24]. Returns false (leaving `out` unchanged)
// for empty / signed / non-numeric / overflowing / zero / non-power-of-2 / too-large
// input, so the caller can emit one clear error at the config boundary instead of
// letting a deep EventStore allocation/throw surface the failure.
bool ParseRingCapacity(const std::string& s, size_t& out);

// Top-level engine object — wires together EventStore, Normalizer, gRPC server.
// Owned by main(); exposed here so tests can construct a headless engine.
class Engine {
public:
    struct Config {
        std::string grpc_address = "0.0.0.0:50051";
        size_t      ring_capacity = 4096;
    };

    // Two constructors instead of one with a `Config cfg = {}` default argument:
    // a brace-init default arg would force evaluation of Config's default member
    // initializers inside Engine's still-incomplete class body, which is ill-formed
    // (CWG 1397 — "default member initializer required before the end of its
    // enclosing class"). Defaulting out of line in engine.cpp sidesteps that.
    Engine();                     // default-configured engine
    explicit Engine(Config cfg);  // engine with an explicit config
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
