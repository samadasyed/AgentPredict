#include <gtest/gtest.h>
#include <atomic>
#include <chrono>
#include <thread>
#include <vector>
#include "event_store.hpp"
#include "events.pb.h"

namespace agentpredict {
namespace {

// Builds a minimal CanonicalEvent with a given event_id.
CanonicalEvent MakeEvent(const std::string& id) {
    CanonicalEvent ev;
    ev.set_event_id(id);
    ev.set_source(SOURCE_POLYMARKET);
    ev.set_ingested_at(1000);
    auto* m = ev.mutable_market_event();
    m->set_market_id("market-" + id);
    m->set_probability(0.5);
    m->set_timestamp(1000);
    return ev;
}

// ─── Constructor ──────────────────────────────────────────────────────────────

TEST(EventStoreTest, RejectsNonPowerOfTwoCapacity) {
    EXPECT_THROW(EventStore(3), std::invalid_argument);
    EXPECT_THROW(EventStore(0), std::invalid_argument);
}

TEST(EventStoreTest, AcceptsPowerOfTwoCapacity) {
    EXPECT_NO_THROW(EventStore(4));
    EXPECT_NO_THROW(EventStore(1024));
}

// ─── Basic append / read ──────────────────────────────────────────────────────

TEST(EventStoreTest, InitialCursorIsZero) {
    EventStore store(4);
    EXPECT_EQ(store.CurrentCursor(), 0u);
}

TEST(EventStoreTest, CursorAdvancesOnAppend) {
    EventStore store(4);
    store.Append(MakeEvent("a"));
    EXPECT_EQ(store.CurrentCursor(), 1u);
    store.Append(MakeEvent("b"));
    EXPECT_EQ(store.CurrentCursor(), 2u);
}

TEST(EventStoreTest, GetSinceReturnsNewEvents) {
    EventStore store(4);
    uint64_t start = store.CurrentCursor();
    store.Append(MakeEvent("a"));
    store.Append(MakeEvent("b"));
    auto [events, next] = store.GetSince(start);
    ASSERT_EQ(events.size(), 2u);
    EXPECT_EQ(events[0].event_id(), "a");
    EXPECT_EQ(events[1].event_id(), "b");
    EXPECT_EQ(next, 2u);
}

TEST(EventStoreTest, GetSinceAtCurrentCursorReturnsEmpty) {
    EventStore store(4);
    store.Append(MakeEvent("x"));
    auto [events, next] = store.GetSince(store.CurrentCursor());
    EXPECT_TRUE(events.empty());
    EXPECT_EQ(next, 1u);
}

// ─── Ring overflow ────────────────────────────────────────────────────────────

TEST(EventStoreTest, RingOverwritesOldEvents) {
    // Capacity 4; append 6 events — first 2 are overwritten.
    EventStore store(4);
    for (int i = 0; i < 6; ++i) {
        store.Append(MakeEvent(std::to_string(i)));
    }
    // Only last 4 events are available.
    auto [events, _] = store.GetSince(0);
    ASSERT_EQ(events.size(), 4u);
    EXPECT_EQ(events[0].event_id(), "2");
    EXPECT_EQ(events[3].event_id(), "5");
}

TEST(EventStoreTest, TotalIngestedCountsAll) {
    EventStore store(4);
    for (int i = 0; i < 6; ++i) store.Append(MakeEvent(std::to_string(i)));
    EXPECT_EQ(store.TotalIngested(), 6u);
}

// ─── Concurrent reads ─────────────────────────────────────────────────────────
// NOTE: run this test suite under TSan to catch data races.
// cmake -DCMAKE_CXX_FLAGS="-fsanitize=thread -g" .. && ctest -V

TEST(EventStoreTest, ConcurrentReadsDoNotCrash) {
    EventStore store(512);
    std::atomic<bool> stop{false};

    // Writer thread.
    std::thread writer([&] {
        for (int i = 0; i < 1000 && !stop.load(); ++i) {
            store.Append(MakeEvent(std::to_string(i)));
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
        stop.store(true);
    });

    // Multiple reader threads.
    std::vector<std::thread> readers;
    for (int r = 0; r < 4; ++r) {
        readers.emplace_back([&] {
            uint64_t cursor = 0;
            while (!stop.load()) {
                auto [events, next] = store.GetSince(cursor);
                cursor = next;
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        });
    }

    writer.join();
    for (auto& t : readers) t.join();
    // If we got here without crash / TSan report, the test passes.
    SUCCEED();
}

TEST(EventStoreTest, WaitForNewReturnsTrueWhenEventArrives) {
    EventStore store(4);
    uint64_t start = store.CurrentCursor();

    std::thread writer([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        store.Append(MakeEvent("delayed"));
    });

    bool got = store.WaitForNew(start, /*timeout_ms=*/500);
    writer.join();
    EXPECT_TRUE(got);
}

TEST(EventStoreTest, WaitForNewTimesOutWhenNoEvent) {
    EventStore store(4);
    uint64_t cursor = store.CurrentCursor();
    bool got = store.WaitForNew(cursor, /*timeout_ms=*/50);
    EXPECT_FALSE(got);
}

}  // namespace
}  // namespace agentpredict
