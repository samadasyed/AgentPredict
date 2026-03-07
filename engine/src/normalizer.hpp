#pragma once

#include <optional>
#include <string>
#include "events.pb.h"

namespace agentpredict {

// Stateless — safe to call from multiple threads simultaneously.
// Validates raw proto messages, stamps event_id (UUID v4) and ingested_at.
class Normalizer {
public:
    Normalizer() = default;

    // Validates and stamps a CanonicalEvent in-place.
    // Returns std::nullopt with an error string on failure.
    struct Result {
        bool        ok    = false;
        std::string error;  // populated when !ok
    };

    // Maximum allowed clock skew between source timestamp and ingestion time.
    static constexpr int64_t kMaxClockSkewMs = 60'000;  // 60 seconds

    // Normalize a pre-constructed CanonicalEvent arriving via gRPC.
    // Sets event_id (UUID v4) and ingested_at (system_clock millis).
    // Validates:
    //   - source is not SOURCE_UNKNOWN
    //   - payload is set (market_event or fight_event)
    //   - MarketEvent: probability in [0,1], market_id non-empty
    //   - FightStatEvent: fight_id and fighter_name non-empty
    //   - source timestamp within ±kMaxClockSkewMs of now
    [[nodiscard]] Result Normalize(CanonicalEvent& event) const;

private:
    [[nodiscard]] Result ValidateMarket(const MarketEvent& m) const;
    [[nodiscard]] Result ValidateFight(const FightStatEvent& f) const;
    [[nodiscard]] Result ValidateTimestamp(int64_t source_ts_ms) const;

    // Generates a UUID v4 string.
    [[nodiscard]] std::string GenerateUUID() const;

    // Returns current time as unix millis.
    [[nodiscard]] int64_t NowMs() const;
};

}  // namespace agentpredict
