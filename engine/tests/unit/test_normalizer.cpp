#include <gtest/gtest.h>
#include <chrono>
#include "normalizer.hpp"
#include "events.pb.h"

namespace agentpredict {
namespace {

// Returns current unix millis.
int64_t NowMs() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

// Builds a valid MarketEvent CanonicalEvent ready for normalization.
CanonicalEvent ValidMarketEvent() {
    CanonicalEvent ev;
    ev.set_source(SOURCE_POLYMARKET);
    auto* m = ev.mutable_market_event();
    m->set_market_id("market-123");
    m->set_outcome("Fighter A wins");
    m->set_probability(0.65);
    m->set_delta(0.05);
    m->set_timestamp(NowMs());
    return ev;
}

// Builds a valid FightStatEvent CanonicalEvent.
CanonicalEvent ValidFightEvent() {
    CanonicalEvent ev;
    ev.set_source(SOURCE_MMA);
    auto* f = ev.mutable_fight_event();
    f->set_fight_id("fight-456");
    f->set_fighter_name("Fighter B");
    f->set_stat_type("significant_strikes");
    f->set_value(42.0);
    f->set_round(2);
    f->set_timestamp(NowMs());
    return ev;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

TEST(NormalizerTest, ValidMarketEventIsAccepted) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    auto result = norm.Normalize(ev);
    EXPECT_TRUE(result.ok) << result.error;
}

TEST(NormalizerTest, StampsEventIdAndIngestedAt) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    norm.Normalize(ev);
    EXPECT_FALSE(ev.event_id().empty());
    EXPECT_GT(ev.ingested_at(), 0);
}

TEST(NormalizerTest, EventIdIsUniquePerCall) {
    Normalizer norm;
    auto ev1 = ValidMarketEvent();
    auto ev2 = ValidMarketEvent();
    norm.Normalize(ev1);
    norm.Normalize(ev2);
    EXPECT_NE(ev1.event_id(), ev2.event_id());
}

TEST(NormalizerTest, RejectsSourceUnknown) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    ev.set_source(SOURCE_UNKNOWN);
    auto result = norm.Normalize(ev);
    EXPECT_FALSE(result.ok);
    EXPECT_FALSE(result.error.empty());
}

TEST(NormalizerTest, RejectsNoPayload) {
    Normalizer norm;
    CanonicalEvent ev;
    ev.set_source(SOURCE_POLYMARKET);
    auto result = norm.Normalize(ev);
    EXPECT_FALSE(result.ok);
}

TEST(NormalizerTest, RejectsProbabilityAboveOne) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    ev.mutable_market_event()->set_probability(1.1);
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, RejectsProbabilityBelowZero) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    ev.mutable_market_event()->set_probability(-0.1);
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, AcceptsBoundaryProbabilities) {
    Normalizer norm;
    auto ev0 = ValidMarketEvent();
    ev0.mutable_market_event()->set_probability(0.0);
    EXPECT_TRUE(norm.Normalize(ev0).ok);

    auto ev1 = ValidMarketEvent();
    ev1.mutable_market_event()->set_probability(1.0);
    EXPECT_TRUE(norm.Normalize(ev1).ok);
}

TEST(NormalizerTest, RejectsEmptyMarketId) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    ev.mutable_market_event()->set_market_id("");
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, ValidFightEventIsAccepted) {
    Normalizer norm;
    auto ev = ValidFightEvent();
    EXPECT_TRUE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, RejectsEmptyFightId) {
    Normalizer norm;
    auto ev = ValidFightEvent();
    ev.mutable_fight_event()->set_fight_id("");
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, RejectsEmptyFighterName) {
    Normalizer norm;
    auto ev = ValidFightEvent();
    ev.mutable_fight_event()->set_fighter_name("");
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, RejectsTimestampTooFarInPast) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    // 120 seconds in the past — exceeds kMaxClockSkewMs (60s)
    ev.mutable_market_event()->set_timestamp(NowMs() - 120'000);
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

TEST(NormalizerTest, RejectsTimestampTooFarInFuture) {
    Normalizer norm;
    auto ev = ValidMarketEvent();
    ev.mutable_market_event()->set_timestamp(NowMs() + 120'000);
    EXPECT_FALSE(norm.Normalize(ev).ok);
}

}  // namespace
}  // namespace agentpredict
