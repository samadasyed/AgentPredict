#include "normalizer.hpp"

#include <chrono>
#include <cstring>
#include <random>
#include <sstream>
#include <iomanip>

namespace agentpredict {

// ─── Public ──────────────────────────────────────────────────────────────────

Normalizer::Result Normalizer::Normalize(CanonicalEvent& event) const {
    // Validate source
    if (event.source() == SOURCE_UNKNOWN) {
        return {false, "source must not be SOURCE_UNKNOWN"};
    }

    // Validate payload and extract source timestamp
    int64_t source_ts_ms = 0;
    if (event.has_market_event()) {
        auto r = ValidateMarket(event.market_event());
        if (!r.ok) return r;
        source_ts_ms = event.market_event().timestamp();
    } else if (event.has_fight_event()) {
        auto r = ValidateFight(event.fight_event());
        if (!r.ok) return r;
        source_ts_ms = event.fight_event().timestamp();
    } else {
        return {false, "CanonicalEvent has no payload set"};
    }

    // Validate timestamp
    auto tr = ValidateTimestamp(source_ts_ms);
    if (!tr.ok) return tr;

    // Stamp event_id and ingested_at
    event.set_event_id(GenerateUUID());
    event.set_ingested_at(NowMs());

    return {true, ""};
}

// ─── Private ─────────────────────────────────────────────────────────────────

Normalizer::Result Normalizer::ValidateMarket(const MarketEvent& m) const {
    if (m.market_id().empty()) {
        return {false, "MarketEvent.market_id is empty"};
    }
    if (m.probability() < 0.0 || m.probability() > 1.0) {
        return {false, "MarketEvent.probability out of [0,1]: " +
                       std::to_string(m.probability())};
    }
    return {true, ""};
}

Normalizer::Result Normalizer::ValidateFight(const FightStatEvent& f) const {
    if (f.fight_id().empty()) {
        return {false, "FightStatEvent.fight_id is empty"};
    }
    if (f.fighter_name().empty()) {
        return {false, "FightStatEvent.fighter_name is empty"};
    }
    return {true, ""};
}

Normalizer::Result Normalizer::ValidateTimestamp(int64_t source_ts_ms) const {
    int64_t now = NowMs();
    int64_t diff = std::abs(now - source_ts_ms);
    if (diff > kMaxClockSkewMs) {
        return {false, "source timestamp skew exceeds 60s: diff=" +
                       std::to_string(diff) + "ms"};
    }
    return {true, ""};
}

std::string Normalizer::GenerateUUID() const {
    // TODO: replace with a proper UUID library (e.g. libuuid) in production.
    // This is a minimal UUID v4 implementation suitable for the skeleton.
    static thread_local std::mt19937_64 rng{std::random_device{}()};
    std::uniform_int_distribution<uint64_t> dist;

    uint64_t hi = dist(rng);
    uint64_t lo = dist(rng);

    // Set version 4 bits
    hi = (hi & 0xFFFFFFFFFFFF0FFFULL) | 0x0000000000004000ULL;
    // Set variant bits
    lo = (lo & 0x3FFFFFFFFFFFFFFFULL) | 0x8000000000000000ULL;

    std::ostringstream ss;
    ss << std::hex << std::setfill('0')
       << std::setw(8) << (hi >> 32)
       << '-' << std::setw(4) << ((hi >> 16) & 0xFFFF)
       << '-' << std::setw(4) << (hi & 0xFFFF)
       << '-' << std::setw(4) << (lo >> 48)
       << '-' << std::setw(12) << (lo & 0x0000FFFFFFFFFFFFULL);
    return ss.str();
}

int64_t Normalizer::NowMs() const {
    using namespace std::chrono;
    return duration_cast<milliseconds>(
               system_clock::now().time_since_epoch())
        .count();
}

}  // namespace agentpredict
