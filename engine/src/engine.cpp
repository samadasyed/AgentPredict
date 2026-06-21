#include "engine.hpp"
#include "grpc_server.hpp"
#include "log.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>

namespace agentpredict {

namespace {
// Upper bound on the ring buffer (16,777,216 events ≈ a few GB worst case) — guards
// against a typo like a 19-digit power of 2 triggering an exabyte allocation.
constexpr size_t kMaxRingCapacity = 1u << 24;
}  // namespace

bool ParseRingCapacity(const std::string& s, size_t& out) {
    if (s.empty()) {
        return false;
    }
    // Require a pure run of ASCII digits: rejects signs (std::stoull turns "-1"
    // into UINT64_MAX with no error), whitespace, and trailing junk.
    if (!std::all_of(s.begin(), s.end(),
                     [](unsigned char c) { return std::isdigit(c) != 0; })) {
        return false;
    }
    unsigned long long value = 0;
    try {
        size_t pos = 0;
        value = std::stoull(s, &pos);
        if (pos != s.size()) {
            return false;
        }
    } catch (const std::exception&) {
        return false;  // std::out_of_range (overflow) or std::invalid_argument
    }
    if (value == 0 || value > kMaxRingCapacity) {
        return false;
    }
    if ((value & (value - 1)) != 0) {
        return false;  // must be a power of 2 (EventStore requirement)
    }
    out = static_cast<size_t>(value);
    return true;
}

// Delegate to the explicit ctor with a freshly default-constructed Config. Legal
// here (unlike a `= {}` default arg in the header) because Engine and Config are
// both complete at this point.
Engine::Engine() : Engine(Config{}) {}

Engine::Engine(Config cfg)
    : cfg_(std::move(cfg)),
      store_(std::make_shared<EventStore>(cfg_.ring_capacity)),
      normalizer_(std::make_shared<Normalizer>()) {
    LOG_INFO("initialized — ring_capacity=" << cfg_.ring_capacity
             << " grpc=" << cfg_.grpc_address);
}

void Engine::Run() {
    RunGrpcServer(cfg_.grpc_address, store_, normalizer_);
}

}  // namespace agentpredict
